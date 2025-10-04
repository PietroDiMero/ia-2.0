"""Minimal crawler stub.

This file was intentionally simplified to unblock FastAPI startup.
Replace with real crawling & discovery logic later.
"""
from __future__ import annotations

import random
from typing import List, Optional


def crawl_sources(limit: int = 10) -> int:
    """Pretend crawl returning a small random number."""
    if limit <= 0:
        return 0
    return random.randint(0, min(3, limit))


def discover_new_sources(
    queries: Optional[List[str]] = None,
    per_query: int = 5,
    max_new: int = 25,
) -> int:
    """Pretend discovery based on number of queries."""
    if not queries:
        return 0
    potential = min(len(queries) * per_query, max_new)
    return random.randint(0, potential) if potential > 0 else 0


__all__ = ["crawl_sources", "discover_new_sources"]
