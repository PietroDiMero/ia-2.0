from __future__ import annotations

from .db import connect, log_event

SEED_SOURCES = [
    ("https://openai.com/blog", "html"),
    ("https://huggingface.co/blog", "html"),
    ("https://stability.ai/blog", "html"),
]


def seed_sources_if_empty() -> int:
    """Insert a small set of default sources if table is empty."""
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM sources;")
                count = cur.fetchone()[0]
                if count and count > 0:
                    return 0
                inserted = 0
                for url, kind in SEED_SOURCES:
                    try:
                        cur.execute(
                            "INSERT INTO sources(url, kind) VALUES(%s,%s) ON CONFLICT (url) DO NOTHING;",
                            (url, kind),
                        )
                        inserted += cur.rowcount or 0
                    except Exception:
                        pass
            conn.commit()
        if inserted:
            log_event("seed", "Seed sources inserted", meta={"count": inserted})
        return inserted
    except Exception:
        return 0
