# Security, Privacy, and Compliance Guidelines

This document outlines how we manage secrets, adhere to site policies (robots.txt, Terms of Service), implement rate-limiting, handle data subject requests, and log responsibly under GDPR.

## Secret and Key Management
- Use environment variables for all secrets (see `.env.example`). Do not commit secrets to git.
- Store production secrets in a vault (e.g., Azure Key Vault, AWS Secrets Manager, GCP Secret Manager, or HashiCorp Vault). Rotate regularly (every 90 days or on exposure).
- Restrict scopes to least privilege. Example: API keys with read-only where possible.
- CI/CD: use GitHub Actions Secrets and Repository/Org-level Encrypted Secrets. Prefer OIDC with cloud roles over long-lived keys.
- Local dev: put secrets in `.env` (not committed) and load via dotenv or platform env.

## Respecting robots.txt, ToS, and Copyright
- Crawler must:
  - Obey `robots.txt` by default. Only crawl allowed paths.
  - Respect site Terms of Service (ToS). If ToS forbids automated scraping, do not crawl.
  - Rate limit per domain (default: 1 req/s/domain) with backoff and retry caps.
  - Identify with a clear `User-Agent` that includes contact info.
  - Deduplicate content; avoid excessive load on target sites.
- Copyright and Source Attribution:
  - Store and surface source URLs for any generated content (RAG citations) where feasible.
  - Do not republish proprietary content; use snippets for reference only.
  - Remove content on request by rights holders (see DSAR-like below).

## DSAR-like Policy (Data Deletion on Request)
- If we receive a request from a data subject or rights holder to remove personal data or proprietary content:
  - Verify the request (identity and scope) via a documented process.
  - Remove documents and derived embeddings from storage for the affected identifiers.
  - Rebuild the index and purge caches.
  - Log the request, action taken, and timestamp. Provide confirmation to the requester.

## Logging and PII Minimization
- Log only necessary operational metrics: timestamps, response times, error codes, job ids, domains, and status counters.
- Avoid logging raw content, personal data, or full query strings with PII. Mask tokens, API keys, and credentials.
- Use structured JSON logs where possible.
- Set log retention to the minimum needed for operations (e.g., 30-90 days), then purge.

## GDPR Considerations
- Legal basis: legitimate interest to improve the system while minimizing impact on data subjects.
- Data minimization: store only what is required for retrieval and evaluation; prefer metadata over raw content when possible.
- Retention: define retention periods per data type (e.g., logs 30-90 days; raw crawl content 90 days; embeddings 180 days) and document exceptions.
- Access controls: restrict DB and storage access to authorized personnel and services; audit periodically.
- Data transfers: ensure appropriate safeguards (SCCs) if transferring data outside the EEA.

## Operational Controls
- Rate limiting: per-process fallback, recommend Redis-based global limiter in production.
- Backoff and concurrency: per-domain concurrency cap and exponential backoff on 429/5xx.
- Monitoring: alerts on error spikes, crawl ban signals (403/robots disallow), and quota limits.
- Incident response: document steps to revoke keys, throttle crawlers, and notify stakeholders.

## Checklist
- [ ] Secrets in env/vault, no secrets in code.
- [ ] Robots/ToS enforced; UA includes contact.
- [ ] Rate limits/backoff applied per domain.
- [ ] DSAR deletion flow documented and operational.
- [ ] Logs are PII-minimized; retention configured.
- [ ] Periodic key rotation and access reviews.
