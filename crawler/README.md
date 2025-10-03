# Crawler Compliance

The crawler follows these policies:

- Obey robots.txt (CRAWLER_OBEY_ROBOTS=1) and only fetch allowed paths.
- Use a clear User-Agent with contact info (CRAWLER_USER_AGENT).
- Per-domain rate limit (CRAWLER_RATE_LIMIT_PER_DOMAIN, default 1 req/s), with backoff on 429/5xx.
- Deduplicate by URL/content-hash; minimal storage of raw content; prefer metadata.
- Log in structured JSON; avoid PII and secrets.

Environment variables are documented in `.env.example`.
