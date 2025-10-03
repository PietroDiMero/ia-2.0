"use client"
import { useEffect, useRef, useState } from "react"
import io from "socket.io-client"
import { LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip } from "recharts"

type Metrics = {
  nb_docs_total: number
  last_doc_title: string | null
  last_doc_date: string | null
  avg_freshness: number | null
  eval_score: number | null
}

export default function Dashboard() {
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [series, setSeries] = useState<{ t: number; c: number }[]>([])
  const totalRef = useRef(0)
  useEffect(() => {
    const socket = io(typeof window !== 'undefined' ? window.location.origin.replace(':3000', ':8080') : "")
    socket.on("metrics", (m: Metrics) => {
      setMetrics(m)
      if (typeof m.nb_docs_total === 'number' && m.nb_docs_total !== totalRef.current) {
        totalRef.current = m.nb_docs_total
        setSeries((prev) => [...prev.slice(-59), { t: Date.now(), c: m.nb_docs_total }])
      }
    })
    return () => { socket.close() }
  }, [])
  return (
    <div style={{ padding: 24 }}>
      <h1>Real-time Dashboard</h1>
      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ border: '1px solid #ddd', borderRadius: 8, padding: 12 }}>
          <div>Nb docs</div>
          <div style={{ fontSize: 24 }}>{metrics?.nb_docs_total ?? '-'}</div>
        </div>
        <div style={{ border: '1px solid #ddd', borderRadius: 8, padding: 12 }}>
          <div>Dernière mise à jour</div>
          <div style={{ fontSize: 14 }}>{metrics?.last_doc_date ?? '-'}</div>
        </div>
        <div style={{ border: '1px solid #ddd', borderRadius: 8, padding: 12 }}>
          <div>Eval score</div>
          <div>
            <span style={{
              display: 'inline-block', padding: '4px 8px', borderRadius: 8,
              background: (metrics?.eval_score ?? 0) > 0.7 ? '#16a34a' : '#dc2626', color: '#fff'
            }}>{metrics?.eval_score ?? 'n/a'}</span>
          </div>
        </div>
      </div>
      <div style={{ marginTop: 24 }}>
        <h3>Docs over time</h3>
        <LineChart width={700} height={280} data={series.map(s => ({ x: new Date(s.t).toLocaleTimeString(), y: s.c }))}>
          <Line type="monotone" dataKey="y" stroke="#2563eb" />
          <CartesianGrid stroke="#ccc" strokeDasharray="5 5" />
          <XAxis dataKey="x" />
          <YAxis />
          <Tooltip />
        </LineChart>
      </div>
    </div>
  )
}
