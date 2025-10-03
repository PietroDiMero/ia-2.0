"use client"
import { createContext, useContext, useEffect, useState, type ReactNode } from "react"

type Lang = "fr" | "en"

const dict = {
  fr: {
    overview: "Aperçu",
    sources: "Sources",
    documents: "Documents",
    index_versions: "Versions d'index",
    running_jobs: "Jobs en cours",
    last_evaluations: "Dernières évaluations",
    jobs: "Jobs",
    index: "Index",
    search: "Recherche",
    activate: "Activer",
    rollback: "Rollback",
    connectivity: "Connectivité",
    url: "URL",
    type: "Type",
    allowed: "Autorisé",
    add: "Ajouter",
    delete: "Supprimer",
    status: "Statut",
    logs: "Logs",
    details: "Détails",
    freshness: "Fraîcheur",
    eval_scores: "Scores d'évaluation",
    query: "Requête",
    answer: "Réponse",
    sources_label: "Citations",
    submit: "Envoyer",
    language: "Langue",
    dark_mode: "Mode sombre"
  },
  en: {
    overview: "Overview",
    sources: "Sources",
    documents: "Documents",
    index_versions: "Index versions",
    running_jobs: "Running jobs",
    last_evaluations: "Latest evaluations",
    jobs: "Jobs",
    index: "Index",
    search: "Search",
    activate: "Activate",
    rollback: "Rollback",
    connectivity: "Connectivity",
    url: "URL",
    type: "Type",
    allowed: "Allowed",
    add: "Add",
    delete: "Delete",
    status: "Status",
    logs: "Logs",
    details: "Details",
    freshness: "Freshness",
    eval_scores: "Eval scores",
    query: "Query",
    answer: "Answer",
    sources_label: "Citations",
    submit: "Submit",
    language: "Language",
    dark_mode: "Dark mode"
  }
} as const

type Dict = typeof dict
type Key = keyof Dict["fr"]

const LangCtx = createContext<{ lang: Lang; setLang: (l: Lang) => void; t: (k: Key) => string }>({
  lang: "fr",
  setLang: (_l: Lang) => {},
  t: (k: Key) => k,
})

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>("fr")
  useEffect(() => {
    const saved = typeof window !== "undefined" ? (window.localStorage.getItem("lang") as Lang | null) : null
    if (saved === "fr" || saved === "en") setLang(saved)
  }, [])
  useEffect(() => {
    if (typeof window !== "undefined") window.localStorage.setItem("lang", lang)
  }, [lang])
  const t = (k: Key) => dict[lang][k] ?? (k as string)
  return <LangCtx.Provider value={{ lang, setLang, t }}>{children}</LangCtx.Provider>
}

export function useI18n() {
  return useContext(LangCtx)
}
