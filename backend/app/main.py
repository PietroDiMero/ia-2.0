from __future__ import annotations

import os
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Any, List
import requests
from fastapi.middleware.cors import CORSMiddleware
from .db import init_db, connect, log_event
from .config import settings
from .indexer import index_unembedded
from crawler.run import crawl_sources, discover_new_sources
from core.search import search_answer
from .routes.admin import router as admin_router
from .routes.search import router as search_router
from contextlib import asynccontextmanager
from .startup import seed_sources_if_empty
from .tasks import celery_app  # for AsyncResult
from celery.result import AsyncResult
from .tasks import task_run_once, task_discover_once
from .evolve import seed_from_docs
import requests as _requests_diag
from .db import connect
from typing import Optional


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[name-defined]
    # Initialize DB only if DATABASE_URL is provided; allows local dev without Docker/DB
    try:
        init_db()
        seed_sources_if_empty()
    except Exception:
        pass
    yield


app = FastAPI(title="AI Auto-Evolve Backend", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    # Explicit origins to satisfy browsers when credentials are allowed
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(admin_router)
app.include_router(search_router)



@app.get("/health")
def health():
    return {
        "status": "ok",
        "env": settings.env,
        "version": settings.version,
        "time": datetime.utcnow().isoformat() + "Z",
    }

# --- New unified ingestion/search pipeline endpoints for frontend --- #

@app.post("/crawl/run")
def crawl_run(limit: int = 50):
    try:
        inserted = crawl_sources(limit=limit)
        return {"status": "ok", "inserted": inserted}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.post("/index/run")
def index_run(batch: int = 50):
    try:
        indexed = index_unembedded(batch_size=batch)
        return {"status": "ok", "indexed": indexed}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.post("/discover/run")
def discover_run(per_query: int = 5, max_new: int = 25, queries: str | None = None):
    try:
        qs = [q.strip() for q in queries.split(",") if q.strip()] if queries else None
        new_sources = discover_new_sources(per_query=per_query, max_new=max_new, queries=qs)
        return {"status": "ok", "new_sources": new_sources}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.post("/discover/run_async")
def discover_run_async(per_query: int = 5, max_new: int = 25, queries: str | None = None):
    try:
        qs = [q.strip() for q in queries.split(",") if q.strip()] if queries else None
        async_res = task_discover_once.delay(per_query=per_query, max_new=max_new, queries=qs)
        return {"status": "ok", "task_id": async_res.id}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/tasks/{task_id}")
def task_status(task_id: str):
    try:
        res: AsyncResult = AsyncResult(task_id, app=celery_app)
        out: dict[str, Any] = {"task_id": task_id, "state": res.state}
        if res.successful():
            out["status"] = "ok"
            if isinstance(res.result, dict):
                out.update(res.result)
        elif res.failed():
            out["status"] = "error"
            out["error"] = str(res.result)
        else:
            out["status"] = "pending"
        return out
    except Exception as e:
        return {"task_id": task_id, "status": "error", "error": str(e)}

@app.get("/docs")
def docs_list(limit: int = 50, offset: int = 0):
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT url, title, published_at, lang, created_at FROM documents ORDER BY id DESC LIMIT %s OFFSET %s;",
                    (limit, offset),
                )
                rows = cur.fetchall()
        return {
            "items": [
                {
                    "url": r[0],
                    "title": r[1],
                    "date": r[2].isoformat() if r[2] else None,
                    "lang": r[3],
                    "created_at": r[4].isoformat() if r[4] else None,
                }
                for r in rows
            ]
        }
    except Exception as e:
        return {"items": [], "error": str(e)}

@app.get("/metrics/history")
def metrics_history(limit: int = 50):
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ts, overall, exact, groundedness, freshness FROM ci_history ORDER BY ts DESC LIMIT %s;",
                    (limit,),
                )
                rows = cur.fetchall()
        return {
            "items": [
                {
                    "ts": r[0].isoformat(),
                    "overall": r[1],
                    "exact": r[2],
                    "groundedness": r[3],
                    "freshness": r[4],
                }
                for r in rows
            ]
        }
    except Exception as e:
        return {"items": [], "error": str(e)}


@app.get("/sources")
def list_sources(limit: int = 100, offset: int = 0):
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, url, kind, created_at FROM sources ORDER BY id ASC LIMIT %s OFFSET %s;",
                    (limit, offset),
                )
                rows = cur.fetchall()
        return {"items": [{"id": r[0], "url": r[1], "kind": r[2], "created_at": r[3].isoformat()} for r in rows]}
    except Exception:
        return {"items": []}


@app.get("/docs/latest")
def docs_latest(limit: int = 10):
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT url, title, published_at, lang FROM documents ORDER BY created_at DESC LIMIT %s;", (limit,))
                rows = cur.fetchall()
        return {"items": [{"url": r[0], "title": r[1], "date": r[2].isoformat() if r[2] else None, "lang": r[3]} for r in rows]}
    except Exception:
        return {"items": []}


@app.get("/metrics")
def metrics():
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM documents;")
                docs = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM sources;")
                sources = cur.fetchone()[0]
                # Pull last CI status and threshold (from env or stored setting)
                cur.execute("SELECT overall, exact, groundedness, freshness, updated_at FROM ci_status WHERE id=1;")
                ci = cur.fetchone()
                cur.execute("SELECT value FROM settings WHERE key='DISCOVERY_QUERIES';")
                row = cur.fetchone()
        ci_status = None
        if ci:
            ci_status = {
                "overall": float(ci[0]) if ci[0] is not None else None,
                "exact": float(ci[1]) if ci[1] is not None else None,
                "groundedness": float(ci[2]) if ci[2] is not None else None,
                "freshness": float(ci[3]) if ci[3] is not None else None,
                "updated_at": ci[4].isoformat() + "Z" if ci[4] else None,
            }
        eval_threshold = os.getenv("EVAL_MIN_OVERALL_SCORE", "0.75")
        discover_qs = None
        try:
            if row and isinstance(row[0], dict):
                discover_qs = row[0].get("queries")
        except Exception:
            discover_qs = None
        # Keep legacy fields and add UI-friendly fields expected by frontend
        return {
            "nb_docs": docs,
            "nb_sources": sources,
            "last_update": datetime.utcnow().isoformat() + "Z",
            "eval_score": None,
            # UI expected keys
            "documents": docs,
            "coverage": 1.0 if sources > 0 else 0.0,
            "freshness_days": None,
            "avg_response_time": None,
            "ci": ci_status,
            "eval_threshold": float(eval_threshold) if eval_threshold else None,
            "discovery_queries": discover_qs,
        }
    except Exception:
        return {
            "nb_docs": 0,
            "nb_sources": 0,
            "last_update": datetime.utcnow().isoformat() + "Z",
            "eval_score": None,
            "documents": 0,
            "coverage": 0.0,
            "freshness_days": None,
            "avg_response_time": None,
        }


@app.post("/ingest/crawl")
def ingest_crawl(limit: int = 10):
    try:
        n = crawl_sources(limit=limit)
        return {"inserted": n}
    except Exception as e:
        return {"inserted": 0, "error": str(e)}


@app.post("/ingest/discover")
def ingest_discover(per_query: int = 5, max_new: int = 25, queries: str | None = None):
    try:
        qs = None
        if queries:
            qs = [q.strip() for q in queries.split(",") if q.strip()]
        n = discover_new_sources(queries=qs, per_query=per_query, max_new=max_new)
        return {"new_sources": n}
    except Exception as e:
        return {"new_sources": 0, "error": str(e)}


@app.post("/ingest/discover_async")
def ingest_discover_async(per_query: int = 5, max_new: int = 25, queries: str | None = None):
    try:
        qs = None
        if queries:
            qs = [q.strip() for q in queries.split(",") if q.strip()]
        async_res = task_discover_once.delay(per_query=per_query, max_new=max_new, queries=qs)
        return {"status": "ok", "task_id": async_res.id}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/ingest/index")
def ingest_index(batch_size: int = 10):
    try:
        n = index_unembedded(batch_size=batch_size)
        return {"indexed": n}
    except Exception as e:
        return {"indexed": 0, "error": str(e)}


@app.get("/search")
def search(q: str, k: int = 6):
    try:
        res = search_answer(q, top_k=k)
        # build sources array [[title,url], ...]
        sources = [[c.get("title") or "", c.get("url") or ""] for c in res.get("citations", [])]
        return {"query": q, **res, "sources": sources}
    except Exception as e:
        return {"query": q, "answer": "Je ne sais pas", "citations": [], "sources": [], "confidence": 0.0, "error": str(e)}


# --- Simple evaluation endpoint to compute basic quality metrics --- #

class EvaluateBody(BaseModel):
    questions: list[str] | None = None
    record: bool = True


def _evaluate_exact(answer: str, question: str) -> float:
    # naive exactness: proportion of question tokens appearing in answer
    q_tokens = {t.lower() for t in question.split() if len(t) > 2}
    if not q_tokens:
        return 0.0
    a_tokens = {t.lower() for t in answer.split()}
    inter = len(q_tokens.intersection(a_tokens))
    return round(inter / len(q_tokens), 3)


def _evaluate_grounded(citations: list[dict[str, Any]]) -> float:
    # groundedness: 1.0 if at least one citation, else 0
    return 1.0 if citations else 0.0


@app.post("/evaluate/run")
def evaluate_run(body: EvaluateBody):
    questions = body.questions or [
        "Qu'est-ce qu'un agent auto-évolutif ?",
        "Comment fonctionne l'index actuel ?",
        "Quel est l'objectif du système ?",
    ]
    results: list[dict[str, Any]] = []
    exact_scores: list[float] = []
    grounded_scores: list[float] = []
    for q in questions:
        try:
            r = search_answer(q)
            ex = _evaluate_exact(r.get("answer", ""), q)
            gr = _evaluate_grounded(r.get("citations", []))
            exact_scores.append(ex)
            grounded_scores.append(gr)
            results.append({
                "question": q,
                "answer": r.get("answer"),
                "exact": ex,
                "grounded": gr,
                "confidence": r.get("confidence"),
                "citations": r.get("citations", []),
            })
        except Exception as e:  # continue evaluating others
            results.append({"question": q, "error": str(e), "exact": 0.0, "grounded": 0.0})
    overall_exact = sum(exact_scores) / max(1, len(exact_scores))
    overall_grounded = sum(grounded_scores) / max(1, len(grounded_scores))
    overall = round((overall_exact * 0.6 + overall_grounded * 0.4), 3)

    if body.record:
        try:
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO ci_history(overall, exact, groundedness, semantic_f1, freshness, avg_freshness_days, meta) VALUES(%s,%s,%s,%s,%s,%s,%s);",
                        (
                            overall,
                            overall_exact,
                            overall_grounded,
                            None,
                            None,
                            None,
                            _requests_diag.types.json.Json({"questions": questions}),
                        ),
                    )
                    cur.execute(
                        "INSERT INTO ci_status(id, overall, exact, groundedness, freshness, updated_at) VALUES(1,%s,%s,%s,%s,NOW()) ON CONFLICT (id) DO UPDATE SET overall=EXCLUDED.overall, exact=EXCLUDED.exact, groundedness=EXCLUDED.groundedness, freshness=EXCLUDED.freshness, updated_at=NOW();",
                        (overall, overall_exact, overall_grounded, None),
                    )
                conn.commit()
            log_event("evolve", "Evaluation enregistrée", meta={"overall": overall})
        except Exception:
            pass

    return {
        "status": "ok",
        "overall": overall,
        "exact": round(overall_exact, 3),
        "groundedness": round(overall_grounded, 3),
        "results": results,
    }


# Minimal jobs endpoint(s) for UI compatibility and polling
@app.get("/jobs")
def list_jobs(status: str | None = None, type: str | None = None):
    # We don't track history yet; return empty list with filters echoed
    return {"items": [], "status": status, "type": type}


@app.get("/jobs/{task_id}")
def job_status(task_id: str):
    try:
        res: AsyncResult = AsyncResult(task_id, app=celery_app)
        state = res.state
        out: dict = {"task_id": task_id, "state": state}
        if res.successful():
            out["result"] = res.result
            out["status"] = res.result.get("status", "ok") if isinstance(res.result, dict) else "ok"
        elif res.failed():
            out["status"] = "error"
            out["error"] = str(res.result)
        return out
    except Exception as e:
        return {"task_id": task_id, "state": "UNKNOWN", "status": "error", "error": str(e)}


class SourceCreate(BaseModel):
    url: str
    type: str = "html"
    allowed: bool | None = None


@app.post("/sources")
def create_source(body: SourceCreate):
    kind = body.type or "html"
    url = body.url
    if not url:
        raise HTTPException(status_code=400, detail="url manquante")
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sources(url, kind) VALUES(%s,%s) ON CONFLICT (url) DO NOTHING RETURNING id;",
                (url, kind),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        # Already exists, fetch id
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM sources WHERE url=%s;", (url,))
                row = cur.fetchone()
    return {"id": row[0] if row else None}


@app.delete("/sources/{source_id}")
def delete_source_simple(source_id: int):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sources WHERE id=%s;", (source_id,))
            deleted = cur.rowcount or 0
        conn.commit()
    return {"status": "ok", "deleted": deleted}


# Additional endpoints for frontend/workflows compatibility
class IngestRunBody(BaseModel):
    source_ids: list[int] | None = None
    new_url: str | None = None


@app.post("/ingest/run")
def ingest_run(body: IngestRunBody | None = None):
    created_source_id = None
    try:
        # Snapshot metrics before
        def _counts():
            try:
                with connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT COUNT(*) FROM sources;")
                        s = cur.fetchone()[0]
                        cur.execute("SELECT COUNT(*) FROM documents;")
                        d = cur.fetchone()[0]
                return int(s), int(d)
            except Exception:
                return 0, 0

        sources_before, docs_before = _counts()

        # Ensure seed if empty
        try:
            seed_sources_if_empty()
        except Exception:
            pass

        if body and body.new_url:
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO sources(url, kind) VALUES(%s,%s) ON CONFLICT (url) DO NOTHING RETURNING id;",
                        (body.new_url, "html"),
                    )
                    row = cur.fetchone()
                conn.commit()
            created_source_id = row[0] if row else None
        # Actively discover new sources before crawling (tunable via env)
        discovered = 0
        try:
            per_query = int(os.getenv("DISCOVERY_PER_QUERY", "5"))
            max_new = int(os.getenv("DISCOVERY_MAX_NEW", "25"))
            discovered = discover_new_sources(per_query=per_query, max_new=max_new)
        except Exception:
            discovered = 0
        # Crawl more aggressively to reflect discovery
        crawl_limit = int(os.getenv("CRAWLER_RUN_ONCE_LIMIT", "50"))
        index_batch = int(os.getenv("INDEX_RUN_ONCE_BATCH", "50"))
        ins = crawl_sources(limit=crawl_limit)
        idx = index_unembedded(batch_size=index_batch)

        sources_after, docs_after = _counts()
        return {
            "status": "ok",
            "inserted": ins,
            "indexed": idx,
            "created_source_id": created_source_id,
            "discovered": discovered,
            "new_sources_added": max(0, sources_after - sources_before),
            "docs_before": docs_before,
            "docs_after": docs_after,
            "sources_before": sources_before,
            "sources_after": sources_after,
            "task_id": None,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "inserted": 0, "indexed": 0, "task_id": None}


@app.post("/ingest/run_async")
def ingest_run_async():
    """Trigger background discovery+crawl+index and return a task id immediately."""
    try:
        per_query = int(os.getenv("DISCOVERY_PER_QUERY", "5"))
        max_new = int(os.getenv("DISCOVERY_MAX_NEW", "25"))
        crawl_limit = int(os.getenv("CRAWLER_RUN_ONCE_LIMIT", "50"))
        index_batch = int(os.getenv("INDEX_RUN_ONCE_BATCH", "50"))
        async_res = task_run_once.delay(per_query=per_query, max_new=max_new, crawl_limit=crawl_limit, index_batch=index_batch)
        return {"status": "ok", "task_id": async_res.id}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/events")
def get_events(limit: int = 100):
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ts, stage, level, message, meta FROM live_events ORDER BY id DESC LIMIT %s;",
                    (limit,),
                )
                rows = cur.fetchall()
        return {
            "items": [
                {"ts": r[0].isoformat(), "stage": r[1], "level": r[2], "message": r[3], "meta": (r[4] or {})}
                for r in rows
            ]
        }
    except Exception as e:
        return {"items": [], "error": str(e)}


class EventIn(BaseModel):
    stage: str
    level: str = "info"
    message: str
    meta: dict | None = None
    token: str | None = None


@app.post("/events")
def post_event(body: EventIn):
    # Simple token-based auth to allow CI to push events
    expected = os.getenv("EVENTS_API_TOKEN", "")
    if not expected:
        # If no token configured on server, reject to avoid abuse
        raise HTTPException(status_code=403, detail="events disabled")
    if (body.token or "") != expected:
        raise HTTPException(status_code=401, detail="invalid token")
    try:
        log_event(body.stage, body.message, level=body.level, meta=body.meta or {})
        # If payload contains evaluator scores, persist to ci_status for dashboard
        try:
            meta = body.meta or {}
            if body.stage == "evolve" and isinstance(meta, dict) and ("overall" in meta or "aggregates" in meta):
                overall = float(meta.get("overall") or meta.get("score") or 0)
                exact = None
                grounded = None
                fresh = None
                ag = meta.get("aggregates") if isinstance(meta.get("aggregates"), dict) else {}
                if ag:
                    exact = ag.get("exact")
                    grounded = ag.get("groundedness")
                    fresh = ag.get("freshness")
                with connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO ci_status(id, overall, exact, groundedness, freshness, updated_at) VALUES(1,%s,%s,%s,%s,NOW()) "
                            "ON CONFLICT (id) DO UPDATE SET overall=EXCLUDED.overall, exact=EXCLUDED.exact, groundedness=EXCLUDED.groundedness, freshness=EXCLUDED.freshness, updated_at=NOW();",
                            (overall, exact, grounded, fresh),
                        )
                    conn.commit()
        except Exception:
            pass
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/evolve/run")
def evolve_run():
    import os as _os
    import requests as _requests
    try:
        # Trim to avoid hidden spaces/newlines causing 404 on workflow dispatch
        token = (_os.getenv("GITHUB_TOKEN") or _os.getenv("GH_TOKEN") or "").strip()
        repo = (_os.getenv("GITHUB_REPOSITORY") or "").strip()
        ref = (_os.getenv("GITHUB_REF", "main") or "main").strip()
        if not token or not repo:
            msg = "GITHUB_TOKEN et GITHUB_REPOSITORY requis dans l'environnement pour déclencher la CI."
            log_event("evolve", msg, level="warn")
            return {"status": "error", "error": msg}
        # Optionally verify workflow exists before dispatch to give clearer 404 cause
        try:
            wfs = _requests.get(f"https://api.github.com/repos/{repo}/actions/workflows", headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            }, timeout=10)
            if wfs.status_code == 200:
                names = [wf.get("path") for wf in wfs.json().get("workflows", [])]
                if ".github/workflows/auto-evolve.yml" not in names:
                    log_event("evolve", "Workflow auto-evolve.yml introuvable (liste workflows)", level="error", meta={"paths": names})
                    return {"status": "error", "code": 404, "hint": "Workflow auto-evolve.yml absent dans la branche ref", "workflows": names}
        except Exception:
            pass
        url = f"https://api.github.com/repos/{repo}/actions/workflows/auto-evolve.yml/dispatches"
        r = _requests.post(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }, json={"ref": ref})
        if r.status_code in (204, 201):
            log_event("evolve", "Workflow auto-evolve déclenché", meta={"repo": repo, "ref": ref})
            return {"status": "ok"}
        else:
            # Fournir un diagnostic plus explicite pour les erreurs communes
            diagnostic: dict[str, Any] = {"status_code": r.status_code, "response": r.text}
            try:
                diagnostic["rate_limit_remaining"] = r.headers.get("x-ratelimit-remaining")
                diagnostic["rate_limit_reset"] = r.headers.get("x-ratelimit-reset")
            except Exception:
                pass
            if r.status_code == 403:
                hint = (
                    "403 GitHub API: La plupart du temps dû à un token sans le scope 'workflow'. "
                    "Assure-toi que: 1) Le PAT est un token classic avec scopes: repo, workflow (ou un fine-grained avec Actions: Read+Write). "
                    "2) Le repo ciblé correspond exactement à GITHUB_REPOSITORY='owner/repo'. "
                    "3) Le workflow existe sous .github/workflows/auto-evolve.yml et contient 'workflow_dispatch:'. "
                    "4) Si tu utilises le GITHUB_TOKEN GitHub Actions natif, l'appel externe depuis un poste local ne fonctionnera pas; utilise un PAT personnel."
                )
                diagnostic["hint"] = hint
            elif r.status_code == 404:
                diagnostic["hint"] = (
                    "404: Vérifie le nom du workflow (auto-evolve.yml) et la valeur de GITHUB_REPOSITORY." 
                    " Le fichier doit être dans la branche indiquée par ref." )
            log_event("evolve", "Échec du déclenchement CI", level="error", meta=diagnostic)
            return {"status": "error", **diagnostic}
    except Exception as e:
        log_event("evolve", f"Erreur: {e}", level="error")
        return {"status": "error", "error": str(e)}


@app.get("/evolve/workflows")
def evolve_list_workflows():
    import os as _os
    token = (_os.getenv("GITHUB_TOKEN") or _os.getenv("GH_TOKEN") or "").strip()
    repo = (_os.getenv("GITHUB_REPOSITORY") or "").strip()
    if not token or not repo:
        return {"status": "error", "error": "GITHUB_TOKEN ou GITHUB_REPOSITORY manquant"}
    url = f"https://api.github.com/repos/{repo}/actions/workflows"
    try:
        r = _requests_diag.get(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }, timeout=15)
        data = {}
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        workflows = [
            {
                "name": wf.get("name"),
                "path": wf.get("path"),
                "id": wf.get("id"),
                "state": wf.get("state"),
                "created_at": wf.get("created_at"),
                "updated_at": wf.get("updated_at"),
            }
            for wf in data.get("workflows", [])
        ]
        return {"status": "ok", "http_status": r.status_code, "count": len(workflows), "workflows": workflows}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/metrics/record")
def metrics_record(payload: dict):
    """Record a CI/evaluation run. Expected fields: overall, exact, groundedness, semantic_f1, freshness, avg_freshness_days, meta"""
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO ci_history(overall, exact, groundedness, semantic_f1, freshness, avg_freshness_days, meta) VALUES(%s,%s,%s,%s,%s,%s,%s);",
                    (
                        payload.get("overall"),
                        payload.get("exact"),
                        payload.get("groundedness"),
                        payload.get("semantic_f1"),
                        payload.get("freshness"),
                        payload.get("avg_freshness_days"),
                        _requests_diag.types.json.Json(payload.get("meta") or {}),
                    ),
                )
            conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/metrics/history")
def metrics_history(limit: Optional[int] = 50):
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, ts, overall, exact, groundedness, semantic_f1, freshness, avg_freshness_days, meta FROM ci_history ORDER BY ts DESC LIMIT %s;", (limit,))
                rows = cur.fetchall()
        items = [
            {
                "id": r[0],
                "ts": r[1].isoformat() if r[1] else None,
                "overall": r[2],
                "exact": r[3],
                "groundedness": r[4],
                "semantic_f1": r[5],
                "freshness": r[6],
                "avg_freshness_days": r[7],
                "meta": r[8],
            }
            for r in rows
        ]
        return {"items": items}
    except Exception as e:
        return {"items": [], "error": str(e)}


@app.post("/index/build")
def index_build():
    try:
        n = index_unembedded(batch_size=25)
        return {"status": "ok", "task_id": None, "indexed": n}
    except Exception as e:
        return {"status": "error", "task_id": None, "indexed": 0, "error": str(e)}


@app.post("/evolve/seed_from_docs")
def evolve_seed_from_docs(limit: int = 200, trigger_ci: bool = False):
    try:
        out = seed_from_docs(limit=limit)
        # Optionally trigger CI evolve workflow so PR includes updated topics/issues
        if trigger_ci:
            try:
                _ = evolve_run()  # reuse handler to trigger workflow and log events
                out["workflow_triggered"] = True
            except Exception:
                out["workflow_triggered"] = False
        return {"status": "ok", **out}
    except Exception as e:
        return {"status": "error", "error": str(e)}


class IndexActivateBody(BaseModel):
    index_version_id: int
    threshold_score: float | None = 0


@app.post("/index/activate")
def index_activate(body: IndexActivateBody):
    # Placeholder: no versioning implemented yet
    return {"status": "ok", "index_version_id": body.index_version_id}


@app.get("/index/versions")
def index_versions():
    return {"items": []}


class EvaluateRunBody(BaseModel):
    sets: list[str] | None = None


@app.post("/evaluate/run")
def evaluate_run(body: EvaluateRunBody | None = None):
    # Placeholder: trigger local evaluator asynchronously in a real setup
    return {"status": "ok", "task_id": None}


@app.get("/evaluate/recent")
def evaluate_recent(limit: int = 5):
    return {"items": []}


# Settings CRUD for admin (persist discovery queries and others)
class SettingIn(BaseModel):
    key: str
    value: dict | list | str | int | float | None


@app.get("/admin/settings")
def get_settings():
    try:
        out: dict[str, Any] = {}
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT key, value FROM settings;")
                for k, v in cur.fetchall():
                    out[k] = v
        # Provide env fallback preview for known toggles if not in DB
        if "EVENTS_VERBOSE" not in out:
            out["EVENTS_VERBOSE"] = os.getenv("EVENTS_VERBOSE", "0")
        if "CRAWLER_OBEY_ROBOTS" not in out:
            out["CRAWLER_OBEY_ROBOTS"] = os.getenv("CRAWLER_OBEY_ROBOTS", "1")
        # Live search related fallbacks
        if "ENABLE_LIVE_SEARCH" not in out:
            out["ENABLE_LIVE_SEARCH"] = os.getenv("ENABLE_LIVE_SEARCH", "0")
        if "LIVE_SEARCH_MODE" not in out:
            out["LIVE_SEARCH_MODE"] = os.getenv("LIVE_SEARCH_MODE", "low")
        if "LIVE_SEARCH_MAX_RESULTS" not in out:
            out["LIVE_SEARCH_MAX_RESULTS"] = os.getenv("LIVE_SEARCH_MAX_RESULTS", "3")
        return {"items": out}
    except Exception as e:
        return {"items": {}, "error": str(e)}


@app.post("/admin/settings")
def upsert_setting(body: SettingIn):
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO settings(key, value, updated_at) VALUES(%s, %s, NOW()) "
                    "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW();",
                    (body.key, body.value),
                )
            conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# Evaluator: provide helper to get publish dates for URLs to compute freshness
@app.post("/evaluator/publish_dates")
def evaluator_publish_dates(urls: List[str]):
    try:
        results: dict[str, str | None] = {}
        with connect() as conn:
            with conn.cursor() as cur:
                for u in urls:
                    cur.execute("SELECT published_at FROM documents WHERE url=%s;", (u,))
                    row = cur.fetchone()
                    results[u] = row[0].isoformat() if row and row[0] else None
        return {"items": results}
    except Exception as e:
        return {"items": {}, "error": str(e)}


@app.post("/sources/{source_id}/test")
def source_test_connectivity(source_id: int):
    url = None
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT url FROM sources WHERE id=%s;", (source_id,))
                row = cur.fetchone()
        url = row[0] if row else None
    except Exception:
        url = None
    if not url:
        raise HTTPException(status_code=404, detail="source introuvable")
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "connectivity-check/1.0"})
        return {"ok": bool(r.ok), "status": r.status_code}
    except Exception as e:
        return {"ok": False, "message": str(e)}
