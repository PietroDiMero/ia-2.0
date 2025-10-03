import { ReactNode } from "react"

type BadgeVariant = "default" | "success" | "warning" | "destructive"
export function Badge({ children, variant = "default" }: { children: ReactNode; variant?: BadgeVariant }) {
  const base = "inline-flex items-center rounded px-2 py-0.5 text-xs font-medium"
  const styles: Record<BadgeVariant, string> = {
    default: "bg-neutral-200 text-neutral-800 dark:bg-neutral-800 dark:text-neutral-200",
    success: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200",
    warning: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200",
    destructive: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200",
  }
  return <span className={`${base} ${styles[variant]}`}>{children}</span>
}
