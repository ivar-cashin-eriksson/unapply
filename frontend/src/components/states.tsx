import { AlertCircle, Loader2, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { describeError } from '@/lib/api'

/** Placeholder lines while a page loads. */
export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-4">
      <Skeleton className="h-8 w-1/3" />
      <Skeleton className="h-4 w-2/3" />
      <div className="space-y-3 pt-4">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    </div>
  )
}

/** An error from the API, in words that say what to do. */
export function ErrorAlert({ error, title = "That didn't work" }: { error: unknown; title?: string }) {
  if (!error) return null
  return (
    <Alert variant="destructive">
      <AlertCircle aria-hidden />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{describeError(error)}</AlertDescription>
    </Alert>
  )
}

/** A friendly empty state: what's missing and what to do next. */
export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon: LucideIcon
  title: string
  children?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed bg-card px-6 py-12 text-center">
      <div className="rounded-full bg-accent p-3 text-primary">
        <Icon className="size-6" aria-hidden />
      </div>
      <h3 className="font-medium">{title}</h3>
      {children && <div className="max-w-md text-sm text-muted-foreground">{children}</div>}
      {action && <div className="pt-2">{action}</div>}
    </div>
  )
}

/** A spinner and a sentence, for steps that take a while. */
export function Working({ children }: { children: ReactNode }) {
  return (
    <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {children}
    </p>
  )
}

/** A page's title, a sentence on what to do, and actions on the right. */
export function PageHeader({
  title,
  children,
  actions,
}: {
  title: string
  children?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="space-y-1.5">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {children && <div className="max-w-2xl text-muted-foreground">{children}</div>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </div>
  )
}
