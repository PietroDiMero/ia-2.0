import { ReactNode } from "react"

type TableProps = React.ComponentPropsWithoutRef<"table">
type SectionProps = React.ComponentPropsWithoutRef<"thead">
type BodyProps = React.ComponentPropsWithoutRef<"tbody">
type RowProps = React.ComponentPropsWithoutRef<"tr">

export function Table(props: TableProps) {
  const { className, ...rest } = props
  return <table {...rest} className={`w-full text-sm ${className ?? ""}`} />
}
export function Thead(props: SectionProps) {
  const { className, ...rest } = props
  return <thead {...rest} className={`bg-neutral-100 dark:bg-neutral-800 ${className ?? ""}`} />
}
export function Tbody(props: BodyProps) {
  const { className, ...rest } = props
  return <tbody {...rest} className={`${className ?? ""}`} />
}
export function Tr(props: RowProps) {
  const { className, ...rest } = props
  return <tr {...rest} className={`border-b border-neutral-200 dark:border-neutral-800 ${className ?? ""}`} />
}
export function Th({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <th className={`text-left font-medium p-3 ${className}`}>{children}</th>
}
export function Td({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <td className={`p-3 align-top ${className}`}>{children}</td>
}
