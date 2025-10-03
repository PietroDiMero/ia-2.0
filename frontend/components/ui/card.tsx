import { ReactNode } from "react"

export function Card({ children, className = "" }: { children: ReactNode, className?: string }) {
  return <div className={`rounded-lg border bg-white dark:bg-neutral-900 shadow-sm ${className}`}>{children}</div>
}
export function CardHeader({ children, className = "" }: { children: ReactNode, className?: string }) {
  return <div className={`p-4 border-b ${className}`}>{children}</div>
}
export function CardContent({ children, className = "" }: { children: ReactNode, className?: string }) {
  return <div className={`p-4 ${className}`}>{children}</div>
}
