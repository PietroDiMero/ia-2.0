from __future__ import annotations

import json
from pathlib import Path

from evaluator.evaluate import evaluate_index


def _fake_backend_ok(q: str):
    # returns perfect answers and sources aligned with sample.json
    if "capitale" in q.lower():
        return {
            "answer": "Paris",
            "sources": [
                "https://fr.wikipedia.org/wiki/Paris",
                "https://www.britannica.com/place/Paris",
            ],
        }
    if "openai" in q.lower():
        return {
            "answer": "2015",
            "sources": [
                "https://openai.com/",
                "https://en.wikipedia.org/wiki/OpenAI",
            ],
        }
    return {
        "answer": "Retrieval-Augmented Generation",
        "sources": [
            "https://arxiv.org/abs/2005.11401",
            "https://www.pinecone.io/learn/retrieval-augmented-generation/",
        ],
    }


def _fake_backend_poor(q: str):
    return {
        "answer": "",
        "sources": [],
    }


def test_evaluate_index_ok(tmp_path: Path):
    # Use the packaged sample testset
    report = evaluate_index(42, backend_search=_fake_backend_ok)
    assert report["version_id"] == 42
    assert 0.0 <= report["overall_score"] <= 1.0
    assert report["eligible_for_activation"] in (True, False)
    # With perfect backend, score should be high
    assert report["overall_score"] >= 0.75


def test_evaluate_index_poor():
    report = evaluate_index(7, backend_search=_fake_backend_poor)
    assert 0.0 <= report["overall_score"] <= 1.0
    assert report["eligible_for_activation"] is False
