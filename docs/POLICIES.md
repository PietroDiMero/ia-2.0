# Operational Policies

## Robots.txt and Terms of Service
- The crawler MUST read and honor robots.txt from each domain.
- Do not crawl disallowed paths. If robots or ToS prohibit automated access, skip the site.
- Identify with a clear User-Agent and contact info.

## Rate Limiting
- Default: 1 request/second per domain, with burst control and jitter.
- On 429/5xx, exponential backoff up to a cap, then skip until next run.

## Copyright and Source Attribution
- Always store the source URL for fetched content.
- In RAG answers, display citations (clickable) and avoid reproducing large portions of copyrighted text.
- Honor removal requests by rights holders.

## DSAR-like Deletion Policy
- On verified request, remove documents and derived embeddings linked to the requester or specified content.
- Rebuild index and purge caches; confirm action to requester.

## Logging and GDPR
- Minimize PII in logs; prefer IDs and aggregate metrics.
- Legal basis: legitimate interest; document assessments.
- Retention: define and enforce durations (e.g., 30-90 days logs).
- Access control and audit for production logs and data.
