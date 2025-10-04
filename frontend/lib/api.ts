import axios, { AxiosError } from "axios"

export const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000"

export const api = axios.create({ baseURL: BACKEND_URL, timeout: 20000 })

// ---- Types ----
export interface CiStatus { overall?: number|null; exact?: number|null; groundedness?: number|null; freshness?: number|null; updated_at?: string|null }
export interface Metrics {
  nb_docs: number; nb_sources: number; last_update: string; documents: number; coverage: number;
  eval_threshold?: number; discovery_queries?: string[]|null; ci?: CiStatus|null;
  retrieval_top_k?: number; confidence_threshold?: number;
  freshness_days?: number|null; avg_response_time?: number|null;
}
export interface Job { task_id?: string; state?: string; status?: string; error?: string; [k: string]: any }
export interface DocItem { url: string; title: string; date?: string|null; lang?: string|null; created_at?: string|null }
export interface PaginatedDocs { items: DocItem[]; total: number; limit: number; offset: number; error?: string }
export interface SourceItem { id: number; url: string; kind?: string; created_at?: string }
export interface EventsItem { ts: string; stage: string; level: string; message: string; meta: Record<string, any> }
export interface SearchResult { query: string; answer: string; citations: { title: string; url: string }[]; confidence: number; sources: [string,string][]; error?: string }
export interface EvaluationResultRow { question: string; answer?: string; exact: number; grounded: number; confidence?: number; citations?: {title:string;url:string}[]; error?: string }
export interface EvaluationRun { status: string; overall: number; exact: number; groundedness: number; freshness?: number|null; avg_freshness_days?: number|null; results: EvaluationResultRow[] }
export interface RuntimeConfig { version: string; env: string; retrieval_top_k: number; confidence_threshold: number; eval_min_overall: number }
export interface EvaluateAsyncStart { status: string; task_id?: string }

function unwrap<T>(p: Promise<{ data: T }>): Promise<T> { return p.then(r=>r.data) }
function safe<T>(fn: ()=>Promise<T>, fallback: T): Promise<T> {
  return fn().catch(()=>fallback)
}

// ---- API helpers ----
export async function getMetrics(): Promise<Metrics> { return unwrap(api.get<Metrics>("/metrics")) }
export async function getRuntimeConfig(): Promise<RuntimeConfig> { return unwrap(api.get<RuntimeConfig>("/config/runtime")) }

export async function getJobs(params?: { type?: string; status?: string }) {
  const { data } = await api.get("/jobs", { params })
  return data as { items: any[]; type?: string; status?: string }
}

export async function postIndexActivate(index_version_id: number, threshold_score = 0) {
  const { data } = await api.post("/index/activate", { index_version_id, threshold_score })
  return data as { status: string; index_version_id: number }
}

export async function postIngestRun(body: { source_ids?: number[]; new_url?: string }) {
  const { data } = await api.post("/ingest/run", body)
  return data as { status: string; task_id?: string }
}

export async function postIndexBuild() {
  const { data } = await api.post("/index/build")
  return data as { status: string; task_id?: string }
}

export async function postEvaluateRun(sets?: string[]) {
  const { data } = await api.post("/evaluate/run", { sets: sets || [] })
  return data as { status: string; task_id?: string }
}
export async function postEvaluateRunAsync(): Promise<EvaluateAsyncStart> {
  return unwrap(api.post<EvaluateAsyncStart>("/evaluate/run_async", {}))
}

export async function getSearch(q: string, k = 5): Promise<SearchResult> {
  return unwrap(api.get<SearchResult>("/search", { params: { q, k } }))
}

// Added: documents latest (placeholder calls backend /docs if exists else fallback empty)
export async function getDocs(limit = 20, offset = 0): Promise<PaginatedDocs> {
  return safe(()=>unwrap(api.get<PaginatedDocs>("/docs", { params: { limit, offset } })), { items: [], total:0, limit, offset })
}

// Sources CRUD
export async function getSources(limit = 30, offset = 0): Promise<{ items: SourceItem[] }> {
  return unwrap(api.get<{ items: SourceItem[] }>("/sources", { params: { limit, offset } }))
}

export async function createSource(item: { url: string; type: string; allowed: boolean }) {
  const { data } = await api.post("/sources", item)
  return data as { id: number }
}

export async function deleteSource(id: number) {
  const { data } = await api.delete(`/sources/${id}`)
  return data as { status: string }
}

export async function testSourceConnectivity(id: number) {
  const { data } = await api.post(`/sources/${id}/test`)
  return data as { ok: boolean; message?: string }
}

// Index versions
export async function getIndexVersions() {
  const { data } = await api.get("/index/versions")
  return data as { items: { id: number; created_at: string; active: boolean; metrics?: any }[] }
}

export async function getRecentEvaluations(limit = 5) {
  const { data } = await api.get("/evaluate/recent", { params: { limit } })
  return data as { items: { id: number; version_id: number; overall_score: number; created_at: string }[] }
}

// Events stream
export async function getEvents(limit = 100): Promise<{ items: EventsItem[] }> {
  return unwrap(api.get<{ items: EventsItem[] }>("/events", { params: { limit } }))
}

// Crawl / Index / Discover triggers (placeholder endpoints assumed)
export async function runCrawl(limit = 50) { return safe(()=>unwrap(api.post("/crawl/run", { limit })), { status:"error" }) }
export async function runIndex(batch = 50) { return safe(()=>unwrap(api.post("/index/run", { batch })), { status:"error" }) }
export async function runDiscover(per_query=5, max_new=25, queries?:string[]) { return safe(()=>unwrap(api.post("/discover/run", { per_query, max_new, queries })), { status:"error" }) }
export async function runDiscoverAsync(per_query=5, max_new=25, queries?:string[]) { return safe(()=>unwrap(api.post("/discover/run_async", { per_query, max_new, queries })), { status:"error" }) }

// Poll job helper
export async function pollJob(task_id: string, timeoutMs = 120000, intervalMs = 2000) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    const { data } = await api.get(`/tasks/${task_id}`)
    if (data.status && data.status !== 'pending' && data.status !== 'running') return data
    await new Promise(r=>setTimeout(r, intervalMs))
  }
  return { status: 'timeout', task_id }
}
