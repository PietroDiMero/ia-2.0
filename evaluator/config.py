from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Optional


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


@dataclass(frozen=True)
class EvalSettings:
    WEIGHT_EXACT: float = 0.25
    WEIGHT_SEMANTIC_F1: float = 0.35
    WEIGHT_GROUNDEDNESS: float = 0.25
    WEIGHT_FRESHNESS: float = 0.15
    MIN_OVERALL_SCORE: float = 0.75
    BACKEND_URL: Optional[str] = None
    DATABASE_URL: Optional[str] = None

    def as_weights(self) -> Dict[str, float]:
        return {
            "exact": float(self.WEIGHT_EXACT),
            "semantic_f1": float(self.WEIGHT_SEMANTIC_F1),
            "groundedness": float(self.WEIGHT_GROUNDEDNESS),
            "freshness": float(self.WEIGHT_FRESHNESS),
        }


@lru_cache(maxsize=1)
def get_eval_settings() -> EvalSettings:
    return EvalSettings(
        WEIGHT_EXACT=_get_float("EVAL_WEIGHT_EXACT", 0.25),
        WEIGHT_SEMANTIC_F1=_get_float("EVAL_WEIGHT_SEMANTIC_F1", 0.35),
        WEIGHT_GROUNDEDNESS=_get_float("EVAL_WEIGHT_GROUNDEDNESS", 0.25),
        WEIGHT_FRESHNESS=_get_float("EVAL_WEIGHT_FRESHNESS", 0.15),
        MIN_OVERALL_SCORE=_get_float("EVAL_MIN_OVERALL_SCORE", 0.75),
        BACKEND_URL=os.getenv("EVAL_BACKEND_URL"),
        DATABASE_URL=os.getenv("EVAL_DATABASE_URL"),
    )

