from __future__ import annotations

"""Centralised configuration helpers for the backend.

This keeps environment lookups in one place so the rest of the codebase
imports from here instead of scattering os.getenv calls everywhere.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess


def _git_commit() -> str | None:
    try:
        out = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
        if out:
            return out
    except Exception:
        return None
    return None


@dataclass(slots=True)
class Settings:
    env: str = os.getenv("APP_ENV", "dev")
    version: str = os.getenv("APP_VERSION", "") or (_git_commit() or "dev")
    github_repo: str | None = os.getenv("GITHUB_REPOSITORY")
    github_token: str | None = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    eval_min_overall: float = float(os.getenv("EVAL_MIN_OVERALL_SCORE", "0.75"))
    events_api_token: str | None = os.getenv("EVENTS_API_TOKEN")
    allow_origins: list[str] = (
        os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
        .split(",")
    )


settings = Settings()

__all__ = ["settings"]
