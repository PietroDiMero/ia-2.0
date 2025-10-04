"use client";
import React from 'react'

export function ToggleRow({ label, description, active, onToggle }:{ label:string; description?:string; active:boolean; onToggle:(n:boolean)=>void }){
  return (
    <div className="flex items-start justify-between gap-4 py-2">
      <div className="flex-1">
        <div className="text-xs font-medium text-slate-200">{label}</div>
        {description && <div className="text-[10px] text-slate-500 mt-0.5">{description}</div>}
      </div>
      <button
        onClick={()=>onToggle(!active)}
        className={`w-10 h-5 rounded-full relative transition-colors duration-200 text-[10px] ${active? 'bg-indigo-600':'bg-slate-700'}`}
        aria-pressed={active}
      >
        <span className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white transition-transform duration-200 ${active? 'translate-x-5':''}`}></span>
      </button>
    </div>
  )
}
export default ToggleRow
