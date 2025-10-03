from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Iterable, List, Tuple


_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(_normalize_text(text))


def exact_match(pred: str, gold: str) -> float:
    return 1.0 if _normalize_text(pred) == _normalize_text(gold) else 0.0


def _bow_vector(tokens: Iterable[str]) -> Counter:
    # Simple BOW with hashing to dampen vocabulary variance
    vec: Counter = Counter()
    for t in tokens:
        # map token into a small-ish space to stabilize on Windows w/o numpy
        bucket = hash(t) % 2048
        vec[bucket] += 1
    return vec


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = 0.0
    for k, v in a.items():
        if k in b:
            dot += v * b[k]
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(dot / (na * nb))


def semantic_f1(pred: str, gold: str) -> float:
    # We approximate a semantic F1 by using cosine similarity of hashed BOW
    pt = _tokenize(pred)
    gt = _tokenize(gold)
    a = _bow_vector(pt)
    b = _bow_vector(gt)
    return _cosine(a, b)


def _norm_url(u: str) -> str:
    u = u.strip().lower()
    u = u.rstrip("/")
    return u


def groundedness(pred_sources: Iterable[str], gold_sources: Iterable[str]) -> Tuple[float, float, float]:
    P = {_norm_url(u) for u in pred_sources}
    G = {_norm_url(u) for u in gold_sources}
    if not P and not G:
        return (1.0, 1.0, 1.0)
    if not P:
        return (0.0, 0.0, 0.0)
    if not G:
        return (0.0, 0.0, 0.0)
    tp = len(P & G)
    prec = tp / len(P) if P else 0.0
    rec = tp / len(G) if G else 0.0
    if prec + rec == 0.0:
        f1 = 0.0
    else:
        f1 = 2 * prec * rec / (prec + rec)
    return (prec, rec, f1)


def freshness(cited_dates: Iterable[datetime]) -> Tuple[float, float]:
    # Returns (freshness_score in [0,1], avg_age_days)
    dates = [d for d in cited_dates if isinstance(d, datetime)]
    if not dates:
        return (0.0, float("inf"))
    now = datetime.now(timezone.utc)
    ages_days: List[float] = []
    for d in dates:
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        delta = now - d
        ages_days.append(delta.total_seconds() / 86400.0)
    avg_days = sum(ages_days) / len(ages_days)
    # Score linearly decays across a year; clamp to [0,1]
    score = max(0.0, 1.0 - (avg_days / 365.0))
    return (float(score), float(avg_days))
