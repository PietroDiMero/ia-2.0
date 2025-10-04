from __future__ import annotations

import os
from celery import Celery

from crawler.run import crawl_sources, discover_new_sources
from .indexer import index_unembedded
from .db import log_event, connect
from .evolve import seed_from_docs
import subprocess
import json
import os as _os
from datetime import datetime
from pathlib import Path
from typing import Any


def _get_env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v is not None else default


redis_url = _get_env("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("auto_evolve", broker=redis_url, backend=redis_url)


@celery_app.task
def task_crawl_once(limit: int = 10) -> int:
    log_event("crawl", "Periodic crawl start", meta={"limit": limit})
    n = crawl_sources(limit=limit)
    log_event("crawl", "Periodic crawl done", meta={"inserted": n})
    return n


@celery_app.task
def task_index_once(batch_size: int = 10) -> int:
    log_event("index", "Periodic index start", meta={"batch_size": batch_size})
    n = index_unembedded(batch_size=batch_size)
    log_event("index", "Periodic index done", meta={"indexed": n})
    # Non-blocking seed of evolve context if enabled via env
    try:
        if os.getenv("EVOLVE_SEED_AFTER_INDEX", "1") in ("1", "true", "True"):
            seed_from_docs(limit=200)
    except Exception:
        pass
    return n


@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):  # type: ignore
    # Every 5 minutes, discover, crawl and then index
    sender.add_periodic_task(300.0, celery_app.signature("backend.app.tasks.task_discover_once"), name="discover every 5m")
    sender.add_periodic_task(300.0, task_crawl_once.s(10), name="crawl every 5m")
    sender.add_periodic_task(300.0, task_index_once.s(10), name="index every 5m")
    # Daily evaluator run at 03:30 UTC (configurable via env)
    try:
        eval_schedule = float(_os.getenv("EVAL_PERIOD_SECONDS", str(24 * 3600)))
        sender.add_periodic_task(eval_schedule, celery_app.signature("backend.app.tasks.task_evaluate_and_record"), name="evaluate daily")
    except Exception:
        pass


@celery_app.task(name="backend.app.tasks.task_discover_once")
def task_discover_once(per_query: int = 5, max_new: int = 25, queries: list[str] | None = None) -> int:
    # Load persisted DISCOVERY_QUERIES if not explicitly provided
    if queries is None:
        try:
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT value FROM settings WHERE key='DISCOVERY_QUERIES';")
                    row = cur.fetchone()
                    if row and isinstance(row[0], dict):
                        arr = row[0].get("queries")
                        if isinstance(arr, list) and arr:
                            queries = [str(x) for x in arr if str(x).strip()]
        except Exception:
            pass
    log_event("discover", "Periodic discover start", meta={"per_query": per_query, "max_new": max_new, "has_queries": bool(queries)})
    n = discover_new_sources(queries=queries, per_query=per_query, max_new=max_new)
    log_event("discover", "Periodic discover done", meta={"new_sources": n})
    return n


@celery_app.task(name="backend.app.tasks.task_run_once")
def task_run_once(per_query: int = 5, max_new: int = 25, crawl_limit: int = 50, index_batch: int = 50) -> dict:
    """Run discovery, then crawl, then index in the background and return a summary dict."""
    try:
        discovered = 0
        try:
            discovered = discover_new_sources(per_query=per_query, max_new=max_new)
        except Exception:
            discovered = 0
        log_event("discover", "Run once discover", meta={"new_sources": discovered})
        inserted = 0
        indexed = 0
        try:
            inserted = crawl_sources(limit=crawl_limit)
        except Exception:
            inserted = 0
        log_event("crawl", "Run once crawl", meta={"inserted": inserted})
        try:
            indexed = index_unembedded(batch_size=index_batch)
        except Exception:
            indexed = 0
        log_event("index", "Run once index", meta={"indexed": indexed})
        try:
            if os.getenv("EVOLVE_SEED_AFTER_INDEX", "1") in ("1", "true", "True"):
                seed_from_docs(limit=200)
        except Exception:
            pass
        return {
            "status": "ok",
            "discovered": int(discovered),
            "inserted": int(inserted),
            "indexed": int(indexed),
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "discovered": 0, "inserted": 0, "indexed": 0}


@celery_app.task(name="backend.app.tasks.task_evaluate_and_record")
def task_evaluate_and_record(version_id: int = 1, testset: str | None = None) -> dict:
    """Run evaluator CLI and record its report into ci_history. Uses evaluator/evaluate.py --version-id <id>"""
    try:
        log_event("evolve", "Evaluator run start", meta={"version_id": version_id})
        cmd = ["python", "evaluator/evaluate.py", "--version-id", str(version_id)]
        if testset:
            cmd += ["--testset", testset]
        # Run evaluator and capture report path (it writes evaluator/reports/index_<id>.json)
        subprocess.check_call(cmd)
        report_path = Path("evaluator/reports") / f"index_{version_id}.json"
        if report_path.exists():
            with report_path.open("r", encoding="utf-8") as f:
                report = json.load(f)
            agg = report.get("aggregates", {})
            overall = report.get("overall_score") or report.get("overall_score")
            payload = {
                "overall": float(report.get("overall_score", 0.0)),
                "exact": float(agg.get("exact", 0.0)),
                "groundedness": float(agg.get("groundedness", 0.0)),
                "semantic_f1": float(report.get("aggregates", {}).get("semantic_f1", 0.0)),
                "freshness": float(agg.get("freshness", 0.0)),
                "avg_freshness_days": float(agg.get("avg_freshness_days")) if agg.get("avg_freshness_days") is not None else None,
                "meta": {"version_id": version_id, "ts": datetime.utcnow().isoformat()},
            }
            # Try direct DB insert first
            try:
                from psycopg import connect as _pg_connect
                with _pg_connect(_os.getenv("DATABASE_URL")) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO ci_history(overall, exact, groundedness, semantic_f1, freshness, avg_freshness_days, meta) VALUES(%s,%s,%s,%s,%s,%s,%s);",
                            (
                                payload["overall"],
                                payload["exact"],
                                payload["groundedness"],
                                payload["semantic_f1"],
                                payload["freshness"],
                                payload["avg_freshness_days"],
                                json.dumps(payload["meta"]),
                            ),
                        )
                    conn.commit()
            except Exception:
                # Fallback to calling the REST endpoint
                try:
                    import requests
                    requests.post((_os.getenv("EVAL_BACKEND_URL") or _os.getenv("BACKEND_URL") or "http://localhost:8000") + "/metrics/record", json=payload, timeout=10)
                except Exception:
                    pass
            log_event("evolve", "Evaluator run recorded", meta={"version_id": version_id})
            return {"status": "ok", "payload": payload}
        else:
            log_event("evolve", "Evaluator report not found", level="error", meta={"path": str(report_path)})
            return {"status": "error", "error": "report not found"}
    except Exception as e:
        log_event("evolve", f"Evaluator run failed: {e}", level="error")
        return {"status": "error", "error": str(e)}


@celery_app.task(name="backend.app.tasks.task_simple_evaluate")
def task_simple_evaluate(questions: list[str] | None = None) -> dict[str, Any]:
    """Async version of /evaluate/run: reuses search_answer logic for provided questions."""
    from core.search import search_answer
    from .main import _evaluate_exact, _evaluate_grounded  # type: ignore
    qs = questions or [
        "Qu'est-ce qu'un agent auto-évolutif ?",
        "Comment fonctionne l'index actuel ?",
        "Quel est l'objectif du système ?",
    ]
    results: list[dict[str, Any]] = []
    exact_scores: list[float] = []
    grounded_scores: list[float] = []
    for q in qs:
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
        except Exception as e:
            results.append({"question": q, "error": str(e), "exact": 0.0, "grounded": 0.0})
    overall_exact = sum(exact_scores) / max(1, len(exact_scores))
    overall_grounded = sum(grounded_scores) / max(1, len(grounded_scores))
    overall = round((overall_exact * 0.6 + overall_grounded * 0.4), 3)
    payload = {
        "status": "ok",
        "overall": overall,
        "exact": round(overall_exact, 3),
        "groundedness": round(overall_grounded, 3),
        "results": results,
    }
    # Persist like sync version (no freshness heuristic here yet)
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO ci_history(overall, exact, groundedness, semantic_f1, freshness, avg_freshness_days, meta) VALUES(%s,%s,%s,%s,%s,%s,%s);",
                    (overall, overall_exact, overall_grounded, None, None, None, json.dumps({"questions": qs})),
                )
                cur.execute(
                    "INSERT INTO ci_status(id, overall, exact, groundedness, freshness, updated_at) VALUES(1,%s,%s,%s,%s,NOW()) ON CONFLICT (id) DO UPDATE SET overall=EXCLUDED.overall, exact=EXCLUDED.exact, groundedness=EXCLUDED.groundedness, freshness=EXCLUDED.freshness, updated_at=NOW();",
                    (overall, overall_exact, overall_grounded, None),
                )
            conn.commit()
        log_event("evolve", "Async evaluation enregistrée", meta={"overall": overall})
    except Exception:
        pass
    return payload
