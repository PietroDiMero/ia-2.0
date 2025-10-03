from __future__ import annotations

import datetime as dt
from typing import List, Optional
import json

import socketio
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session
from sqlalchemy.sql import text
from pgvector.sqlalchemy import Vector

try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg://appuser:apppass@db:5432/appdb"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"


settings = Settings()


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(32))  # rss|html|api
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(1024))
    content: Mapped[str] = mapped_column(Text)
    lang: Mapped[str | None] = mapped_column(String(10), nullable=True)
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    embedding: Mapped[List[float] | None] = mapped_column(Vector(1536), nullable=True)


engine = create_engine(settings.DATABASE_URL, future=True)
with engine.begin() as conn:
    try:
        conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    except Exception:
        pass
Base.metadata.create_all(engine)


sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
fastapi = FastAPI()
app = socketio.ASGIApp(sio, other_asgi_app=fastapi)


class AskResponse(BaseModel):
    answer: str
    citations: List[dict]
    sources: List[dict]


def _embed(text: str) -> Optional[List[float]]:
    if not settings.OPENAI_API_KEY or OpenAI is None:
        return None
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        resp = client.embeddings.create(model=settings.EMBEDDING_MODEL, input=text)
        return list(resp.data[0].embedding)
    except Exception:
        return None


def _metrics(session: Session):
    nb_docs = session.scalar(select(func.count()).select_from(Document)) or 0
    last_doc = session.execute(select(Document.title, Document.created_at).order_by(Document.created_at.desc()).limit(1)).first()
    last_title = last_doc[0] if last_doc else None
    last_date = last_doc[1].isoformat() if last_doc else None
    # avg freshness = mean age in days
    now = dt.datetime.now(dt.timezone.utc)
    docs = session.execute(select(Document.created_at)).all()
    if docs:
        ages = []
        for (created_at,) in docs:
            if created_at is None:
                continue
            delta = now - created_at
            ages.append(delta.total_seconds() / 86400.0)
        avg_fresh = sum(ages) / max(1, len(ages)) if ages else None
    else:
        avg_fresh = None
    # eval score placeholder
    eval_score = None
    return {
        "nb_docs_total": nb_docs,
        "last_doc_title": last_title,
        "last_doc_date": last_date,
        "avg_freshness": avg_fresh,
        "eval_score": eval_score,
    }


@fastapi.post("/ask", response_model=AskResponse)
def ask(q: str = Query(..., description="user query")):
    with Session(engine) as session:
        qvec = _embed(q)
        docs: List[Document]
        if qvec is None:
            docs = session.execute(select(Document).order_by(Document.created_at.desc()).limit(6)).scalars().all()
        else:
            rows = session.execute(
                text("SELECT id, title, url, content FROM documents WHERE embedding IS NOT NULL ORDER BY embedding <-> :qvec LIMIT 6"),
                {"qvec": qvec},
            ).all()
            docs = [Document(id=r.id, title=r.title, url=r.url, content=r.content) for r in rows]  # type: ignore[arg-type]
        if not docs:
            return AskResponse(answer="Je ne sais pas", citations=[], sources=[])
        paras: List[str] = []
        cites: List[dict] = []
        for d in docs[:3]:
            snippet = (d.content or "")[:180]
            paras.append(f"{snippet}… [{d.title}]({d.url})")
            cites.append({"title": d.title, "url": d.url})
        answer = "\n\n".join(paras)
        sources = [{"title": d.title, "url": d.url} for d in docs]
        return AskResponse(answer=answer, citations=cites, sources=sources)


@fastapi.get("/metrics")
def metrics():
    with Session(engine) as session:
        m = _metrics(session)
        return {
            "nb_docs": m["nb_docs_total"],
            "nb_sources": session.scalar(select(func.count()).select_from(Source)) or 0,
            "last_update": m["last_doc_date"],
            "avg_freshness": m["avg_freshness"],
        }


@fastapi.get("/realtime/metrics")
def realtime_metrics():
    with Session(engine) as session:
        return _metrics(session)


@fastapi.get("/docs/latest")
def docs_latest():
    with Session(engine) as session:
        docs = session.execute(select(Document).order_by(Document.created_at.desc()).limit(20)).scalars().all()
        return [
            {
                "id": d.id,
                "title": d.title,
                "url": d.url,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ]


class SourceIn(BaseModel):
    url: str
    type: str


@fastapi.post("/sources/add")
def sources_add(body: SourceIn):
    with Session(engine) as session:
        exists = session.scalar(select(Source).where(Source.url == body.url))
        if exists:
            raise HTTPException(status_code=409, detail="source already exists")
        s = Source(url=body.url, type=body.type)
        session.add(s)
        session.commit()
        return {"id": s.id}


async def broadcast_metrics():
    with Session(engine) as session:
        data = _metrics(session)
    await sio.emit("metrics", data)


@sio.event
async def connect(sid, environ):
    await broadcast_metrics()


class IngestIn(BaseModel):
    title: str
    url: str
    content: str


@fastapi.post("/ingest")
async def ingest(body: IngestIn):
    with Session(engine) as session:
        emb = _embed(body.title + "\n\n" + body.content)
        d = Document(title=body.title, url=body.url, content=body.content, embedding=emb)
        session.add(d)
        session.commit()
    await broadcast_metrics()
    return {"status": "ok", "id": d.id}


@fastapi.get("/evolver/history")
def evolver_history():
    # Serve evolver/history.json if present
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    history_path = repo_root / "real-time-ai-dashboard" / "evolver" / "history.json"
    if history_path.exists():
        try:
            return json.loads(history_path.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []
