import axios from "axios"

export const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000"

export const api = axios.create({
  baseURL: BACKEND_URL,
  timeout: 20000,
})

export async function getMetrics() {
  const { data } = await api.get("/metrics")
  return data as any
}

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

export async function getSearch(q: string, k = 5) {
  const { data } = await api.get("/search", { params: { q, k } })
  return data as any
}

// Added: documents latest (placeholder calls backend /docs if exists else fallback empty)
export async function getDocsLatest(limit = 15) {
  try {
    const { data } = await api.get("/docs", { params: { limit } })
    return data as { items: any[] }
  } catch {
    return { items: [] }
  }
}

// Sources CRUD
export async function getSources(limit = 30, offset = 0) {
  const { data } = await api.get("/sources", { params: { limit, offset } })
  return data as { items: { id: number; url: string; type: string; allowed: boolean }[] }
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
export async function getEvents(limit = 100) {
  const { data } = await api.get("/events", { params: { limit } })
  return data as { items: any[] }
}

// Crawl / Index / Discover triggers (placeholder endpoints assumed)
export async function runCrawl(limit = 50) {
  try { const { data } = await api.post("/crawl/run", { limit }); return data } catch(e:any){ return { error: String(e) } }
}
export async function runIndex(batch = 50) {
  try { const { data } = await api.post("/index/run", { batch }); return data } catch(e:any){ return { error: String(e) } }
}
export async function runDiscover(per_query=5, max_new=25) {
  try { const { data } = await api.post("/discover/run", { per_query, max_new }); return data } catch(e:any){ return { error: String(e) } }
}
export async function runDiscoverAsync(per_query=5, max_new=25, queries?:string[]) {
  try { const { data } = await api.post("/discover/run_async", { per_query, max_new, queries }); return data } catch(e:any){ return { error: String(e) } }
}

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
