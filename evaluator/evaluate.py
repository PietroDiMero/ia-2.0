from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import requests

from .config import get_eval_settings
from .metrics import exact_match, semantic_f1, groundedness, freshness


SearchFn = Callable[[str], Dict[str, Any]]


def _default_backend_search(q: str) -> Dict[str, Any]:
    st = get_eval_settings()
    if not st.BACKEND_URL:
        raise RuntimeError("BACKEND_URL is not configured; provide a backend_search function instead")
    url = st.BACKEND_URL.rstrip("/") + "/search"
    r = requests.get(url, params={"q": q, "k": 5}, timeout=20)
    r.raise_for_status()
    return r.json()


def _load_testset(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _collect_freshness_dates(sources: Iterable[str]) -> List[datetime]:
    # Placeholder: in a real system, we'd fetch publish dates from DB.
    # For now, we treat missing dates as no contribution (freshness 0).
    # If a source embeds an ISO date in query or path, parse it.
    dates: List[datetime] = []
    for s in sources:
        # naive parse YYYY (if present) as Jan 1st of that year
        import re

        m = re.search(r"(20\d{2}|19\d{2})", s)
        if m:
            try:
                y = int(m.group(1))
                dates.append(datetime(y, 1, 1))
            except Exception:
                pass
    return dates


@dataclass
class ItemResult:
    question: str
    expected_answer: str
    expected_sources: List[str]
    answer: str
    sources: List[str]
    metrics: Dict[str, float]


def evaluate_index(version_id: int, testset_path: Optional[str] = None, backend_search: Optional[SearchFn] = None) -> Dict[str, Any]:
    st = get_eval_settings()
    weights = st.as_weights()
    if backend_search is None:
        backend_search = _default_backend_search

    # Load cases
    if testset_path is None:
        testset_path = str(Path(__file__).parent / "testsets" / "sample.json")
    cases = _load_testset(Path(testset_path))

    item_results: List[ItemResult] = []
    agg = {"exact": 0.0, "semantic_f1": 0.0, "groundedness": 0.0, "freshness": 0.0}
    freshness_days: List[float] = []

    for case in cases:
        q = case["question"]
        gold = case["expected_answer"]
        gold_sources = case.get("expected_sources", [])
        res = backend_search(q)
        pred = str(res.get("answer", ""))
        pred_sources = [s if isinstance(s, str) else (s[0] if isinstance(s, (list, tuple)) and s else "") for s in res.get("sources", [])]

        em = exact_match(pred, gold)
        sf1 = semantic_f1(pred, gold)
        _, _, grd_f1 = groundedness(pred_sources, gold_sources)
        f_score, avg_days = freshness(_collect_freshness_dates(pred_sources))

        item_results.append(
            ItemResult(
                question=q,
                expected_answer=gold,
                expected_sources=gold_sources,
                answer=pred,
                sources=pred_sources,
                metrics={
                    "exact": em,
                    "semantic_f1": sf1,
                    "groundedness": grd_f1,
                    "freshness": f_score,
                },
            )
        )
        agg["exact"] += em
        agg["semantic_f1"] += sf1
        agg["groundedness"] += grd_f1
        agg["freshness"] += f_score
        if avg_days != float("inf"):
            freshness_days.append(avg_days)

    n = max(1, len(item_results))
    for k in list(agg.keys()):
        agg[k] = agg[k] / n

    # Normalize weights to sum 1
    sw = sum(weights.values()) or 1.0
    weights = {k: v / sw for k, v in weights.items()}

    overall = (
        weights["exact"] * agg["exact"]
        + weights["semantic_f1"] * agg["semantic_f1"]
        + weights["groundedness"] * agg["groundedness"]
        + weights["freshness"] * agg["freshness"]
    )

    avg_fresh_days = sum(freshness_days) / len(freshness_days) if freshness_days else None
    eligible = overall >= float(st.MIN_OVERALL_SCORE)

    report = {
        "version_id": int(version_id),
        "items": [
            {
                "question": it.question,
                "expected_answer": it.expected_answer,
                "expected_sources": it.expected_sources,
                "answer": it.answer,
                "sources": it.sources,
                "metrics": it.metrics,
            }
            for it in item_results
        ],
        "aggregates": {
            "exact": agg["exact"],
            "semantic_f1": agg["semantic_f1"],
            "groundedness": agg["groundedness"],
            "freshness": agg["freshness"],
            "avg_freshness_days": avg_fresh_days,
        },
        "weights": weights,
        "overall_score": overall,
        "eligible_for_activation": eligible,
    }

    out_dir = Path(__file__).parent / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"index_{version_id}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Optional: mark eligibility in DB if configured
    _maybe_mark_db(version_id, eligible)

    return report


def _maybe_mark_db(version_id: int, eligible: bool) -> None:
    from urllib.parse import urlparse

    st = get_eval_settings()
    if not st.DATABASE_URL:
        return
    try:
        import psycopg
        with psycopg.connect(st.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DO $$
                    BEGIN
                      IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'index_versions' AND column_name = 'eligible_for_activation'
                      ) THEN
                        UPDATE index_versions
                        SET eligible_for_activation = %s,
                            updated_at = NOW()
                        WHERE id = %s;
                      END IF;
                    END;
                    $$;
                    """,
                    (eligible, version_id),
                )
                conn.commit()
    except Exception:
        # Best-effort; ignore if DB or table not available
        return


def main():
    parser = argparse.ArgumentParser(description="Evaluate an index version and generate JSON report")
    parser.add_argument("--version-id", type=int, required=True)
    parser.add_argument("--testset", type=str, default=None)
    args = parser.parse_args()
    evaluate_index(args.version_id, testset_path=args.testset)


if __name__ == "__main__":
    main()
