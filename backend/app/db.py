from __future__ import annotations

import os
from typing import Any, Iterable, Optional

import psycopg


def get_db_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL manquant")
    # Normalize common variants (e.g., SQLAlchemy style 'postgresql+psycopg://') to libpq URI
    if url.startswith("postgresql+psycopg://"):
        url = "postgresql://" + url.split("postgresql+psycopg://", 1)[1]
    if url.startswith("postgres+psycopg://"):
        url = "postgresql://" + url.split("postgres+psycopg://", 1)[1]
    if url.startswith("postgres://"):
        # psycopg accepts postgresql://, normalize older postgres://
        url = "postgresql://" + url.split("postgres://", 1)[1]
    return url


def connect() -> psycopg.Connection:  # type: ignore
    return psycopg.connect(get_db_url())


def log_event(stage: str, message: str, level: str = "info", meta: Optional[dict[str, Any]] = None) -> None:
        try:
                with connect() as conn:
                        with conn.cursor() as cur:
                                cur.execute(
                                        "INSERT INTO live_events(stage, level, message, meta) VALUES(%s,%s,%s,%s);",
                                        (stage, level, message, psycopg.types.json.Json(meta or {})),
                                )
                        conn.commit()
        except Exception:
                # Best effort logging; ignore errors
                pass


def init_db() -> None:
    # Ensure extension and tables exist; avoid failing the whole init if index creation isn't supported
    with connect() as conn:
        with conn.cursor() as cur:
            # Extension might require superuser; ignore failure
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            except Exception:
                pass
            # sources
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    id SERIAL PRIMARY KEY,
                    url TEXT UNIQUE NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'html',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            # documents
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id BIGSERIAL PRIMARY KEY,
                    url TEXT UNIQUE NOT NULL,
                    title TEXT,
                    content TEXT,
                    published_at TIMESTAMPTZ,
                    lang TEXT,
                    hash TEXT UNIQUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    embedding vector(3072),
                    indexed BOOLEAN NOT NULL DEFAULT FALSE
                );
                """
            )
            # settings
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value JSONB,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            # ci_status
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ci_status (
                    id SMALLINT PRIMARY KEY DEFAULT 1,
                    overall DOUBLE PRECISION,
                    exact DOUBLE PRECISION,
                    groundedness DOUBLE PRECISION,
                    freshness DOUBLE PRECISION,
                    report_path TEXT,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            # ci_history
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ci_history (
                    id SERIAL PRIMARY KEY,
                    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    overall DOUBLE PRECISION,
                    exact DOUBLE PRECISION,
                    groundedness DOUBLE PRECISION,
                    semantic_f1 DOUBLE PRECISION,
                    freshness DOUBLE PRECISION,
                    avg_freshness_days DOUBLE PRECISION,
                    meta JSONB
                );
                """
            )
            # live_events
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS live_events (
                    id SERIAL PRIMARY KEY,
                    ts TIMESTAMP DEFAULT NOW(),
                    stage TEXT,
                    level TEXT,
                    message TEXT,
                    meta JSONB
                );
                """
            )
        conn.commit()

    # Optional vector index creation
    import os as _os
    index_method = (_os.getenv("VECTOR_INDEX_METHOD") or "auto").lower()
    embedding_dim = 3072
    create_stmt: Optional[str] = None
    if index_method == "hnsw":
        create_stmt = "CREATE INDEX documents_embedding_hnsw_idx ON documents USING hnsw (embedding vector_cosine_ops);"
    elif index_method in ("ivfflat", "auto") and embedding_dim <= 2000:
        create_stmt = "CREATE INDEX documents_embedding_ivfflat_idx ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists=100);"
    if create_stmt:
        try:
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                                WHERE c.relname = 'documents_embedding_ivfflat_idx' OR c.relname = 'documents_embedding_hnsw_idx'
                            ) THEN
                                {create_stmt}
                            END IF;
                        END$$;
                        """
                    )
                conn.commit()
        except Exception:
            pass
