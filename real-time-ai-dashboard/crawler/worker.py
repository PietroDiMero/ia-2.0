from __future__ import annotations

import datetime as dt
import json
import os
import time
from dataclasses import dataclass
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from celery import Celery


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8080")
ALLOWED_SOURCES = os.getenv("ALLOWLIST", "/app/crawler/allowlist.yaml")

celery_app = Celery("crawler", broker=REDIS_URL, backend=REDIS_URL)
# Schedule crawl every 5 minutes
celery_app.conf.beat_schedule = {
    "crawl-every-5-min": {
        "task": "crawl_once",
        "schedule": 300.0,
    }
}


def load_allowlist() -> List[dict]:
    try:
        import yaml  # type: ignore

        with open(ALLOWED_SOURCES, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or []
    except Exception:
        return []


def extract_text_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # remove script/style
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return " ".join(text.split())


@celery_app.task(name="crawl_once")
def crawl_once():
    sources = load_allowlist()
    for src in sources:
        url = src.get("url")
        typ = src.get("type", "html")
        try:
            if typ == "rss":
                # naive: fetch RSS and then items
                import feedparser  # type: ignore

                feed = feedparser.parse(url)
                for entry in feed.entries[:10]:
                    link = entry.link
                    r = requests.get(link, timeout=15)
                    content = extract_text_html(r.text)
                    _send_doc(title=entry.title, url=link, content=content)
            else:  # html/api
                r = requests.get(url, timeout=20)
                content = extract_text_html(r.text)
                title = src.get("title") or url
                _send_doc(title=title, url=url, content=content)
        except Exception as e:
            print(json.dumps({"level": "error", "msg": "crawl_failed", "url": url, "error": str(e)}))
    return {"status": "ok"}


def _send_doc(title: str, url: str, content: str):
    try:
        payload = {"title": title, "url": url, "content": content}
        requests.post(f"{BACKEND_URL}/ingest", json=payload, timeout=20)
        print(json.dumps({"level": "info", "msg": "doc_sent", "title": title, "url": url}))
    except Exception as e:
        print(json.dumps({"level": "error", "msg": "send_failed", "url": url, "error": str(e)}))
