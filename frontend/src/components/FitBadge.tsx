import { CircleAlert, Gauge, Trophy } from 'lucide-react'
import { Link } from 'react-router'

import { Badge } from '@/components/ui/badge'
import { fitLabel, placeText } from '@/lib/format'
import type { Fit, FitBand, FitFilter } from '@/lib/types'
import { cn } from '@/lib/utils'

/** Colours per band; the label always says the band, so colour is never the only cue. */
const BAND_STYLE: Record<FitBand, string> = {
  strong: 'border-emerald-300 bg-emerald-50 text-emerald-800',
  good: 'border-sky-300 bg-sky-50 text-sky-800',
  partial: 'border-amber-300 bg-amber-50 text-amber-800',
  low: 'border-slate-300 bg-slate-50 text-slate-700',
}

/** The candidate's fit band for a job, as a badge; with `to`, a link to the board filtered by it. */
export function FitBadge({ band, to }: { band: FitBand; to?: string }) {
  const content = (
    <>
      <Gauge aria-hidden /> {fitLabel(band)}
    </>
  )
  if (to) {
    return (
      <Badge variant="outline" className={cn(BAND_STYLE[band], 'hover:border-primary/60')} asChild>
        <Link to={to} title="From your own levels. Show the jobs with this fit">
          {content}
        </Link>
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className={cn(BAND_STYLE[band])} title="From your own levels">
      {content}
    </Badge>
  )
}

/** The hard filters the candidate doesn't meet, as the ad names them. */
export function MissedFilters({ fit, className, to }: { fit: Fit; className?: string; to?: string }) {
  if (!fit.missed.length) return null
  return (
    // A group, not a list: it sits inside the board's list of jobs.
    <div role="group" aria-label="Requirements you don't meet" className={cn('flex flex-wrap gap-1.5', className)}>
      {fit.missed.map((m) => (
        to ? (
          <Badge key={m.filter} variant="destructive" asChild>
            <Link to={to} title="Show the jobs with a requirement you don't meet">
              <CircleAlert aria-hidden /> {m.label}
            </Link>
          </Badge>
        ) : (
          <Badge key={m.filter} variant="destructive">
            <CircleAlert aria-hidden /> {m.label}
          </Badge>
        )
      ))}
    </div>
  )
}

/**
 * Everything about the fit on a card on the board: band, place, missed filters. With
 * `fitTo`, the band links to the board filtered by it, and the missed filters to the
 * jobs with a requirement you don't meet.
 */
export function FitSummary({ fit, fitTo }: { fit: Fit; fitTo?: (filter: FitFilter) => string }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5" aria-label="Your fit" role="group">
      {fit.band && <FitBadge band={fit.band} to={fitTo?.(fit.band)} />}
      {fit.place && (
        <Badge variant="secondary">
          <Trophy aria-hidden /> {placeText(fit.place)}
        </Badge>
      )}
      <MissedFilters fit={fit} to={fitTo?.('not_met')} />
    </div>
  )
}
