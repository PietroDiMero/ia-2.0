"use client";
import React from 'react'

export function Section({ title, children, actions, dense }:{ title:string; children:React.ReactNode; actions?:React.ReactNode; dense?:boolean }){
  return (
    <section className={`rounded border border-slate-800 bg-slate-900/50 ${dense? 'p-3':'p-4'} flex flex-col gap-3`}>
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-sm font-semibold text-slate-200 tracking-wide">{title}</h2>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
      <div>{children}</div>
    </section>
  )
}
export default Section
