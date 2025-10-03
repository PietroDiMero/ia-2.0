"use client"
import { useState } from "react"
import { getSearch } from "@/lib/api"

export default function SearchPage() {
  const [q, setQ] = useState("")
  const [res, setRes] = useState<null | { answer: string; sources: (string | [string, string])[]; confidence: number }>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSearch() {
    setLoading(true)
    setError(null)
    try {
      const data = await getSearch(q, 5)
      setRes({ answer: data.answer, sources: data.sources || [], confidence: data.confidence ?? 0 })
    } catch (e: any) {
      setError(e?.message || "Erreur")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-4">
      <h1 className="text-2xl font-semibold">Recherche</h1>
      <div className="flex gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="flex-1 border rounded px-3 py-2"
          placeholder="Posez une question…"
        />
        <button onClick={onSearch} disabled={loading} className="px-4 py-2 rounded bg-blue-600 text-white">
          {loading ? "…" : "Chercher"}
        </button>
      </div>
      {error && <div className="text-red-600 text-sm">{error}</div>}
      {res && (
        <div className="space-y-2">
          <div className="font-semibold">Réponse</div>
          <pre className="whitespace-pre-wrap text-sm bg-neutral-50 p-3 rounded border">{res.answer}</pre>
          <div className="text-sm">Confiance: {(res.confidence * 100).toFixed(0)}%</div>
          {res.sources?.length ? (
            <div className="text-sm">
              Sources: {res.sources.map((s, i) => {
                const [title, url] = Array.isArray(s) ? s : [String(s), String(s)]
                return (
                  <a key={i} className="underline text-blue-600 mr-2" href={url} target="_blank">
                    {title}
                  </a>
                )
              })}
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
