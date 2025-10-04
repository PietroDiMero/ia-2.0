"use client";
import React, { useState } from 'react'
import { getSearch } from '@/lib/api'

export function SearchPanel(){
  const [q, setQ] = useState('')
  const [res, setRes] = useState<any[]|null>(null)
  const [loading, setLoading] = useState(false)
  const run = async ()=>{
    setLoading(true)
    try{
      const data = await getSearch(q, 5)
      setRes(data.items || [])
    }catch(e){
      setRes([])
    }finally{ setLoading(false) }
  }
  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <input value={q} onChange={e=>setQ(e.target.value)} placeholder="question..." className="flex-1 px-3 py-2 bg-slate-800 border border-slate-700 rounded text-sm" />
        <button onClick={run} disabled={loading} className="px-3 py-2 bg-indigo-600 rounded text-xs disabled:opacity-50">Chercher</button>
      </div>
      {loading && <div className="text-xs text-slate-400">Chargement…</div>}
      {res && <ul className="text-xs divide-y divide-slate-800 rounded border border-slate-800 overflow-hidden">
        {res.map((r,i)=>(
          <li key={i} className="p-2 space-y-1 bg-slate-900/40">
            <div className="font-medium text-slate-200">{r.title || r.url || 'Résultat'}</div>
            <div className="text-slate-400 text-[11px] line-clamp-3">{r.snippet || r.text?.slice(0,220) || ''}</div>
          </li>
        ))}
        {res.length===0 && <li className="p-2 text-[11px] text-slate-500">Aucun résultat</li>}
      </ul>}
    </div>
  )
}
export default SearchPanel
