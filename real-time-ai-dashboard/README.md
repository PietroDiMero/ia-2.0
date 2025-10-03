# real-time-ai-dashboard

End-to-end stack with real-time ingestion and dashboards:
- FastAPI backend with pgvector RAG and Socket.IO real-time metrics
- Celery crawler + Celery Beat scheduler (every 5 minutes)
- PostgreSQL (pgvector) + Redis
- Next.js 14 (TypeScript) frontend with live dashboard

## Quick start

1) Create a .env (see env variables inline in docker-compose.yml) and run:

- docker compose up -d --build

2) Visit:
- Backend: http://localhost:8080/docs
- Frontend: http://localhost:3000

## Services
- backend: FastAPI + Socket.IO (ASGI)
- crawler-worker: Celery worker, performs crawl tasks
- celery-beat: Scheduler triggering crawl every 5 minutes
- db: Postgres with pgvector
- redis: Redis for Celery
- frontend: Next.js app