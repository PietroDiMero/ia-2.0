from __future__ import annotations

import json
import os
import time
from datetime import datetime
import traceback
from pathlib import Path
import shutil
import socket
import threading
from collections import deque
import hashlib
from urllib.parse import urlparse, urljoin, parse_qs, unquote, quote
import urllib.robotparser as robotparser
from typing import Any, Dict

from flask import Flask, jsonify, request, send_from_directory
from flask import has_request_context
from flask_cors import CORS

# We reuse the core logic implemented in main.py
import main as core
try:
    from openai import OpenAI  # type: ignore
except Exception:
    OpenAI = None  # type: ignore


ROOT = Path(__file__).resolve().parent

# Data directory persistence
def _ensure_data_dir() -> Path:
    data_dir_env = os.getenv("DATA_DIR")
    if data_dir_env:
        p = Path(data_dir_env)
    else:
        p = ROOT  # fallback
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    # Seed initial files if missing
    seed_data = ROOT / "dummy_data.json"
    target_data = p / "dummy_data.json"
    if not target_data.exists():
        try:
            if seed_data.exists():
                shutil.copyfile(seed_data, target_data)
            else:
                target_data.write_text("[]", encoding="utf-8")
        except Exception:
            # Best effort
            pass
    target_logs = p / "logs.json"
    if not target_logs.exists():
        try:
            target_logs.write_text("[]", encoding="utf-8")
        except Exception:
            pass
    return p

DATA_DIR = _ensure_data_dir()
DATA_FILE = DATA_DIR / "dummy_data.json"
LOG_FILE = DATA_DIR / "logs.json"


app = Flask(__name__, static_folder=str(ROOT / "dashboard"))
CORS(app, resources={r"*": {"origins": ["http://localhost:3000", "http://127.0.0.1:3000", "*"]}})


# ---- In-memory state ----
running: bool = False

# Initialize documents and TF-IDF index
docs = core.load_documents()
doc_vecs, idf = core.build_index(docs)


def _load_logs() -> list[Dict[str, Any]]:
    try:
        if LOG_FILE.exists():
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_logs(logs: list[Dict[str, Any]]) -> None:
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _get_last_threshold(default: float = 0.1) -> float:
    logs = _load_logs()
    if logs:
        last = logs[-1]
        if isinstance(last, dict) and isinstance(last.get("threshold"), (int, float)):
            return float(last["threshold"])
    return default


threshold: float = _get_last_threshold()

# ---- Background web crawler state ----
_crawl_lock = threading.Lock()
_crawl_thread: threading.Thread | None = None
_crawl_state: Dict[str, Any] = {
    "running": False,
    "started_at": None,
    "seeds": [],
    "domain": None,
    "max_pages": 0,
    "delay": 1.5,
    "visited": set(),  # internal only
    "queue": deque(),  # internal only
    "added": 0,
    "errors": 0,
    "last_url": None,
    "last_error": None,
    "blocked_domains": set(),
}

# Domains to skip (anti-bot or low textual value)
SKIP_DOMAINS = {
    "facebook.com", "m.facebook.com", "instagram.com", "linkedin.com", "x.com", "twitter.com",
    "tiktok.com", "pinterest.com", "youtube.com", "youtu.be", "tripadvisor.com", "tripadvisor.fr",
}

# ---- Server-side error buffer (recent errors) ----
_error_buffer: deque[dict] = deque(maxlen=200)
_IGNORED_ERROR_PATH_PREFIXES = (
    "/.well-known/appspecific",
)
_IGNORED_ERROR_PATHS = {"/favicon.ico"}

def _record_error(message: str, status: int, extra: dict | None = None) -> None:
    try:
        path = method = None
        if has_request_context():
            try:
                path = request.path
                method = request.method
            except Exception:
                path = None
                method = None
        # Skip noisy/benign paths
        if path and (path in _IGNORED_ERROR_PATHS or any(path.startswith(p) for p in _IGNORED_ERROR_PATH_PREFIXES)):
            return
        evt = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "path": path,
            "method": method,
            "status": int(status),
            "message": str(message)[:2000],
        }
        if extra:
            # Keep stack/info concise
            if "stack" in extra and isinstance(extra["stack"], str):
                extra = {**extra, "stack": extra["stack"][:4000]}
            evt.update(extra)
        _error_buffer.append(evt)
    except Exception:
        # Never raise from logging
        pass


# --- Noisy path handlers to avoid 404 spam ---
@app.get("/.well-known/appspecific/com.chrome.devtools.json")
def _wellknown_chrome_devtools():
    # Return an empty JSON object; browsers probing this will get 200
    return jsonify({})


@app.get("/favicon.ico")
def _favicon_blank():
    # Avoid 404 noise for favicon; browsers probe this by default
    return ("", 204, {})


def _norm_url(u: str) -> str:
    try:
        parsed = urlparse(u)
        # Remove fragment
        clean = parsed._replace(fragment="").geturl()
        return clean
    except Exception:
        return u


def _is_http_url(u: str) -> bool:
    return u.startswith("http://") or u.startswith("https://")


def _same_domain(u: str, domain: str) -> bool:
    try:
        return urlparse(u).netloc.endswith(domain)
    except Exception:
        return False


def _read_dataset() -> list[Dict[str, Any]]:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_dataset(dataset: list[Dict[str, Any]]):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)


def _rebuild_index_if_needed(batch_counter: int):
    global docs, doc_vecs, idf
    if batch_counter >= 5:
        docs = _read_dataset()
        doc_vecs, idf = core.build_index(docs)
        return 0
    return batch_counter


def _extract_text_from_html(html: str) -> tuple[str, str]:
    from bs4 import BeautifulSoup  # type: ignore
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string if soup.title and soup.title.string else "")[:200]
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    text = "\n".join(paragraphs)
    return title, text


def _crawl_worker():
    global docs, doc_vecs, idf
    ua_pool = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    headers = {
        "User-Agent": ua_pool[0],
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    # Snapshot config
    with _crawl_lock:
        domain = _crawl_state.get("domain")
        max_pages = int(_crawl_state.get("max_pages") or 0)
        delay = float(_crawl_state.get("delay") or 1.5)
        queue: deque[str] = _crawl_state["queue"]
        visited: set[str] = _crawl_state["visited"]

    rp = robotparser.RobotFileParser()
    if domain:
        robots_url = f"https://{domain}/robots.txt"
        try:
            rp.set_url(robots_url)
            rp.read()
        except Exception:
            # If robots fails to load, we proceed conservatively
            pass

    additions_since_reindex = 0
    domain_last_fetch: dict[str, float] = {}
    block_domains: set[str] = set()
    retries: dict[str, int] = {}
    try:
        while True:
            with _crawl_lock:
                if not _crawl_state["running"]:
                    break
                if not queue or len(visited) >= max_pages:
                    _crawl_state["running"] = False
                    break
                current = queue.popleft()
                _crawl_state["last_url"] = current
            if current in visited:
                continue
            visited.add(current)
            # Throttle per domain
            cur_domain = urlparse(current).netloc
            # Skip if in skip-list or previously blocked
            with _crawl_lock:
                shared_blocked = set(_crawl_state.get("blocked_domains", set()))
            if cur_domain in SKIP_DOMAINS or cur_domain in shared_blocked:
                continue
            now = time.time()
            last = domain_last_fetch.get(cur_domain, 0.0)
            min_gap = max(1.0, delay)
            wait = last + min_gap - now
            if wait > 0:
                time.sleep(wait)
            domain_last_fetch[cur_domain] = time.time()
            # Robots check
            try:
                if domain and not rp.can_fetch(headers["User-Agent"], current):
                    continue
            except Exception:
                pass
            try:
                import requests
                # rotate UA a bit
                headers["User-Agent"] = ua_pool[len(visited) % len(ua_pool)]
                resp = requests.get(current, headers=headers, timeout=20, allow_redirects=True)
                # Handle 429 (Too Many Requests): simple backoff and retry once
                if resp.status_code == 429:
                    backoff = min(10.0, delay * 2)
                    time.sleep(backoff)
                    retries[current] = retries.get(current, 0) + 1
                    if retries[current] <= 1:
                        with _crawl_lock:
                            _crawl_state["queue"].append(current)
                        continue
                # Handle 403: block domain for this run and skip
                if resp.status_code == 403:
                    block_domains.add(cur_domain)
                    with _crawl_lock:
                        bd = _crawl_state.setdefault("blocked_domains", set())
                        bd.add(cur_domain)
                    raise requests.RequestException(f"403 Forbidden for domain {cur_domain}")
                resp.raise_for_status()
                # Content-Type filter
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if "text/html" not in ctype:
                    continue
                # Content-Length filter (if provided)
                try:
                    clen = int(resp.headers.get("Content-Length") or 0)
                    if clen and clen > 3_000_000:  # ~3MB
                        continue
                except Exception:
                    pass
                title, text = _extract_text_from_html(resp.text)
                # Minimal content filter
                content = (text or "").strip()
                if len(content) < 200:
                    # Skip very short pages
                    continue
                # Deduplicate by URL and content hash
                url_key = _norm_url(current)
                content_hash = hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()
                dataset = _read_dataset()
                known_urls = {d.get("url") for d in dataset}
                known_hashes = {hashlib.sha256((d.get("content") or "").encode("utf-8", errors="ignore")).hexdigest() for d in dataset}
                if url_key in known_urls or content_hash in known_hashes:
                    # Already present
                    pass
                else:
                    dataset.append({"title": title or url_key, "url": url_key, "content": content[:5000]})
                    _write_dataset(dataset)
                    additions_since_reindex += 1
                    with _crawl_lock:
                        _crawl_state["added"] += 1
                    additions_since_reindex = _rebuild_index_if_needed(additions_since_reindex)
                # Extract links for BFS
                from bs4 import BeautifulSoup  # type: ignore
                s = BeautifulSoup(resp.text, "html.parser")
                for a in s.find_all("a", href=True):
                    href = a.get("href")
                    if not href:
                        continue
                    if href.startswith("mailto:") or href.startswith("javascript:"):
                        continue
                    abs_url = urljoin(current, href)
                    abs_url = _norm_url(abs_url)
                    if not _is_http_url(abs_url):
                        continue
                    if domain and not _same_domain(abs_url, domain):
                        continue
                    # Skip blocked or unfriendly domains
                    next_dom = urlparse(abs_url).netloc
                    with _crawl_lock:
                        shared_blocked = set(_crawl_state.get("blocked_domains", set()))
                    if next_dom in block_domains or next_dom in SKIP_DOMAINS or next_dom in shared_blocked:
                        continue
                    if abs_url not in visited:
                        with _crawl_lock:
                            queue.append(abs_url)
            except Exception as e:  # network or parse errors
                with _crawl_lock:
                    _crawl_state["errors"] += 1
                    _crawl_state["last_error"] = str(e)
            finally:
                time.sleep(delay)
    finally:
        # Final rebuild if pending additions
        if additions_since_reindex:
            docs = _read_dataset()
            doc_vecs, idf = core.build_index(docs)
        with _crawl_lock:
            _crawl_state["running"] = False


def _start_crawl(seeds: list[str], max_pages: int, delay: float, same_domain: bool) -> dict:
    """Initialize and start crawler thread with given seeds."""
    global _crawl_thread
    parsed0 = urlparse(seeds[0])
    if not parsed0.scheme or not parsed0.netloc:
        raise ValueError("seed invalide")
    domain = parsed0.netloc if same_domain else None
    with _crawl_lock:
        if _crawl_state["running"]:
            raise RuntimeError("un crawl est déjà en cours")
        _crawl_state.update(
            {
                "running": True,
                "started_at": datetime.utcnow().isoformat() + "Z",
                "seeds": seeds,
                "domain": domain,
                "max_pages": max_pages,
                "delay": delay,
                "visited": set(),
                "queue": deque(),
                "added": 0,
                "errors": 0,
                "last_url": None,
                "last_error": None,
            }
        )
        for s in seeds:
            if _is_http_url(s):
                _crawl_state["queue"].append(_norm_url(s))
    _crawl_thread = threading.Thread(target=_crawl_worker, daemon=True)
    _crawl_thread.start()
    return {"domain": domain, "max_pages": max_pages, "delay": delay}


def _discover_links_ddg(query: str, max_results: int = 10, lang: str = "fr-fr") -> list[str]:
    links: list[str] = []
    try:
        import requests
        from bs4 import BeautifulSoup  # type: ignore
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        }
        url = "https://duckduckgo.com/html/"
        params = {"q": query, "kl": lang}
        resp = requests.get(url, params=params, headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("a.result__a, a.result__url"):  # be flexible
            href = a.get("href")
            if not href:
                continue
            # Extract direct URL from DuckDuckGo redirect
            if "duckduckgo.com/l/" in href or "uddg=" in href:
                try:
                    qs = parse_qs(urlparse(href).query)
                    target = qs.get("uddg", [None])[0]
                    if target:
                        href = unquote(target)
                except Exception:
                    pass
            if _is_http_url(href):
                links.append(_norm_url(href))
            if len(links) >= max_results:
                break
    except Exception:
        pass
    # Deduplicate preserving order
    seen = set()
    uniq = []
    for u in links:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def _discover_links_bing(query: str, max_results: int = 10) -> list[str]:
    key = os.getenv("BING_API_KEY")
    if not key:
        return []
    try:
        import requests
        headers = {"Ocp-Apim-Subscription-Key": key}
        params = {"q": query, "count": max_results}
        resp = requests.get("https://api.bing.microsoft.com/v7.0/search", headers=headers, params=params, timeout=20)
        resp.raise_for_status()
        js = resp.json()
        web_pages = js.get("webPages", {}).get("value", [])
        return [v.get("url") for v in web_pages if _is_http_url(v.get("url") or "")]
    except Exception:
        return []


def _discover_links_google_cse(query: str, max_results: int = 10) -> list[str]:
    api_key = os.getenv("GOOGLE_API_KEY")
    cse_id = os.getenv("GOOGLE_CSE_ID")
    if not api_key or not cse_id:
        return []
    try:
        import requests
        params = {"key": api_key, "cx": cse_id, "q": query, "num": min(max_results, 10)}
        resp = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=20)
        resp.raise_for_status()
        js = resp.json()
        items = js.get("items", [])
        return [it.get("link") for it in items if _is_http_url(it.get("link") or "")]
    except Exception:
        return []


def _discover_links_serpapi(query: str, max_results: int = 10, engine: str = "google") -> list[str]:
    key = os.getenv("SERPAPI_KEY")
    if not key:
        return []
    try:
        import requests
        params = {"engine": engine, "q": query, "api_key": key, "num": max_results}
        resp = requests.get("https://serpapi.com/search", params=params, timeout=20)
        resp.raise_for_status()
        js = resp.json()
        links: list[str] = []
        for it in js.get("organic_results", []) or []:
            url = it.get("link") or it.get("url")
            if _is_http_url(url or ""):
                links.append(_norm_url(url))
        return links[:max_results]
    except Exception:
        return []


@app.post("/api/crawl_start")
def api_crawl_start():
    """Start a background crawl job.
    Body: { seeds: [url, ...], max_pages?: int (default 50), delay?: float seconds (default 1.5), same_domain?: bool (default true) }
    """
    global _crawl_thread
    try:
        data = request.get_json(force=True) or {}
        seeds = data.get("seeds") or []
        if isinstance(seeds, str):
            seeds = [seeds]
        seeds = [s.strip() for s in seeds if isinstance(s, str) and s.strip()]
        if not seeds:
            return jsonify({"error": "seeds manquants"}), 400
        # sanitize seeds: strip quotes, extract first http(s)://, add https to www.*
        import re as _re
        def _clean_seed(u: str) -> str | None:
            u = u.strip()
            if (u.startswith("'") and u.endswith("'")) or (u.startswith('"') and u.endswith('"')):
                u = u[1:-1]
            if not u.lower().startswith(("http://", "https://")) and "http" in u:
                m = _re.search(r"https?://[^\s'\"]+", u)
                if m:
                    u = m.group(0)
            if not u.lower().startswith(("http://", "https://")) and u.lower().startswith("www."):
                u = "https://" + u
            return u if u.lower().startswith(("http://", "https://")) else None
        seeds = [s for s in (_clean_seed(s) for s in seeds) if s]
        if not seeds:
            return jsonify({"error": "Aucun seed valide (attendu http(s)://...)"}), 400
        max_pages = int(data.get("max_pages") or 50)
        delay = float(data.get("delay") or 1.5)
        same_domain = True if data.get("same_domain") is None else bool(data.get("same_domain"))

        # Determine domain from first seed
        info = _start_crawl(seeds, max_pages, delay, same_domain)
        return jsonify({"ok": True, **info})
    except RuntimeError as re:
        _record_error(str(re), 409)
        return jsonify({"error": str(re)}), 409
    except ValueError as ve:
        _record_error(str(ve), 400)
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        _record_error(str(e), 500, {"stack": traceback.format_exc()})
        return jsonify({"error": str(e)}), 500
@app.post("/api/search_and_learn")
def api_search_and_learn():
    """Discover links from search engines for a query, then crawl them.

    Body: { query: str, max_results?: int=10, engine?: 'ddg'|'bing'|'google'|'serpapi', max_pages?: int=30, delay?: float=1.5, same_domain?: bool=false }
    """
    try:
        data = request.get_json(force=True) or {}
        query = (data.get("query") or "").strip()
        if not query:
            return jsonify({"error": "query manquante"}), 400
        max_results = int(data.get("max_results") or 10)
        engine = (data.get("engine") or "ddg").lower()
        max_pages = int(data.get("max_pages") or 30)
        delay = float(data.get("delay") or 1.5)
        same_domain = bool(data.get("same_domain") or False)

        links: list[str] = []
        if engine == "bing":
            links = _discover_links_bing(query, max_results=max_results)
        elif engine == "google":
            links = _discover_links_google_cse(query, max_results=max_results)
        elif engine == "serpapi":
            links = _discover_links_serpapi(query, max_results=max_results)
        else:
            links = _discover_links_ddg(query, max_results=max_results)

        if not links:
            return jsonify({"error": "Aucun lien découvert (vérifiez le moteur/API key)", "engine": engine}), 424

        info = _start_crawl(links, max_pages=max_pages, delay=delay, same_domain=same_domain)
        return jsonify({"ok": True, "engine": engine, "discovered": len(links), "seeds": links[:5], **info})
    except RuntimeError as re:
        _record_error(str(re), 409)
        return jsonify({"error": str(re)}), 409
    except ValueError as ve:
        _record_error(str(ve), 400)
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        _record_error(str(e), 500, {"stack": traceback.format_exc()})
        return jsonify({"error": str(e)}), 500


@app.post("/api/crawl_stop")
def api_crawl_stop():
    with _crawl_lock:
        _crawl_state["running"] = False
    return jsonify({"ok": True})


@app.get("/api/crawl_status")
def api_crawl_status():
    with _crawl_lock:
        st = {
            k: v
            for k, v in _crawl_state.items()
            if k not in {"visited", "queue"}
        }
        st["visited_count"] = len(_crawl_state.get("visited", []))
        st["queue_count"] = len(_crawl_state.get("queue", []))
        # Report blocked domains
        bd = _crawl_state.get("blocked_domains", set())
        st["blocked_count"] = len(bd)
        st["blocked_domains"] = sorted(list(bd))[:10]
    return jsonify(st)


def _infer_source_type(url: str) -> str:
    u = (url or "").lower()
    if "rss" in u or u.endswith(".xml"):
        return "rss"
    if "/api/" in u or "api." in u:
        return "api"
    return "html"


def _infer_language(text: str) -> str:
    t = text or ""
    # Very naive detection
    if any(c in t for c in "éèêàùçôîïëäöü"):
        return "fr"
    return "en"


def _doc_created_at_default() -> str:
    # Fallback to file mtime as ISO date
    try:
        ts = DATA_FILE.stat().st_mtime
        return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m-%d")


def _get_openai_client() -> Any | None:
    """Return an OpenAI client if OPENAI_API_KEY is configured and SDK available."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return None
    try:
        client = OpenAI(api_key=api_key)
        return client
    except Exception:
        return None


@app.get("/")
def index():
    # Serve the static dashboard
    return send_from_directory(app.static_folder, "dashboard.html")


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/metrics")
def metrics():
    """Minimal metrics compatible with frontend expectations."""
    try:
        documents = len(docs)
        # Simple placeholders
        coverage = min(1.0, documents / 100.0)
        logs = _load_logs()
        if logs:
            avg_rt = sum(float(x.get("response_time", 0.0)) for x in logs) / max(1, len(logs))
        else:
            avg_rt = None
        return jsonify(
            {
                "documents": documents,
                "coverage": coverage,
                "freshness_days": None,
                "avg_response_time": avg_rt,
                "last_update": _doc_created_at_default(),
                "score": round(min(1.0, 0.5 + (documents / 200.0)), 2),
            }
        )
    except Exception as e:
        _record_error(str(e), 500, {"stack": traceback.format_exc()})
        return jsonify({"error": str(e)}), 500


@app.get("/jobs")
def jobs_list():
    """Return an empty jobs list to satisfy UI queries."""
    job_type = request.args.get("type")
    status = request.args.get("status")
    return jsonify({"items": [], "type": job_type, "status": status})


@app.get("/search")
def search():
    """Simple search endpoint mapping to TF-IDF answer generation.

    Query params: q (str), k (int)
    Returns: { query, answer, confidence, sources }
    """
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"error": "missing q"}), 400
    try:
        k = int(request.args.get("k") or 5)
    except ValueError:
        k = 5
    results = core.query_documents(q, doc_vecs, idf, docs, k=k, threshold=threshold)
    answer, sources = core.generate_answer(q, results)
    # naive confidence: based on number of sources
    conf = min(0.99, 0.3 + 0.2 * len(sources)) if sources else 0.2
    return jsonify({"query": q, "answer": answer, "confidence": conf, "sources": sources})


@app.get("/dashboard/overview")
def dashboard_overview():
    docs_count = len(docs)
    jobs_running = 0
    return jsonify(
        {
            "kpis": {
                "documents": docs_count,
                "last_update": _doc_created_at_default(),
                "score": round(min(1.0, 0.5 + (docs_count / 200.0)), 2),
                "jobs_active": jobs_running,
            }
        }
    )


@app.get("/dashboard/timeseries/docs_per_day")
def docs_per_day():
    # Build a simple timeseries from logs as proxy for ingest activity
    data = {}
    for entry in _load_logs():
        ts = entry.get("timestamp")
        if not ts:
            continue
        day = ts[:10]
        data[day] = data.get(day, 0) + 1
    series = [
        {"date": day, "documents": count} for day, count in sorted(data.items())
    ]
    if not series:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        series = [{"date": today, "documents": len(docs)}]
    return jsonify({"items": series})


@app.get("/dashboard/sources_breakdown")
def sources_breakdown():
    buckets = {"rss": 0, "api": 0, "html": 0}
    for d in docs:
        st = _infer_source_type(d.get("url", ""))
        if st in buckets:
            buckets[st] += 1
        else:
            buckets["html"] += 1
    items = [{"type": k, "count": v} for k, v in buckets.items()]
    return jsonify({"items": items})


@app.get("/dashboard/recent_docs")
def recent_docs():
    items = []
    for d in docs[-20:][::-1]:
        items.append(
            {
                "title": d.get("title") or "",
                "source": _infer_source_type(d.get("url", "")),
                "date": _doc_created_at_default(),
                "lang": _infer_language(d.get("content", "")),
            }
        )
    return jsonify({"items": items})


@app.get("/dashboard/jobs_active")
def jobs_active():
    return jsonify({"items": []})


@app.get("/dashboard/evolver_history")
def evolver_history():
    hist_file = ROOT / "real-time-ai-dashboard" / "evolver" / "history.json"
    if hist_file.exists():
        try:
            with open(hist_file, "r", encoding="utf-8") as f:
                return jsonify({"items": json.load(f)})
        except Exception:
            pass
    return jsonify({"items": []})


@app.get("/api/logs")
def api_logs():
    return jsonify(_load_logs())


def _parse_host_port_from_url(url: str, default_port: int) -> tuple[str, int]:
    try:
        u = urlparse(url)
        host = u.hostname or "localhost"
        port = u.port or default_port
        return host, int(port)
    except Exception:
        return "localhost", default_port


def _probe_tcp(host: str, port: int, timeout: float = 1.0) -> tuple[bool, str | None]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, None
    except Exception as e:
        return False, str(e)


@app.get("/api/healthz")
def api_healthz():
    # Backend is up if handler reached
    health: dict[str, Any] = {"backend": True}
    # DB reachability via TCP
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        host, port = _parse_host_port_from_url(db_url, 5432)
        ok, err = _probe_tcp(host, port)
        health["db"] = {"ok": ok, "host": host, "port": port, "error": err}
    else:
        health["db"] = {"ok": False, "error": "DATABASE_URL non défini"}
    # Redis reachability via TCP
    redis_url = os.getenv("REDIS_URL", "")
    if redis_url:
        host, port = _parse_host_port_from_url(redis_url, 6379)
        ok, err = _probe_tcp(host, port)
        health["redis"] = {"ok": ok, "host": host, "port": port, "error": err}
    else:
        health["redis"] = {"ok": False, "error": "REDIS_URL non défini"}
    # Data persistence
    try:
        docs_count = len(_read_dataset())
        health["data"] = {"ok": DATA_DIR.exists(), "dir": str(DATA_DIR), "docs": docs_count}
    except Exception as e:
        health["data"] = {"ok": False, "dir": str(DATA_DIR), "error": str(e)}
    # Crawler state
    with _crawl_lock:
        health["crawler"] = {
            "running": bool(_crawl_state.get("running")),
            "visited": len(_crawl_state.get("visited", [])),
            "queue": len(_crawl_state.get("queue", [])),
            "added": int(_crawl_state.get("added", 0)),
            "errors": int(_crawl_state.get("errors", 0)),
        }
    return jsonify(health)


@app.get("/api/status")
def api_status():
    logs = _load_logs()
    return jsonify(
        {
            "running": running,
            "threshold": threshold,
            "logs": len(logs),
        }
    )


@app.post("/api/start")
def api_start():
    global running
    running = True
    return jsonify({"ok": True})


@app.post("/api/stop")
def api_stop():
    global running
    running = False
    return jsonify({"ok": True})


@app.post("/api/ask")
def api_ask():
    global threshold
    try:
        data = request.get_json(force=True) or {}
        question = (data.get("question") or "").strip()
        if not question:
            return jsonify({"error": "question manquante"}), 400

        start = time.perf_counter()
        results = core.query_documents(question, doc_vecs, idf, docs, k=3, threshold=threshold)
        answer, sources = core.generate_answer(question, results)
        elapsed = time.perf_counter() - start

        # Simple evaluation: success if at least two distinct sources
        success = len(sources) >= 2
        # Adjust threshold (bounds 0.05 - 0.5) similar to main.py
        if success:
            threshold = max(0.05, threshold - 0.02)
        else:
            threshold = min(0.5, threshold + 0.02)

        # Optional: augment answer using OpenAI if configured
        llm_answer = None
        client = _get_openai_client()
        if client is not None:
            try:
                # Build a short context from top sources
                context_snippets = []
                for _, doc in results[:2]:
                    context_snippets.append(f"Titre: {doc.get('title')}\nContenu: {doc.get('content')[:800]}")
                prompt = (
                    "Tu es un assistant utile. Réponds brièvement et cite les sources si possible.\n" 
                    f"Question: {question}\n"
                    + ("\n\nContexte:\n" + "\n---\n".join(context_snippets) if context_snippets else "")
                )
                llm_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
                resp = client.responses.create(model=llm_model, input=prompt, store=False)
                llm_answer = getattr(resp, "output_text", None) or getattr(resp, "content", None)
            except Exception:
                llm_answer = None

        # Log the interaction
        logs = _load_logs()
        logs.append(
            {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "question": question,
                "answer": answer,
                "llm_answer": llm_answer,
                "sources": sources,
                "success": success,
                "response_time": elapsed,
                "threshold": threshold,
            }
        )
        _save_logs(logs)

        return jsonify(
            {
                "answer": answer,
                "llm_answer": llm_answer,
                "sources": sources,
                "response_time": elapsed,
                "threshold": threshold,
            }
        )
    except Exception as e:
        _record_error(str(e), 500, {"stack": traceback.format_exc()})
        return jsonify({"error": str(e)}), 500


@app.get("/api/llm_test")
def api_llm_test():
    client = _get_openai_client()
    if client is None:
        _record_error("OPENAI_API_KEY manquant ou SDK non disponible", 400)
        return jsonify({"ok": False, "error": "OPENAI_API_KEY manquant ou SDK non disponible"}), 400
    try:
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        resp = client.responses.create(model=model, input="write a 1-line haiku about AI", store=False)
        text = getattr(resp, "output_text", None) or getattr(resp, "content", None)
        return jsonify({"ok": True, "model": model, "text": text})
    except Exception as e:
        _record_error(str(e), 500, {"stack": traceback.format_exc()})
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/evolve")
def api_evolve():
    """Minimal evolution step: gently decrease threshold within bounds."""
    global threshold
    try:
        old = threshold
        threshold = max(0.05, threshold - 0.01)
        return jsonify({"ok": True, "old_threshold": old, "new_threshold": threshold})
    except Exception as e:
        _record_error(str(e), 500, {"stack": traceback.format_exc()})
        return jsonify({"error": str(e)}), 500


@app.post("/api/crawl")
def api_crawl():
    """
    Very small crawler: fetch an URL, extract title + text, add to dataset, rebuild index.
    """
    import re
    from bs4 import BeautifulSoup  # type: ignore
    import requests
    from urllib.parse import urlparse, unquote, quote

    global docs, doc_vecs, idf

    try:
        data = request.get_json(force=True) or {}
        raw_url = (data.get("url") or "").strip()
        if not raw_url:
            return jsonify({"error": "url manquante"}), 400
        # Sanitize and ensure scheme
        url = raw_url
        # Strip surrounding quotes if pasted
        if (url.startswith("'") and url.endswith("'")) or (url.startswith('"') and url.endswith('"')):
            url = url[1:-1]
        # If the string contains an URL inside text, extract the first one
        if not url.lower().startswith(("http://", "https://")) and "http" in url:
            import re as _re
            m = _re.search(r"https?://[^\s'\"]+", url)
            if m:
                url = m.group(0)
        if not url.lower().startswith(("http://", "https://")):
            if url.lower().startswith("www."):
                url = "https://" + url
            else:
                return jsonify({"error": "URL invalide: doit commencer par http(s)://"}), 400

        # Use a browser-like User-Agent, Accept-Language and allow redirects to avoid simple 403 blocks
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "Accept": "application/json, text/html;q=0.8"
        }
        parsed = urlparse(url)
        is_wikipedia = parsed.netloc.endswith("wikipedia.org") and "/wiki/" in parsed.path
        if not parsed.scheme or not parsed.netloc:
            return jsonify({"error": "URL invalide: hôte introuvable"}), 400

        # Wikipedia: prefer API summary directly to avoid HTML protections
        if is_wikipedia:
            lang = parsed.netloc.split(".")[0] or "en"
            title_slug = parsed.path.split("/wiki/")[-1]
            title = unquote(title_slug)
            api_title = quote(title, safe="")
            api_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{api_title}?redirect=true"
            api_resp = requests.get(api_url, timeout=20, headers=headers)
            api_resp.raise_for_status()
            data_json = api_resp.json()
            title = data_json.get("title") or title
            extract = data_json.get("extract") or ""
            if not extract:
                # Fallback to MediaWiki action API extracts
                action_url = f"https://{lang}.wikipedia.org/w/api.php"
                params = {
                    "action": "query",
                    "prop": "extracts",
                    "explaintext": 1,
                    "redirects": 1,
                    "format": "json",
                    "titles": title,
                }
                action_resp = requests.get(action_url, params=params, timeout=20, headers=headers)
                action_resp.raise_for_status()
                action_json = action_resp.json()
                pages = action_json.get("query", {}).get("pages", {})
                for _, page in pages.items():
                    extract = page.get("extract") or ""
                    if extract:
                        break
                if not extract:
                    return jsonify({"error": "Wikipedia: résumé indisponible pour cette page (essayez un article spécifique)."}), 422
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                dataset = json.load(f)
            dataset.append({"title": title, "url": url, "content": extract[:5000]})
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(dataset, f, ensure_ascii=False, indent=2)
            docs = dataset
            doc_vecs, idf = core.build_index(docs)
            return jsonify({"ok": True, "title": title, "added": True, "via": "wikipedia_api"})

        # Generic HTML fetch
        resp = requests.get(url, timeout=20, headers=headers, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # Extract title and main text
        title = (soup.title.string if soup.title and soup.title.string else url)[:200]
        # Simple text extraction: join paragraphs
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        text = "\n".join(paragraphs)
        # Trim overly long content
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            text = "Contenu indisponible ou page principalement visuelle."

        # Load, append, and persist
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            dataset = json.load(f)
        new_doc = {"title": title, "url": url, "content": text[:5000]}
        dataset.append(new_doc)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(dataset, f, ensure_ascii=False, indent=2)

        # Refresh in-memory index
        docs = dataset
        doc_vecs, idf = core.build_index(docs)

        return jsonify({"ok": True, "title": title, "added": True})
    except requests.RequestException as rexc:  # type: ignore
        _record_error(f"HTTP: {rexc}", 502)
        return jsonify({"error": f"HTTP: {rexc}"}), 502
    except Exception as e:
        _record_error(str(e), 500, {"stack": traceback.format_exc()})
        return jsonify({"error": str(e)}), 500


# Log any HTTP error responses automatically
@app.after_request
def after_request_log_errors(response):  # type: ignore
    try:
        status = int(getattr(response, "status_code", 0) or 0)
        if status >= 400:
            msg = None
            try:
                if response.is_json:
                    js = response.get_json(silent=True) or {}
                    msg = js.get("error") or js.get("message")
            except Exception:
                msg = None
            _record_error(msg or f"HTTP {status}", status)
    except Exception:
        pass
    return response

# ---- Global error handlers and error listing endpoint ----
@app.errorhandler(404)
def handle_404(e):  # type: ignore
    _record_error("Not Found", 404)
    return jsonify({"error": "Not Found"}), 404


@app.errorhandler(405)
def handle_405(e):  # type: ignore
    _record_error("Method Not Allowed", 405)
    return jsonify({"error": "Method Not Allowed"}), 405


@app.errorhandler(500)
def handle_500(e):  # type: ignore
    _record_error(str(e), 500, {"stack": traceback.format_exc()})
    return jsonify({"error": "Internal Server Error"}), 500


@app.get("/api/errors")
def api_errors():
    # Return recent errors (most recent last)
    return jsonify(list(_error_buffer))


if __name__ == "__main__":
    # Bind 0.0.0.0 for Docker container access; still fine locally
    app.run(host="0.0.0.0", port=8000, debug=True)
