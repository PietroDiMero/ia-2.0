"""
Crawler minimal pour apprendre d'Internet.

Fonctionnalités:
- Récupère une page web via HTTP GET.
- Extrait du texte lisible (titre, paragraphes).
- Ajoute un document dans dummy_data.json si contenu non vide.

Remarques:
- À des fins de démonstration seulement; ne gère pas robots.txt ni le crawling
  massif. Évitez de lancer sur de nombreux sites. Ajoutez un user-agent
  explicite et des limites de fréquence en production.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "dummy_data.json"


@dataclass
class CrawlResult:
    url: str
    title: str
    content: str
    added: bool


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_and_extract(url: str, timeout: int = 10) -> CrawlResult:
    headers = {"User-Agent": "AutoEvolveBot/0.1 (+https://example.local)"}
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else url
    # Concaténer paragraphes
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    content = clean_text(" ".join(paragraphs))[:1500]
    added = False
    if content:
        # Charger existant
        docs: List[Dict[str, str]] = []
        if DATA_FILE.exists():
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                docs = json.load(f)
        # Éviter doublons exacts d'URL
        if not any(d.get("url") == url for d in docs):
            docs.append({"title": title, "content": content, "url": url})
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(docs, f, ensure_ascii=False, indent=2)
            added = True
    return CrawlResult(url=url, title=title, content=content, added=added)
