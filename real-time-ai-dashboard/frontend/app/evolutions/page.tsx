"use client"
import { useEffect, useState } from "react"

type Entry = { timestamp: string; branch: string; patch_file?: string; pr?: { number?: number; html_url?: string; state?: string } }

export default function Evolutions() {
  const [items, setItems] = useState<Entry[]>([])
  useEffect(() => {
    const base = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8080"
    fetch(base + "/evolver/history")
      .then(r => r.ok ? r.json() : [])
      .then(setItems)
      .catch(() => setItems([]))
  }, [])
  return (
    <div style={{ padding: 24 }}>
      <h1>Évolutions</h1>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>Date</th>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>Branche</th>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>PR</th>
            <th style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>Statut</th>
          </tr>
        </thead>
        <tbody>
          {items.map((e, i) => (
            <tr key={i}>
              <td style={{ padding: 8 }}>{new Date(e.timestamp).toLocaleString()}</td>
              <td style={{ padding: 8 }}>{e.branch}</td>
              <td style={{ padding: 8 }}>
                {e.pr?.html_url ? <a href={e.pr.html_url} target="_blank" rel="noreferrer">PR #{e.pr.number}</a> : "-"}
              </td>
              <td style={{ padding: 8 }}>
                <span style={{
                  display: 'inline-block', padding: '2px 8px', borderRadius: 8,
                  background: e.pr?.state === 'merged' ? '#16a34a' : '#dc2626', color: '#fff'
                }}>{e.pr?.state ?? 'en attente'}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
