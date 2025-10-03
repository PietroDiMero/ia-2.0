"use client"
import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { getMetrics, getJobs } from "@/lib/api"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { useI18n } from "@/lib/i18n"

export default function OverviewPage() {
  const { t } = useI18n()
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: getMetrics })
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: () => getJobs({ status: "running" }) })
  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-semibold">{t("overview")}</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <Card>
          <CardHeader>{t("documents")}</CardHeader>
          <CardContent>
            <div className="text-3xl">{metrics.data?.documents ?? "-"}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>Coverage</CardHeader>
          <CardContent>
            <div className="text-3xl">{metrics.data ? Math.round(metrics.data.coverage * 100) + "%" : "-"}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>{t("running_jobs")}</CardHeader>
          <CardContent>
            <div className="text-3xl">{jobs.data?.items?.length ?? 0}</div>
          </CardContent>
        </Card>
      </div>

      <div className="flex gap-4">
        <Link className="underline" href="/sources">{t("sources")}</Link>
        <Link className="underline" href="/jobs">{t("jobs")}</Link>
        <Link className="underline" href="/index">{t("index")}</Link>
        <Link className="underline" href="/search">{t("search")}</Link>
      </div>
    </div>
  )
}
