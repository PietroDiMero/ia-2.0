"use client"
import { useEffect, useRef, useState, useMemo } from "react"
import Link from "next/link"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  getMetrics,
  getDocsLatest,
  getSources,
  createSource,
  deleteSource,
  testSourceConnectivity,
  runCrawl,
  runIndex,
  getSearch,
  postIngestRun,
  pollJob,
  getIndexVersions,
  postEvaluateRun,
  runDiscover,
  runDiscoverAsync,
  getEvents,
} from "@/lib/api"
import { BACKEND_URL } from "@/lib/api"
import { KpiCard } from "@/components/admin/KpiCard"
import { Tabs } from "@/components/admin/Tabs"
import { Section } from "@/components/admin/Section"
import { ToggleRow } from "@/components/admin/ToggleRow"
import { SearchPanel } from "@/components/admin/SearchPanel"
import CiChart from "@/components/admin/CiChart"

export default function AdminPage() {
  const qc = useQueryClient()
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: getMetrics, refetchInterval: 5000 })
  const docs = useQuery({ queryKey: ["docs"], queryFn: () => getDocsLatest(15), refetchInterval: 10000 })
  const [srcLimit, setSrcLimit] = useState(30)
  const sources = useQuery({ queryKey: ["sources", srcLimit], queryFn: () => getSources(srcLimit, 0), refetchInterval: 20000 })
  const versions = useQuery({ queryKey: ["versions"], queryFn: getIndexVersions, refetchInterval: 30000 })

  const [newUrl, setNewUrl] = useState("")
  const [searchQ, setSearchQ] = useState("")
  const [searchRes, setSearchRes] = useState<any | null>(null)
  const [message, setMessage] = useState("")
  const [lastResult, setLastResult] = useState<any | null>(null)
  const [discoverQueries, setDiscoverQueries] = useState("")
  const events = useQuery({ queryKey: ["events"], queryFn: () => getEvents(200), refetchInterval: 2000 })
  const live = useQuery({ queryKey: ["events-live"], queryFn: () => getEvents(400), refetchInterval: 1000 })
  const liveRef = useRef<HTMLUListElement | null>(null)
  useEffect(() => { const el = liveRef.current; if (el) el.scrollTop = el.scrollHeight }, [live.data])
  const settings = useQuery({ queryKey: ["settings"], queryFn: async () => {
    const r = await fetch(`${BACKEND_URL}/admin/settings`)
    return r.json()
  } })

  const ciHistory = useQuery({ queryKey: ["ci_history"], queryFn: async () => { const r = await fetch(`${BACKEND_URL}/metrics/history?limit=50`); return r.json() }, refetchInterval: 30000 })

  const mCrawl = useMutation({
    mutationFn: async () => runCrawl(10),
    onSuccess: (data) => { qc.invalidateQueries({ queryKey: ["metrics"] }); setMessage("Crawl lancé"); setLastResult(data) },
    onError: (err: any) => { setMessage("Erreur crawl"); setLastResult(err?.response?.data || String(err)) }
  })
  const mIndex = useMutation({
    mutationFn: async () => runIndex(10),
    onSuccess: (data) => { qc.invalidateQueries({ queryKey: ["metrics"] }); setMessage("Index lancé"); setLastResult(data) },
    onError: (err: any) => { setMessage("Erreur index"); setLastResult(err?.response?.data || String(err)) }
  })
  const mDiscover = useMutation({
    mutationFn: async () => {
      const queries = discoverQueries.split(",").map((q) => q.trim()).filter(Boolean)
      const start = await runDiscoverAsync(5, 25, queries.length ? queries : undefined)
      setLastResult(start)
      setMessage("Discover démarré…")
      if (start.task_id) {
        const res = await pollJob(start.task_id, parseInt(process.env.NEXT_PUBLIC_LONG_TIMEOUT_MS || "300000", 10), 2000)
        return res
      }
      return start
    },
    onSuccess: (data) => { qc.invalidateQueries({ queryKey: ["sources"] }); setMessage("Discover terminé"); setLastResult(data) },
    onError: (err: any) => { setMessage("Erreur discover"); setLastResult(err?.response?.data || String(err)) }
  })
  const mRunOnce = useMutation({
    mutationFn: async () => {
      const start = await postIngestRun({ new_url: newUrl || undefined })
      setLastResult(start)
      setMessage("Run once démarré en arrière-plan…")
      if (start.task_id) {
        const res = await pollJob(start.task_id, parseInt(process.env.NEXT_PUBLIC_LONG_TIMEOUT_MS || "300000", 10), 2000)
        return res
      }
      return start
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["metrics"] })
      setMessage("Run once terminé")
      setLastResult(data)
    },
    onError: (err: any) => { setMessage("Erreur run once"); setLastResult(err?.response?.data || String(err)) }
  })
  const mEval = useMutation({
    mutationFn: async () => postEvaluateRun([]),
    onSuccess: (data) => { setMessage("Évaluation lancée"); setLastResult(data) },
    onError: (err: any) => { setMessage("Erreur évaluation"); setLastResult(err?.response?.data || String(err)) }
  })

  const mSeedFromDocs = useMutation({
    mutationFn: async () => {
      const r = await fetch(`${BACKEND_URL}/evolve/seed_from_docs`, { method: "POST" })
      return r.json()
    },
    onSuccess: (data) => { setMessage("Seed from docs exécuté"); setLastResult(data) },
    onError: (err: any) => { setMessage("Erreur seed_from_docs"); setLastResult(String(err)) }
  })

  const mTriggerEvolve = useMutation({
    mutationFn: async () => {
      const r = await fetch(`${BACKEND_URL}/evolve/run`, { method: "POST" })
      return r.json()
    },
    onSuccess: (data) => { setMessage("Workflow auto-evolve déclenché"); setLastResult(data) },
    onError: (err: any) => { setMessage("Erreur evolve/run"); setLastResult(String(err)) }
  })

  const [discLocal, setDiscLocal] = useState<string>("")
  useEffect(() => {
    const arr = settings.data?.items?.DISCOVERY_QUERIES?.queries || metrics.data?.discovery_queries
    if (Array.isArray(arr)) setDiscLocal(arr.join(", "))
    else if (typeof arr === "string") setDiscLocal(arr)
  }, [settings.data, metrics.data])

  const mSaveDiscovery = useMutation({
    mutationFn: async () => {
      const arr = discLocal.split(",").map(s => s.trim()).filter(Boolean)
      const r = await fetch(`${BACKEND_URL}/admin/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: "DISCOVERY_QUERIES", value: { queries: arr } })
      })
      return r.json()
    },
    onSuccess: () => { setMessage("Queries sauvegardées"); qc.invalidateQueries({ queryKey: ["settings"] }) },
    onError: (err: any) => { setMessage("Erreur sauvegarde queries"); setLastResult(String(err)) }
  })

  const boolFrom = (v: any) => {
    if (typeof v === 'boolean') return v
    if (typeof v === 'number') return v !== 0
    if (typeof v === 'string') return ['1','true','yes','on'].includes(v.toLowerCase())
    if (v && typeof v === 'object' && 'enabled' in v) return boolFrom((v as any).enabled)
    return false
  }
  const evVerbose = boolFrom(settings.data?.items?.EVENTS_VERBOSE)
  const obeyRobots = boolFrom(settings.data?.items?.CRAWLER_OBEY_ROBOTS ?? '1')
  const toggleSetting = async (key: string, next: boolean) => {
    await fetch(`${BACKEND_URL}/admin/settings`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, value: { enabled: next } })
    })
    qc.invalidateQueries({ queryKey: ["settings"] })
  }

  const mCreateSource = useMutation({
    mutationFn: async () => { if (!newUrl) return; return createSource({ url: newUrl, type: "html", allowed: true }) },
    onSuccess: (data) => { qc.invalidateQueries({ queryKey: ["sources"] }); setNewUrl(""); setMessage("Source créée"); setLastResult(data) },
    onError: (err: any) => { setMessage("Erreur création source"); setLastResult(err?.response?.data || String(err)) }
  })

  const [tab, setTab] = useState<string>("observability")
  const tabs = useMemo(() => ([
    { key: 'observability', label: 'Observabilité' },
    { key: 'search', label: 'Recherche' },
    { key: 'sources', label: 'Sources & Ingestion' },
    { key: 'evolve', label: 'Évolution / CI' },
    { key: 'settings', label: 'Paramètres' },
  ]), [])

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur px-6 py-4 flex items-center justify-between gap-6">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-semibold tracking-wide text-slate-100">AI Admin Console</h1>
          <nav className="hidden md:flex gap-4 text-xs text-slate-400">
            <Link className="hover:text-slate-200" href="/">Accueil</Link>
            <Link className="hover:text-slate-200" href="/dashboard">Dashboard</Link>
            <a className="hover:text-slate-200" href={`${BACKEND_URL}/health`} target="_blank">Health</a>
          </nav>
        </div>
        <div className="flex gap-2 text-xs text-slate-400">
          <span>Docs: <strong className="text-slate-200">{metrics.data?.documents ?? 0}</strong></span>
          <span>CI: <strong className="text-slate-200">{metrics.data?.ci?.overall ?? '-'}</strong></span>
        </div>
      </header>
      <main className="flex-1 px-6 py-5 space-y-6 max-w-7xl w-full mx-auto">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <KpiCard label="Documents" value={metrics.data?.documents ?? 0} />
          <KpiCard label="Couverture" value={`${Math.round((metrics.data?.coverage ?? 0) * 100)}%`} />
            <KpiCard label="Fraîcheur" value={metrics.data?.freshness_days ?? '–'} />
            <KpiCard label="Temps moyen" value={metrics.data?.avg_response_time ?? '–'} />
          <KpiCard label="CI Overall" value={metrics.data?.ci?.overall ?? '–'} />
        </div>
        <Tabs tabs={tabs} current={tab} onChange={setTab} />

        {tab === 'observability' && (
          <div className="grid lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 flex flex-col gap-6">
              <Section title="Actions rapides" actions={<div className="flex flex-wrap gap-2">
                <button className="px-3 py-2 bg-indigo-600 rounded text-xs hover:bg-indigo-500" onClick={() => mRunOnce.mutate()}>Run Once</button>
                <button className="px-3 py-2 bg-indigo-600 rounded text-xs hover:bg-indigo-500" onClick={() => mDiscover.mutate()}>Discover</button>
                <button className="px-3 py-2 bg-indigo-600 rounded text-xs hover:bg-indigo-500" onClick={() => mCrawl.mutate()}>Crawler</button>
                <button className="px-3 py-2 bg-indigo-600 rounded text-xs hover:bg-indigo-500" onClick={() => mIndex.mutate()}>Indexer</button>
                <button className="px-3 py-2 bg-indigo-600 rounded text-xs hover:bg-indigo-500" onClick={() => mEval.mutate()}>Évaluer</button>
                <button className="px-3 py-2 bg-indigo-600 rounded text-xs hover:bg-indigo-500" onClick={() => mSeedFromDocs.mutate()}>Seed docs</button>
                <button className="px-3 py-2 bg-indigo-600 rounded text-xs hover:bg-indigo-500" onClick={() => mTriggerEvolve.mutate()}>Evolve CI</button>
              </div>}>
                <div className="text-xs text-slate-400 leading-relaxed">
                  {message || 'Surveille les logs pour l’exécution des jobs. Les actions longues sont asynchrones.'}
                </div>
                {lastResult && <pre className="text-[10px] bg-slate-950/70 border border-slate-800 rounded p-2 max-h-56 overflow-auto">{JSON.stringify(lastResult, null, 2)}</pre>}
              </Section>
              <Section title="Logs en temps réel">
                <ul ref={liveRef} className="text-[11px] divide-y divide-slate-800 max-h-[420px] overflow-auto leading-relaxed">
                  {(live.data?.items || []).map((e: any, i: number) => {
                    const stageColor = e.stage === 'discover' ? 'bg-amber-600/60' : e.stage === 'crawl' ? 'bg-indigo-600/60' : e.stage === 'index' ? 'bg-emerald-600/60' : e.stage === 'evolve' ? 'bg-purple-600/60' : 'bg-slate-700/60'
                    const levelColor = e.level === 'error' ? 'text-rose-400' : e.level === 'warn' ? 'text-amber-300' : 'text-slate-400'
                    const meta = typeof e.meta === 'string' ? e.meta : JSON.stringify(e.meta, null, 0)
                    return (
                      <li key={i} className="py-2">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-slate-500 tabular-nums">{e.ts}</span>
                          <span className={`px-1 rounded text-[10px] uppercase tracking-wide text-white ${stageColor}`}>{e.stage}</span>
                          <span className={`text-[10px] font-medium ${levelColor}`}>{e.level}</span>
                          <span className="flex-1 text-slate-200 break-words">{e.message}</span>
                        </div>
                        {e.meta && <pre className="mt-1 ml-2 bg-slate-950/40 p-1 rounded text-[10px] text-slate-400 whitespace-pre-wrap break-words">{meta}</pre>}
                      </li>
                    )
                  })}
                </ul>
              </Section>
              <Section title="Trend CI Score">
                <CiChart data={ciHistory.data?.items || []} />
                <div className="text-xs text-slate-300 mt-2">Dernier score: <strong className="text-slate-100">{ciHistory.data?.items?.[0]?.overall ?? '-'}</strong></div>
              </Section>
            </div>
            <div className="flex flex-col gap-6">
              <Section title="Événements">
                <ul className="text-[11px] divide-y divide-slate-800 max-h-[420px] overflow-auto">
                  {(events.data?.items || []).map((e: any, i: number) => (
                    <li key={i} className="py-2 space-y-1">
                      <div className="flex items-center gap-2 flex-wrap text-slate-400">
                        <span className="tabular-nums">{e.ts}</span>
                        <span className="text-slate-300">{e.stage}</span>
                        <span className="text-slate-500">{e.level}</span>
                      </div>
                      <div className="text-slate-200 text-xs break-words">{e.message}</div>
                    </li>
                  ))}
                </ul>
              </Section>
              <Section title="Derniers documents">
                <ul className="text-xs divide-y divide-slate-800 max-h-[300px] overflow-auto">
                  {(docs.data?.items || []).map((d, i) => (
                    <li key={i} className="py-2">
                      <a className="underline decoration-dotted" href={d.url} target="_blank" rel="noreferrer">{d.title || d.url}</a>
                      <div className="text-[10px] text-slate-500 mt-0.5">{d.lang || 'und'} · {d.date || ''}</div>
                    </li>
                  ))}
                </ul>
              </Section>
              <Section title="Index versions" dense>
                <ul className="text-[11px] text-slate-400 space-y-1">
                  {(versions.data?.items || []).length === 0 && <li>Aucune version</li>}
                  {(versions.data?.items || []).map((v: any) => <li key={v.id}>#{v.id} {v.active ? '(actif)' : ''}</li>)}
                </ul>
              </Section>
            </div>
          </div>
        )}

        {tab === 'search' && (
          <div className="grid md:grid-cols-3 gap-6">
            <div className="md:col-span-2">
              <Section title="Recherche & QA">
                <SearchPanel />
              </Section>
            </div>
            <div className="flex flex-col gap-6">
              <Section title="Toggles (runtime)">
                <ToggleRow label="Logs verbeux" description="Ajoute des étapes détaillées" active={evVerbose} onToggle={(n) => toggleSetting('EVENTS_VERBOSE', n)} />
                <ToggleRow label="Respect robots.txt" description="Crawler suit robots.txt" active={obeyRobots} onToggle={(n) => toggleSetting('CRAWLER_OBEY_ROBOTS', n)} />
              </Section>
              <Section title="CI / Qualité" dense>
                <div className="text-xs space-y-1 text-slate-300">
                  <div>Score global: {metrics.data?.ci?.overall ?? '–'}</div>
                  <div>Exact / Grounded: {metrics.data?.ci?.exact ?? '–'} / {metrics.data?.ci?.groundedness ?? '–'}</div>
                  <div>Seuil Merge: {metrics.data?.eval_threshold ?? '–'}</div>
                </div>
              </Section>
            </div>
          </div>
        )}

        {tab === 'sources' && (
          <div className="grid lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 flex flex-col gap-6">
              <Section title="Sources">
                <div className="flex gap-2 mb-3">
                  <input className="flex-1 px-3 py-2 bg-slate-800 rounded border border-slate-700 text-sm" placeholder="https://..." value={newUrl} onChange={(e) => setNewUrl(e.target.value)} />
                  <button className="px-3 py-2 bg-indigo-600 rounded text-xs" onClick={() => mCreateSource.mutate()}>Ajouter</button>
                </div>
                <ul className="text-xs divide-y divide-slate-800 max-h-[420px] overflow-auto">
                  {(sources.data?.items || []).map((s) => (
                    <li key={s.id} className="py-2 flex items-center gap-2">
                      <span className="truncate flex-1" title={s.url}>{s.url}</span>
                      <span className="text-slate-500">{s.type}</span>
                      <button className="px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 text-[10px]" onClick={async () => alert(JSON.stringify(await testSourceConnectivity(s.id)))}>Test</button>
                      <button className="px-2 py-1 rounded bg-rose-700 hover:bg-rose-600 text-[10px]" onClick={async () => { await deleteSource(s.id); qc.invalidateQueries({ queryKey: ['sources'] }) }}>X</button>
                    </li>
                  ))}
                </ul>
                <div className="mt-3 flex justify-center">
                  <button className="px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 text-xs" onClick={() => setSrcLimit(n => n + 30)}>Plus</button>
                </div>
              </Section>
              <Section title="Ingestion / Pipeline" dense>
                <div className="flex flex-wrap gap-2 text-[11px] text-slate-300">
                  <button className="px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-500" onClick={() => mRunOnce.mutate()}>Run Once</button>
                  <button className="px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-500" onClick={() => mDiscover.mutate()}>Discover</button>
                  <button className="px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-500" onClick={() => mCrawl.mutate()}>Crawler</button>
                  <button className="px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-500" onClick={() => mIndex.mutate()}>Indexer</button>
                </div>
              </Section>
            </div>
            <div className="flex flex-col gap-6">
              <Section title="Docs récents">
                <ul className="text-xs divide-y divide-slate-800 max-h-[420px] overflow-auto">
                  {(docs.data?.items || []).map((d, i) => (
                    <li key={i} className="py-2">
                      <a className="underline decoration-dotted" href={d.url} target="_blank" rel="noreferrer">{d.title || d.url}</a>
                      <div className="text-[10px] text-slate-500">{d.lang || 'und'} · {d.date || ''}</div>
                    </li>
                  ))}
                </ul>
              </Section>
            </div>
          </div>
        )}

        {tab === 'evolve' && (
          <div className="grid md:grid-cols-2 gap-6">
            <Section title="Évolution & CI">
              <div className="flex flex-wrap gap-2 mb-4">
                <button className="px-3 py-2 bg-indigo-600 rounded text-xs" onClick={() => mSeedFromDocs.mutate()}>Seed from docs</button>
                <button className="px-3 py-2 bg-indigo-600 rounded text-xs" onClick={() => mTriggerEvolve.mutate()}>Déclencher auto-evolve</button>
                <button className="px-3 py-2 bg-indigo-600 rounded text-xs" onClick={() => mEval.mutate()}>Évaluer</button>
              </div>
              <div className="grid grid-cols-2 gap-3 text-[11px] text-slate-300">
                <div>Overall: <span className="text-slate-100">{metrics.data?.ci?.overall ?? '–'}</span></div>
                <div>Exact: <span className="text-slate-100">{metrics.data?.ci?.exact ?? '–'}</span></div>
                <div>Grounded: <span className="text-slate-100">{metrics.data?.ci?.groundedness ?? '–'}</span></div>
                <div>Seuil: <span className="text-slate-100">{metrics.data?.eval_threshold ?? '–'}</span></div>
              </div>
              {lastResult && <pre className="mt-4 text-[10px] bg-slate-950/70 border border-slate-800 rounded p-2 max-h-56 overflow-auto">{JSON.stringify(lastResult, null, 2)}</pre>}
            </Section>
            <Section title="Résultat dernière action" dense>
              <div className="text-[11px] text-slate-300">{message || 'Aucune action lancée.'}</div>
              {lastResult && <pre className="mt-3 text-[10px] bg-slate-950/60 border border-slate-800 rounded p-2 max-h-80 overflow-auto">{JSON.stringify(lastResult, null, 2)}</pre>}
            </Section>
          </div>
        )}

        {tab === 'settings' && (
          <div className="grid md:grid-cols-2 gap-6">
            <Section title="Toggles runtime">
              <ToggleRow label="Logs verbeux (EVENTS_VERBOSE)" active={evVerbose} onToggle={(n) => toggleSetting('EVENTS_VERBOSE', n)} />
              <ToggleRow label="Respect robots.txt" active={obeyRobots} onToggle={(n) => toggleSetting('CRAWLER_OBEY_ROBOTS', n)} />
            </Section>
            <Section title="Discovery queries">
              <div className="space-y-2">
                <input className="w-full px-3 py-2 bg-slate-800 rounded border border-slate-700 text-sm" placeholder="queries séparées par virgule" value={discLocal} onChange={(e) => setDiscLocal(e.target.value)} />
                <button className="px-3 py-2 bg-indigo-600 rounded text-xs" onClick={() => mSaveDiscovery.mutate()}>Sauver</button>
              </div>
            </Section>
          </div>
        )}
      </main>
    </div>
  )
}
