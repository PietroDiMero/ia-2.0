"use client"
import { createContext, useContext, useState } from "react"

type Toast = { id: number; message: string }

const ToastCtx = createContext<{ add: (msg: string) => void }>({ add: (_msg: string) => {} })

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  function add(message: string) {
    const id = Date.now() + Math.random()
    setItems((prev) => [...prev, { id, message }])
    setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== id)), 3000)
  }
  return (
    <ToastCtx.Provider value={{ add }}>
      {children}
      <div className="fixed right-4 top-16 space-y-2 z-50">
        {items.map((t) => (
          <div key={t.id} className="rounded bg-neutral-900 text-white px-3 py-2 shadow">
            {t.message}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export function useToast() {
  return useContext(ToastCtx)
}
