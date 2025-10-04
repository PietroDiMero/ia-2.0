"use client";
import React from 'react'

export function Tabs({ tabs, current, onChange }:{ tabs:{key:string; label:string}[]; current:string; onChange:(k:string)=>void }){
  return (
    <div className="flex flex-wrap gap-2">
      {tabs.map(t => (
        <button
          key={t.key}
          onClick={()=>onChange(t.key)}
          className={`px-3 py-1.5 rounded text-xs font-medium border ${current===t.key? 'bg-indigo-600 border-indigo-500 text-white':'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700'}`}
        >{t.label}</button>
      ))}
    </div>
  )
}
export default Tabs
