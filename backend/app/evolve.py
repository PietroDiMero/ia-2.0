from __future__ import annotations

from .db import log_event


def seed_from_docs(limit: int = 100) -> int:
    """Placeholder evolve seeding: simply logs an event and returns 0.

    Real implementation would update embeddings / evaluation context.
    """
    try:
        log_event("evolve", "seed_from_docs placeholder", meta={"limit": limit})
    except Exception:
        pass
    return 0


__all__ = ["seed_from_docs"]
