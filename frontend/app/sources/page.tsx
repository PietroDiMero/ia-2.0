"use client"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { useI18n } from "@/lib/i18n"

export default function SourcesPage() {
  const { t } = useI18n()
  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-semibold">{t("sources")}</h1>
      <Card>
        <CardHeader>{t("connectivity")}</CardHeader>
        <CardContent>
          <p className="text-sm text-neutral-600 dark:text-neutral-300">CRUD minimal à implémenter (URL, type, allowed) + tests de connectivité.</p>
        </CardContent>
      </Card>
    </div>
  )
}
