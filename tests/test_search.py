import os
from typing import List

import pytest

from core.search import search_answer, retrieve_passages, Passage


def test_search_answer_no_sources(monkeypatch):
    # Force retrieval to return no passages
    def _empty_retrieve(query: str, top_k: int = 6) -> List[Passage]:
        return []

    monkeypatch.setenv("RETRIEVAL_TOP_K", "6")
    monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.25")
    monkeypatch.setattr("core.search.retrieve_passages", _empty_retrieve)

    out = search_answer("Quel est le sens de la vie ?")
    assert isinstance(out, dict)
    assert out["answer"] == "Je ne sais pas"
    assert out["citations"] == []
    assert out["confidence"] == 0.0


def test_search_answer_with_fallback_tfidf(monkeypatch):
    # Ensure no network/DB is used
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("RETRIEVAL_TOP_K", "3")
    monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.0")  # ensure it tries to answer

    # Query chosen to match dummy_data (EvoAgentX is present in titles)
    out = search_answer("Qu'est-ce que EvoAgentX ?")
    assert isinstance(out, dict)
    assert "answer" in out
    assert isinstance(out["citations"], list)
    # Should have at least one citation from dummy_data
    assert len(out["citations"]) >= 1
    assert 0.0 <= out["confidence"] <= 1.0
