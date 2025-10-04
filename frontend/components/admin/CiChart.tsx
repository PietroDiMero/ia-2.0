"use client"
import React from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'

export function CiChart({ data }:{ data: Array<any> }){
  const formatted = (data || []).slice().reverse().map((d:any)=>({
    ts: d.ts ? new Date(d.ts).toLocaleString() : '',
    overall: d.overall || 0,
  }))
  return (
    <div style={{ width: '100%', height: 240 }}>
      <ResponsiveContainer>
        <LineChart data={formatted}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="ts" tick={{fontSize:10}} />
          <YAxis domain={[0,1]} tickFormatter={(v)=>String(Math.round((v as number)*100) + '%')} />
          <Tooltip formatter={(v:any)=>[String(v), 'Score']} />
          <Line type="monotone" dataKey="overall" stroke="#8884d8" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default CiChart
