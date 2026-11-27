import { Briefcase, Eye, FileText, Link2, Mail } from 'lucide-react'

import { cn } from '@/lib/utils'
import type { ListingCounts } from '@/lib/types'
import { vacancies as vacancyText } from '@/lib/format'

/** How far a job's candidates got, and its vacancies if given: on listings and the shortlist. */
export function Counts({
  counts,
  vacancies,
  className,
}: {
  counts: ListingCounts
  /** Left out where the vacancies are shown already. */
  vacancies?: number
  className?: string
}) {
  const items = [
    ...(vacancies === undefined ? [] : [{ icon: Briefcase, text: vacancyText(vacancies), label: 'Vacancies' }]),
    { icon: Link2, text: `${counts.connected} connected`, label: 'Connected' },
    { icon: Eye, text: `${counts.revealed} revealed`, label: 'Revealed' },
    { icon: Mail, text: `${counts.requested} asked to apply`, label: 'Asked to apply' },
    {
      icon: FileText,
      text: `${counts.applied} application${counts.applied === 1 ? '' : 's'}`,
      label: 'Applications',
    },
  ]
  return (
    <div
      role="group"
      aria-label="How far candidates got"
      className={cn('flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground', className)}
    >
      {items.map(({ icon: Icon, text, label }) => (
        <span key={label} className="inline-flex items-center gap-1.5" title={label}>
          <Icon className="size-3.5" aria-hidden />
          <span className="tabular-nums">{text}</span>
        </span>
      ))}
    </div>
  )
}
