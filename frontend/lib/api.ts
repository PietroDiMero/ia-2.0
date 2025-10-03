import axios from "axios"

export const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000"

export const api = axios.create({
  baseURL: BACKEND_URL,
  timeout: 20000,
})

export async function getMetrics() {
  const { data } = await api.get("/metrics")
  return data as {
    documents: number
    coverage: number
    freshness_days: number | null
    avg_response_time: number | null
  }
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
  return data as { status: string; task_id: string }
}

export async function postIndexBuild() {
  const { data } = await api.post("/index/build")
  return data as { status: string; task_id: string }
}

export async function postEvaluateRun(sets?: string[]) {
  const { data } = await api.post("/evaluate/run", { sets: sets || [] })
  return data as { status: string; task_id: string }
}

export async function getSearch(q: string, k = 5) {
  const { data } = await api.get("/search", { params: { q, k } })
  return data as { query: string; answer: string; confidence: number; sources: (string | [string, string])[] }
}

// Sources (CRUD minimal) - endpoints are placeholders; adjust to your backend
export async function getSources() {
  const { data } = await api.get("/sources")
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

// Index versions & evaluations - endpoints as placeholders
export async function getIndexVersions() {
  const { data } = await api.get("/index/versions")
  return data as { items: { id: number; created_at: string; active: boolean; metrics?: any }[] }
}

export async function getRecentEvaluations(limit = 5) {
  const { data } = await api.get("/evaluate/recent", { params: { limit } })
  return data as { items: { id: number; version_id: number; overall_score: number; created_at: string }[] }
}
