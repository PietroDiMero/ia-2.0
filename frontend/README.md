# Frontend (Next.js App Router)

This is a minimal scaffold for the requested dashboard:

- Pages
  - / (Overview): cards for Documents/Coverage/Running Jobs and links to other pages
  - /sources: placeholder for CRUD (URL, type, allowed) + connectivity tests
  - /jobs: list and filters (crawl/index/evaluate) [to wire to backend]
  - /index: versions, metrics, Activate button, diff/rollback [to wire]
  - /search: RAG search with clickable citations [to wire]
- Components
  - Card, Table, Badge, Dialog (shadcn-like)
  - Toast utility
- Client
  - axios + TanStack Query for data fetching
- Theme/i18n
  - next-themes for dark mode, custom i18n provider (fr/en)

Setup

1. Install Node.js 18+ and npm.
2. In this folder:

```powershell
npm install
npm run dev
```

Configure
- Set NEXT_PUBLIC_BACKEND_URL to your backend API, e.g. http://localhost:8000

Notes
- Several API endpoints in lib/api.ts are placeholders and should be aligned with the backend.
- For a production UI, consider adding shadcn/ui directly and design tokens.
