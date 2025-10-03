"use client"
import Link from "next/link"
import { useTheme } from "next-themes"
import { useI18n } from "@/lib/i18n"
import type { ChangeEvent } from "react"

export function NavBar() {
  const { theme, setTheme } = useTheme()
  const { lang, setLang, t } = useI18n()
  return (
    <div className="w-full border-b sticky top-0 bg-white/70 dark:bg-neutral-950/70 backdrop-blur z-10">
      <div className="max-w-6xl mx-auto flex items-center justify-between p-3 text-sm">
        <div className="flex items-center gap-4">
          <Link className="font-semibold" href="/">Web AI Evolving</Link>
          <Link className="hover:underline" href="/sources">{t("sources")}</Link>
          <Link className="hover:underline" href="/jobs">{t("jobs")}</Link>
          <Link className="hover:underline" href="/index">{t("index")}</Link>
          <Link className="hover:underline" href="/search">{t("search")}</Link>
        </div>
        <div className="flex items-center gap-3">
          <label className="hidden md:block opacity-70">{t("language")}:</label>
          <select
            className="bg-transparent border rounded px-2 py-1"
            value={lang}
            onChange={(e: ChangeEvent<HTMLSelectElement>) => setLang(e.target.value as "fr" | "en")}
          >
            <option value="fr">FR</option>
            <option value="en">EN</option>
          </select>
          <button
            className="border rounded px-2 py-1"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            {t("dark_mode")}
          </button>
        </div>
      </div>
    </div>
  )
}
