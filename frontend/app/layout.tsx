import type { Metadata } from "next"
import "./globals.css"
import { ReactNode } from "react"
import { Providers } from "@/app/providers"
import { NavBar } from "@/components/nav"

export const metadata: Metadata = {
  title: "Web AI Evolving",
  description: "Dashboard",
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fr" suppressHydrationWarning>
      <body>
        <Providers>
          <div className="min-h-screen bg-white text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
            <NavBar />
            {children}
          </div>
        </Providers>
      </body>
    </html>
  )
}
