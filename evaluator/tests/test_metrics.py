from __future__ import annotations

from datetime import datetime, timedelta, timezone

from evaluator.metrics import exact_match, semantic_f1, groundedness, freshness


def test_exact_match():
    assert exact_match("Paris", "paris") == 1.0
    assert exact_match("Paris ", "Paris") == 1.0
    assert exact_match("Lyon", "Paris") == 0.0


def test_semantic_f1_basic():
    a = "Retrieval Augmented Generation"
    b = "retrieval-augmented generation"
    c = "completely unrelated text"
    assert semantic_f1(a, b) > 0.8
    assert semantic_f1(a, c) < 0.3


def test_groundedness():
    P = ["https://example.com/A/", "https://x.com/b"]
    G = ["https://example.com/a", "https://y.com/c"]
    prec, rec, f1 = groundedness(P, G)
    assert 0.0 <= prec <= 1.0
    assert 0.0 <= rec <= 1.0
    assert 0.0 <= f1 <= 1.0
    assert f1 > 0.0


def test_freshness():
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=10)
    old = now - timedelta(days=500)
    s_recent, d_recent = freshness([recent])
    s_old, d_old = freshness([old])
    assert s_recent > s_old
    assert d_recent < d_old
