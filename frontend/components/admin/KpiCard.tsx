"use client";
import React from "react";

export function KpiCard({ label, value, sub }:{ label:string; value:React.ReactNode; sub?:React.ReactNode }){
  return (
    <div className="rounded border border-slate-800 bg-slate-900/60 p-3 flex flex-col gap-1">
      <div className="text-[10px] uppercase tracking-wide text-slate-500 font-medium">{label}</div>
      <div className="text-lg font-semibold text-slate-100 tabular-nums">{value}</div>
      {sub && <div className="text-[10px] text-slate-500">{sub}</div>}
    </div>
  );
}
export default KpiCard;
