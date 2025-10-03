from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Optional third-party deps; code should gracefully degrade during tests
try:  # OpenAI Python SDK v1.x
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover - optional
    OpenAI = None  # type: ignore

try:  # psycopg v3 binary for simple local usage
    import psycopg  # type: ignore
except Exception:  # pragma: no cover - optional
    psycopg = None  # type: ignore


DATA_FILE = Path(__file__).resolve().parent.parent / "dummy_data.json"


@dataclass
class Passage:
    title: str
    url: str
    content: str
    score: float


def _get_env(name: str, default: Optional[str] = None) -> str:
    val = os.getenv(name)
    return val if val is not None else (default or "")


def _embed_query(query: str) -> Optional[List[float]]:
    """Return the embedding vector for the query using OpenAI, or None if unavailable."""
    api_key = _get_env("OPENAI_API_KEY")
    model = _get_env("EMBEDDING_MODEL", "text-embedding-3-small")
    if not api_key or OpenAI is None:
        return None
    try:  # pragma: no cover - network path not covered by unit tests
        client = OpenAI(api_key=api_key)
        resp = client.embeddings.create(model=model, input=query)
        return list(resp.data[0].embedding)
    except Exception:
        return None


def _pgvector_search(query: str, top_k: int) -> Optional[List[Passage]]:
    """Try to retrieve top_k passages from Postgres/pgvector using cosine similarity.

    Returns None if the database or embedding service isn't available.
    """
    if psycopg is None:
        return None
    db_url = _get_env("DATABASE_URL")
    if not db_url:
        return None
    embedding = _embed_query(query)
    if embedding is None:
        return None
    # Build vector literal for pgvector (e.g., '[1,2,3]')
    vec_literal = "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"
    sql = (
        "WITH q AS (SELECT %s::vector AS emb) "
        "SELECT d.title, d.url, d.content, (1 - (d.embedding <=> q.emb)) AS score "
        "FROM documents d, q "
        "ORDER BY d.embedding <=> q.emb ASC "
        "LIMIT %s"
    )
    try:  # pragma: no cover - requires DB
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (vec_literal, top_k))
                rows = cur.fetchall()
        passages: List[Passage] = []
        for title, url, content, score in rows:
            passages.append(Passage(title=title, url=url, content=content, score=float(score)))
        return passages
    except Exception:
        return None


# -------- Fallback TF-IDF retrieval over local dummy_data.json ---------

_tfidf_index: Optional[Tuple[List[Dict[str, float]], Dict[str, float], List[Dict[str, str]]]] = None


def _tokenize(text: str) -> List[str]:
    text = text.lower()
    text = re.sub(r"【[^】]*】", "", text)
    return re.findall(r"[a-zàâäéèêëïîôöùûüç]+", text)


def _build_index() -> Tuple[List[Dict[str, float]], Dict[str, float], List[Dict[str, str]]]:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        docs = json.load(f)
    # doc frequencies
    df: Dict[str, int] = {}
    tokenized: List[List[str]] = []
    for d in docs:
        toks = _tokenize((d.get("title") or "") + " " + (d.get("content") or ""))
        tokenized.append(toks)
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    n = max(1, len(docs))
    idf: Dict[str, float] = {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}
    # tf-idf vectors
    vectors: List[Dict[str, float]] = []
    for toks in tokenized:
        tf: Dict[str, float] = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        L = max(1, len(toks))
        for t in tf:
            tf[t] /= L
        vec: Dict[str, float] = {t: tf[t] * idf.get(t, 0.0) for t in tf}
        vectors.append(vec)
    return vectors, idf, docs


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    dot = 0.0
    for k, v in a.items():
        dot += v * b.get(k, 0.0)
    na = math.sqrt(sum(x * x for x in a.values()))
    nb = math.sqrt(sum(x * x for x in b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _vectorize_query(q: str, idf: Dict[str, float]) -> Dict[str, float]:
    toks = _tokenize(q)
    tf: Dict[str, float] = {}
    for t in toks:
        tf[t] = tf.get(t, 0) + 1
    L = max(1, len(toks))
    for t in tf:
        tf[t] /= L
    return {t: tf[t] * idf.get(t, 0.0) for t in tf}


def _fallback_search(query: str, top_k: int) -> List[Passage]:
    global _tfidf_index
    if _tfidf_index is None:
        _tfidf_index = _build_index()
    vectors, idf, docs = _tfidf_index
    qv = _vectorize_query(query, idf)
    scored: List[Tuple[float, int]] = []
    for i, dv in enumerate(vectors):
        scored.append((_cosine(qv, dv), i))
    scored.sort(key=lambda x: x[0], reverse=True)
    passages: List[Passage] = []
    for score, idx in scored[:top_k]:
        if score <= 0.0:
            continue
        d = docs[idx]
        passages.append(
            Passage(title=d.get("title", "Sans titre"), url=d.get("url", ""), content=d.get("content", ""), score=float(score))
        )
    return passages


def retrieve_passages(query: str, top_k: int = 6) -> List[Passage]:
    """Public retrieval function. Prefers pgvector, falls back to local TF-IDF."""
    pg = _pgvector_search(query, top_k)
    if pg is not None:
        return pg
    return _fallback_search(query, top_k)


def _build_prompt(query: str, passages: List[Passage]) -> str:
    snippets = []
    for p in passages:
        snippets.append(f"- Titre: {p.title}\n  URL: {p.url}\n  Extrait: {p.content}")
    sources_block = "\n".join(snippets) if snippets else "(aucune)"
    instr = (
        "Réponds en citant [titre](url) après chaque paragraphe utilisé. "
        "Si les sources ne suffisent pas, dis 'Je ne sais pas' et liste juste les sources."
    )
    return (
        f"Question: {query}\n\n"
        f"Voici des passages de sources candidates:\n{sources_block}\n\n"
        f"Consignes: {instr}\n"
        f"Réponds en français, de manière concise et factuelle."
    )


def _call_llm(prompt: str) -> Optional[str]:
    model = _get_env("OPENAI_MODEL", "gpt-4o-mini")
    temp = float(_get_env("LLM_TEMPERATURE", "0.2"))
    api_key = _get_env("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return None
    try:  # pragma: no cover - network path not covered by unit tests
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            temperature=temp,
            messages=[
                {"role": "system", "content": "Tu es un assistant qui répond uniquement sur la base des sources fournies."},
                {"role": "user", "content": prompt},
            ],
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return None


def _extract_citations(answer: str) -> List[Dict[str, str]]:
    cites: List[Dict[str, str]] = []
    seen = set()
    for title, url in re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", answer or ""):
        key = (title.strip(), url.strip())
        if key in seen:
            continue
        seen.add(key)
        cites.append({"title": title.strip(), "url": url.strip()})
    return cites


def search_answer(query: str) -> Dict[str, Any]:
    """
    - Récupère top_k=6 passages via pgvector (cosine), fallback TF-IDF si indispo.
    - Construit un prompt imposant les citations [titre](url) après chaque paragraphe, sinon "Je ne sais pas" + sources.
    - Appelle le LLM (modèle et température via env) si des sources pertinentes existent.
    - Renvoie { answer, citations: [{title,url}], confidence }.
    """
    top_k = int(_get_env("RETRIEVAL_TOP_K", "6") or 6)
    threshold = float(_get_env("CONFIDENCE_THRESHOLD", "0.25") or 0.25)

    passages = retrieve_passages(query, top_k=top_k)
    if not passages:
        return {"answer": "Je ne sais pas", "citations": [], "confidence": 0.0}

    # Confidence from mean of top scores (clamped 0..1)
    mean_score = sum(p.score for p in passages) / max(1, len(passages))
    confidence = max(0.0, min(1.0, float(mean_score)))

    # If below threshold, short-circuit with "Je ne sais pas" and list only sources
    if confidence < threshold:
        cites = [{"title": p.title, "url": p.url} for p in passages]
        return {"answer": "Je ne sais pas", "citations": cites, "confidence": round(confidence, 3)}

    prompt = _build_prompt(query, passages)
    answer = _call_llm(prompt)

    if not answer:
        # Deterministic fallback: build a minimal answer citing each passage
        paras: List[str] = []
        for p in passages[:3]:
            # Take a short snippet (first sentence) if available
            snippet = (p.content or "").split(". ")[0].strip()
            if not snippet:
                snippet = p.content.strip()[:200]
            paras.append(f"{snippet}. [{p.title}]({p.url})")
        answer = "\n\n".join(paras) if paras else "Je ne sais pas"

    citations = _extract_citations(answer)
    # If the model forgot to cite but we have sources, attach the top sources as citations
    if not citations:
        citations = [{"title": p.title, "url": p.url} for p in passages]

    return {"answer": answer, "citations": citations, "confidence": round(confidence, 3)}
