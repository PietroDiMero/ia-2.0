from __future__ import annotations

from fastapi import APIRouter

# Clean minimal placeholder; real search endpoints can be added later.
router = APIRouter(prefix="/search", tags=["search"])


@router.get("/ping")
async def search_ping():
    return {"status": "ok", "scope": "search"}
