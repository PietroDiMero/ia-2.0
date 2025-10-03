"""
Prototype d'IA auto‑évolutive pour répondre à des questions à partir de
documents factices et ajuster son comportement en fonction de l'évaluation.

Usage :
    python main.py

L'utilisateur peut poser des questions interactives. Saisissez "quit" pour
terminer la session.
Les logs seront enregistrés dans logs.json.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


DATA_FILE = Path(__file__).resolve().parent / "dummy_data.json"
LOG_FILE = Path(__file__).resolve().parent / "logs.json"


def load_documents() -> List[Dict[str, str]]:
    """Charge les documents factices à partir du fichier JSON."""
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def tokenize(text: str) -> List[str]:
    """Tokenise le texte en mots minuscules en retirant les caractères non alphanumériques."""
    # Remplace les tirets par des espaces et retire les caractères non alphabet/chiffre
    text = text.lower()
    # Supprime les balises ou crochets comme 【†】 s'il y en a
    text = re.sub(r"【[^】]*】", "", text)
    tokens = re.findall(r"[a-zàâäéèêëïîôöùûüç]+", text)
    return tokens


def build_index(docs: List[Dict[str, str]]) -> Tuple[List[Dict], Dict[str, float]]:
    """
    Construit un index TF-IDF simple pour une liste de documents.

    Retourne une liste de vecteurs (dictionnaires mot→poids TF-IDF) et l'IDF global.
    """
    # Compte des documents contenant chaque terme
    doc_freq: Dict[str, int] = {}
    doc_tokens: List[List[str]] = []
    for doc in docs:
        tokens = tokenize(doc["title"] + " " + doc["content"])
        doc_tokens.append(tokens)
        unique_tokens = set(tokens)
        for token in unique_tokens:
            doc_freq[token] = doc_freq.get(token, 0) + 1

    # Calcul de l'IDF : log(N / df)
    num_docs = len(docs)
    idf: Dict[str, float] = {}
    for token, df in doc_freq.items():
        idf[token] = math.log((num_docs + 1) / (df + 1)) + 1.0

    # Construction des vecteurs TF-IDF pour chaque document
    vectors: List[Dict[str, float]] = []
    for tokens in doc_tokens:
        tf: Dict[str, float] = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        # Normalisation TF (division par longueur)
        length = len(tokens) or 1
        for token in tf:
            tf[token] = tf[token] / length
        # Combine TF et IDF
        vec: Dict[str, float] = {}
        for token, tf_val in tf.items():
            vec[token] = tf_val * idf.get(token, 0.0)
        vectors.append(vec)

    return vectors, idf


def vectorize_query(query: str, idf: Dict[str, float]) -> Dict[str, float]:
    """Transforme une requête en vecteur TF-IDF selon l'IDF global."""
    tokens = tokenize(query)
    tf: Dict[str, float] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    length = len(tokens) or 1
    for t in tf:
        tf[t] = tf[t] / length
    vec: Dict[str, float] = {}
    for token, tf_val in tf.items():
        vec[token] = tf_val * idf.get(token, 0.0)
    return vec


def cosine_similarity(vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
    """Calcule la similarité cosinus entre deux vecteurs creux."""
    # Produit scalaire
    dot = 0.0
    for token, v1 in vec1.items():
        dot += v1 * vec2.get(token, 0.0)
    # Normes
    norm1 = math.sqrt(sum(x * x for x in vec1.values()))
    norm2 = math.sqrt(sum(x * x for x in vec2.values()))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def query_documents(query: str, doc_vecs: List[Dict[str, float]], idf: Dict[str, float], docs: List[Dict[str, str]], k: int = 3, threshold: float = 0.1) -> List[Tuple[float, Dict[str, str]]]:
    """
    Retourne les k documents les plus similaires à la requête, avec un seuil minimal.

    Paramètres :
    - query : texte de la requête
    - doc_vecs : vecteurs TF-IDF des documents
    - idf : dictionnaire IDF global
    - docs : documents originaux
    - k : nombre maximum de résultats
    - threshold : seuil de similarité minimale pour retenir un document
    """
    query_vec = vectorize_query(query, idf)
    scores: List[Tuple[float, int]] = []
    for idx, doc_vec in enumerate(doc_vecs):
        score = cosine_similarity(query_vec, doc_vec)
        scores.append((score, idx))
    # Trier par score décroissant
    scores.sort(reverse=True, key=lambda x: x[0])
    selected: List[Tuple[float, Dict[str, str]]] = []
    for score, idx in scores[:k]:
        if score >= threshold:
            selected.append((score, docs[idx]))
    return selected


def generate_answer(query: str, selected_docs: List[Tuple[float, Dict[str, str]]]) -> Tuple[str, List[str]]:
    """
    Génère une réponse simple à partir des documents sélectionnés.
    Retourne un texte et une liste de sources (URLs).
    """
    if not selected_docs:
        return "Je ne dispose pas de sources pertinentes pour répondre à cette question.", []
    # Concatène les titres et résumés pour composer une réponse
    answer_lines = []
    sources = []
    for score, doc in selected_docs:
        answer_lines.append(f"Dans \"{doc['title']}\", il est expliqué que {doc['content']}")
        sources.append(doc["url"])
    # Limiter la réponse à 2 ou 3 phrases pour plus de lisibilité
    answer_text = "\n".join(answer_lines[:2])
    return answer_text, sources


def load_logs() -> List[Dict]:
    """Charge les logs existants depuis le fichier."""
    if LOG_FILE.exists():
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


def save_logs(logs: List[Dict]) -> None:
    """Écrit les logs au format JSON."""
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)


def main():
    print("==== Prototype IA Auto‑Évolutive ====")
    print("Posez une question (ou tapez 'quit' pour terminer) :")
    docs = load_documents()
    doc_vecs, idf = build_index(docs)
    # Paramètre évolutif : seuil de similarité
    threshold = 0.1
    logs = load_logs()
    while True:
        try:
            query = input("> ")
        except EOFError:
            break
        if not query:
            continue
        if query.strip().lower() in {"quit", "exit"}:
            break
        start_time = time.perf_counter()
        results = query_documents(query, doc_vecs, idf, docs, k=3, threshold=threshold)
        answer, sources = generate_answer(query, results)
        elapsed = time.perf_counter() - start_time
        # Évaluation simple : succès si au moins 2 sources distinctes
        success = len(sources) >= 2
        # Ajustement du seuil : diminuer si succès, augmenter sinon (limites 0.05 - 0.5)
        if success:
            threshold = max(0.05, threshold - 0.02)
        else:
            threshold = min(0.5, threshold + 0.02)
        # Affiche la réponse
        print("Réponse :")
        print(answer)
        if sources:
            print("Sources :", ", ".join(sources))
        else:
            print("Sources : aucune")
        print(f"Temps de réponse : {elapsed:.3f} s | Seuil actuel : {threshold:.2f}")
        # Enregistre le log
        logs.append(
            {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "question": query,
                "answer": answer,
                "sources": sources,
                "success": success,
                "response_time": elapsed,
                "threshold": threshold,
            }
        )
        save_logs(logs)
    print("Session terminée. Merci d'avoir utilisé le prototype IA auto‑évolutive !")


if __name__ == "__main__":
    main()