"use client"
import { ReactNode, useState } from "react"
import { ThemeProvider } from "next-themes"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { LangProvider } from "@/lib/i18n"

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient())
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <QueryClientProvider client={queryClient}>
        <LangProvider>{children}</LangProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
