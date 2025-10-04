"""Minimal indexing module.

Provides a placeholder `index_unembedded` function so the FastAPI app and
Celery tasks can run even if no real embedding service is configured yet.

Behaviour:
  - Select up to `batch_size` documents whose embedding is NULL or `indexed` is FALSE.
  - Assign a zero vector (length 3072) as a dummy embedding and mark them indexed.
  - Return the number of documents updated.

You can later replace the zero vector with real embeddings (OpenAI, local model, etc.).
"""

from __future__ import annotations

import os
from typing import List

from .db import connect, log_event  # type: ignore

EMBED_DIM = 3072
_ZERO_VECTOR_LITERAL = "[" + ",".join("0" for _ in range(EMBED_DIM)) + "]"


def index_unembedded(batch_size: int = 25) -> int:
    """Index (embed) the next batch of unembedded documents.

    Returns the number of documents updated. On any failure returns 0.
    """
    try:
        with connect() as conn:  # type: ignore
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM documents WHERE (embedding IS NULL OR indexed = FALSE) ORDER BY id ASC LIMIT %s;",
                    (batch_size,),
                )
                rows = cur.fetchall()
                if not rows:
                    return 0
                updated = 0
                for (doc_id,) in rows:
                    cur.execute(
                        "UPDATE documents SET embedding = %s::vector, indexed = TRUE WHERE id = %s;",
                        (_ZERO_VECTOR_LITERAL, doc_id),
                    )
                    updated += cur.rowcount or 0
            conn.commit()
        if updated:
            try:
                verbose = os.getenv("EVENTS_VERBOSE", "0").lower() in ("1", "true", "yes", "debug")
                log_event("index", "Indexed batch", meta={"updated": updated})  # type: ignore
                if verbose:
                    log_event("index", "Dummy embeddings used", meta={"dim": EMBED_DIM})  # type: ignore
            except Exception:
                pass
        return updated
    except Exception:
        return 0

__all__ = ["index_unembedded"]
