import {
  ArrowLeft,
  Briefcase,
  Building2,
  Check,
  ChevronDown,
  Download,
  Eye,
  IdCard,
  Link2,
  Link2Off,
  Loader2,
  Mail,
  MapPin,
  MessagesSquare,
  PlayCircle,
  Search,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  X,
} from 'lucide-react'
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { AdText } from '@/components/AdText'
import { Counts } from '@/components/Counts'
import { FitBadge, FitSummary, MissedFilters } from '@/components/FitBadge'
import { MessageThread, UnreadBadge } from '@/components/MessageThread'
import { StageBadge } from '@/components/StageBadge'
import { WhyDisabled } from '@/components/WhyDisabled'
import { EmptyState, ErrorAlert, Loading, PageHeader } from '@/components/states'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { api } from '@/lib/api'
import {
  adSummary,
  day,
  FIT_FILTERS,
  minVacancies,
  permitLabel,
  placeText,
  seniorityLabel,
  SENIORITIES,
  vacancies,
  workModeLabel,
} from '@/lib/format'
import type { Board, BoardQuery, BoardSort, Connection, Fit, FitFilter, Listing } from '@/lib/types'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'
import {
  activeFilters,
  filterLabel,
  filterQuery,
  withFilter,
  withoutFilter,
  type ActiveFilter,
  type FilterKey,
} from '@/pages/candidate/boardFilters'
import { useCandidate } from '@/pages/candidate/context'

/** Wait this long after the last key before searching, in milliseconds. */
const SEARCH_DELAY = 250

/** Skills shown on a card on the board; the listing shows them all. */
const CARD_SKILLS = 6

/** Where a pill links to: the board filtered by it. */
type FilterTo = (key: FilterKey, value: string) => string

/** Filters the advanced section holds; it opens by itself when one is on. */
const ADVANCED: FilterKey[] = ['work_permit', 'min_vacancies', 'skill']

/**
 * Connect the candidate's profile to a job, or withdraw it, and say so.
 *
 * The board's cards and the listing both use this, so the two act the same; the server
 * refuses unapproved profiles and withdrawals after a reveal.
 */
async function changeConnection(name: string, job: string, company: string, connect: boolean) {
  if (connect) {
    await api.connect(name, job)
    toast.success(`Your profile is connected to ${company}.`)
  } else {
    await api.withdraw(name, job)
    toast.success(`You withdrew from ${company}.`)
  }
}

/** The job board: browse and search the listings, and see which you connected to. */
export function JobBoard() {
  const { name, summary } = useCandidate()
  const [text, setText] = useState('')
  const [q, setQ] = useState('')
  // The filters live in the address, so pills can link to the board filtered by them.
  const [params, setSearchParams] = useSearchParams()
  // The router applies a change to the address in a transition, so a filter set
  // right after another (such as just after "Clear filters") would start from the
  // old params and undo it. Changes start from the latest params set instead.
  const latest = useRef(params)
  useEffect(() => {
    latest.current = params
  }, [params])
  function setParams(next: URLSearchParams | Record<string, string>) {
    latest.current = new URLSearchParams(next)
    setSearchParams(latest.current, { replace: true })
  }
  const active = activeFilters(params)
  const fitFilter = (params.get('fit') as FitFilter | null) ?? ''
  const [sort, setSort] = useState<BoardSort>('newest')
  const [advanced, setAdvanced] = useState(() => active.some((f) => ADVANCED.includes(f.key)))
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    const timer = setTimeout(() => setQ(text.trim()), SEARCH_DELAY)
    return () => clearTimeout(timer)
  }, [text])

  const query: BoardQuery = {
    q: q || undefined,
    ...filterQuery(params),
    // The server works out the fit for these from the candidate's own levels.
    ...(fitFilter || sort === 'fit'
      ? { candidate: name, fit: fitFilter || undefined, sort: sort === 'fit' ? sort : undefined }
      : {}),
  }
  const loaded = useResource(() => api.board(query), JSON.stringify(query))
  // Keep showing the last board while the next search loads, so the filters stay put
  // (and keep focus) instead of making way for a loading state on every change.
  const [last, setLast] = useState<Board | undefined>(undefined)
  if (loaded.data && loaded.data !== last) setLast(loaded.data)
  const board = { ...loaded, data: loaded.data ?? (loaded.error ? undefined : last) }
  const connections = useResource(() => api.connections(name), name)
  const connectionOf = new Map((connections.data ?? []).map((c) => [c.job, c]))
  const requests = (connections.data ?? []).filter((c) => c.stage === 'requested' && c.listing)
  // How well you fit each job; the board works without it if it can't load.
  const fits = useResource(() => api.fits(name), `${name}:${board.data?.total ?? 0}`)
  const fitOf = new Map((fits.data ?? []).map((f) => [f.job, f]))
  // Without a profile there is no band, so nothing to filter or sort by.
  const byFit = (fits.data ?? []).some((f) => f.band)
  const filtered = Boolean(q || active.length)
  // The job whose connection is changing, and the error if that failed.
  const [changing, setChanging] = useState<string | null>(null)
  const [changeError, setChangeError] = useState<{ job: string; error: unknown } | null>(null)

  async function change(x: Listing, connect: boolean) {
    setChanging(x.name)
    setChangeError(null)
    try {
      await changeConnection(name, x.name, x.company, connect)
      // The card's action is ready again once the connection shows. Working out the
      // fit for every listing can take a while, so it updates on its own afterwards.
      void fits.reload()
      await connections.reload()
    } catch (e) {
      setChangeError({ job: x.name, error: e })
    } finally {
      setChanging(null)
    }
  }

  /** Set one filter from its select; an empty value turns it off. */
  function setFilter(key: FilterKey, value: string) {
    const next = new URLSearchParams(latest.current)
    next.delete(key)
    setParams(value ? withFilter(next, key, value) : next)
  }

  const filterTo: FilterTo = (key, value) => `?${withFilter(params, key, value)}`

  function clear() {
    setText('')
    setQ('')
    setParams({})
  }

  async function addDemoJobs() {
    setAdding(true)
    setError(null)
    try {
      const { jobs } = await api.createBoardDemo()
      toast.success(`${jobs.length} demo jobs are on the board.`)
      await board.reload()
    } catch (e) {
      setError(e)
    } finally {
      setAdding(false)
    }
  }

  const header = (
    <PageHeader
      title="Find jobs"
      actions={
        // Demo candidates can always add the demo jobs; adding them again changes nothing.
        summary.demo && (board.data?.total ?? 0) > 0 ? (
          <Button variant="outline" onClick={addDemoJobs} disabled={adding}>
            <PlayCircle aria-hidden /> Add the demo jobs
          </Button>
        ) : undefined
      }
    >
      Read the jobs on the board and connect your profile to the ones you want. A job you
      connect to can match and rank you anonymously; the employer only learns who you are if
      they reveal you.
    </PageHeader>
  )

  if (!board.data) {
    return (
      <>
        {header}
        {board.error ? <ErrorAlert error={board.error} title="Couldn't load the job board" /> : <Loading label="Loading the job board" />}
      </>
    )
  }
  const b = board.data

  if (b.total === 0) {
    return (
      <>
        {header}
        <EmptyState
          icon={Briefcase}
          title="No jobs on the board yet"
          action={
            <Button onClick={addDemoJobs} disabled={adding}>
              <PlayCircle aria-hidden /> Add the demo jobs
            </Button>
          }
        >
          Jobs appear here once an employer approves what they match on. Add eleven invented demo
          jobs to try the board: it costs nothing.
        </EmptyState>
        <div className="mt-4">
          <ErrorAlert error={error} title="Couldn't add the demo jobs" />
        </div>
      </>
    )
  }

  return (
    <>
      {header}
      <div className="mb-4 empty:hidden">
        <ErrorAlert error={error} title="Couldn't add the demo jobs" />
      </div>
      {requests.length > 0 && <Requests requests={requests} />}
      {!summary.approved && (
        <p className="mb-4 text-sm text-muted-foreground">
          Approve your profile to connect it to jobs:{' '}
          <Link to="../review" className="text-primary underline-offset-4 hover:underline">
            go to your review
          </Link>
          .
        </p>
      )}
      <div
        role="search"
        aria-label="Filter the jobs"
        className={cn(
          'mb-6 grid gap-3 rounded-xl border bg-card p-4 sm:grid-cols-2',
          byFit ? 'lg:grid-cols-[2fr_1fr_1fr_1fr_1fr]' : 'lg:grid-cols-[2fr_1fr_1fr_1fr]',
        )}
      >
        <div className="space-y-1.5">
          <Label htmlFor="board-q">Search</Label>
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input
              id="board-q"
              type="search"
              value={text}
              placeholder="Title, company or words in the ad"
              className="pl-8"
              onChange={(e) => setText(e.target.value)}
            />
          </div>
        </div>
        <Filter label="Location" value={params.get('location') ?? ''} onChange={(v) => setFilter('location', v)} any="Anywhere">
          {b.locations.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </Filter>
        <Filter label="Work mode" value={params.get('work_mode') ?? ''} onChange={(v) => setFilter('work_mode', v)} any="Any">
          {b.work_modes.map((m) => (
            <option key={m} value={m}>
              {workModeLabel(m)}
            </option>
          ))}
        </Filter>
        <Filter label="Seniority" value={params.get('seniority') ?? ''} onChange={(v) => setFilter('seniority', v)} any="Any">
          {SENIORITIES.filter((s) => b.seniorities.includes(s.value)).map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </Filter>
        {byFit && (
          <Filter label="Fit" value={fitFilter} onChange={(v) => setFilter('fit', v)} any="Any">
            {FIT_FILTERS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </Filter>
        )}
        <div className="sm:col-span-full">
          <Button
            variant="ghost"
            size="sm"
            className="-ml-2"
            aria-expanded={advanced}
            aria-controls="board-advanced"
            onClick={() => setAdvanced(!advanced)}
          >
            <SlidersHorizontal aria-hidden /> Advanced
            <ChevronDown aria-hidden className={cn('transition-transform', advanced && 'rotate-180')} />
          </Button>
        </div>
        {advanced && (
          <div
            id="board-advanced"
            role="group"
            aria-label="Advanced filters"
            className="grid gap-3 sm:col-span-full sm:grid-cols-3"
          >
            <Filter
              label="Work permit"
              value={params.get('work_permit') ?? ''}
              onChange={(v) => setFilter('work_permit', v)}
              any="Any"
            >
              {b.work_permits.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </Filter>
            <Filter
              label="Vacancies"
              value={params.get('min_vacancies') ?? ''}
              onChange={(v) => setFilter('min_vacancies', v)}
              any="Any"
            >
              {b.vacancies
                .filter((n) => n > 1)
                .map((n) => (
                  <option key={n} value={n}>
                    {minVacancies(n)}
                  </option>
                ))}
            </Filter>
            <Filter
              label="Skills in the ad"
              value=""
              onChange={(v) => v && setParams(withFilter(latest.current, 'skill', v))}
              any="Add a skill"
            >
              {b.skills
                .filter((s) => !params.getAll('skill').includes(s))
                .map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
            </Filter>
          </div>
        )}
      </div>

      {active.length > 0 && (
        <Chips filters={active} onRemove={(f) => setParams(withoutFilter(latest.current, f.key, f.value))} />
      )}

      <div className="mb-3 flex items-center justify-between gap-2 text-sm text-muted-foreground">
        <p role="status" aria-live="polite">
          {filtered ? `${b.listings.length} of ${b.total} jobs` : `${b.total} jobs`}
          {board.loading && ' · searching…'}
        </p>
        <div className="flex items-center gap-2">
          {filtered && (
            <Button variant="ghost" size="sm" onClick={clear}>
              Clear filters
            </Button>
          )}
          {byFit && <SortBy value={sort} onChange={setSort} />}
        </div>
      </div>

      {b.listings.length === 0 ? (
        <EmptyState
          icon={Search}
          title="No jobs match"
          action={
            <Button variant="outline" onClick={clear}>
              Clear filters
            </Button>
          }
        >
          Try fewer words or filters.
        </EmptyState>
      ) : (
        <ul className="space-y-3" aria-label="Jobs">
          {b.listings.map((x) => (
            <li key={x.name}>
              <ListingCard
                listing={x}
                connection={connectionOf.get(x.name)}
                fit={fitOf.get(x.name)}
                filterTo={filterTo}
                // Until the connections load, the card can't tell which action fits.
                action={
                  connections.data ? (
                    <CardConnect
                      listing={x}
                      connection={connectionOf.get(x.name)}
                      approved={summary.approved}
                      busy={changing === x.name}
                      error={changeError?.job === x.name ? changeError.error : null}
                      onChange={(connect) => change(x, connect)}
                    />
                  ) : undefined
                }
              />
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

/** A filter as a native select: keyboard friendly and clear to screen readers. */
function Filter({
  label,
  value,
  onChange,
  any,
  children,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  any: string
  children: ReactNode
}) {
  const id = useId()
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-8 w-full rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <option value="">{any}</option>
        {children}
      </select>
    </div>
  )
}

/** The active filters as chips, each with a button to remove it. */
function Chips({ filters, onRemove }: { filters: ActiveFilter[]; onRemove: (filter: ActiveFilter) => void }) {
  return (
    <ul aria-label="Active filters" className="mb-3 flex flex-wrap gap-1.5">
      {filters.map((f) => {
        const label = filterLabel(f)
        return (
          <li key={`${f.key}=${f.value}`}>
            <span className="inline-flex h-7 items-center gap-1 rounded-full border border-primary/40 bg-accent/40 pr-1 pl-2.5 text-xs font-medium">
              {label}
              <button
                type="button"
                aria-label={`Remove ${label}`}
                className="rounded-full p-0.5 outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
                onClick={() => onRemove(f)}
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </span>
          </li>
        )
      })}
    </ul>
  )
}

/**
 * A pill that filters the board by what it says: on the board it adds the filter, on a
 * listing it goes back to the board filtered by it.
 */
function FilterPill({
  to,
  variant = 'outline',
  className,
  children,
}: {
  to: string
  variant?: 'outline' | 'secondary'
  className?: string
  children: ReactNode
}) {
  return (
    <Badge variant={variant} className={cn('hover:border-primary/60', className)} asChild>
      <Link to={to} title="Show the jobs with this">
        {children}
      </Link>
    </Badge>
  )
}

/** The pills of what a listing shows: seniority, work modes, permits and vacancies. */
function Pills({ listing: x, filterTo }: { listing: Listing; filterTo: FilterTo }) {
  return (
    <>
      <FilterPill variant="secondary" to={filterTo('seniority', x.seniority)}>
        {seniorityLabel(x.seniority)}
      </FilterPill>
      {x.work_modes.map((m) => (
        <FilterPill key={m} to={filterTo('work_mode', m)}>
          {workModeLabel(m)}
        </FilterPill>
      ))}
      {x.work_permits.map((p) => (
        <FilterPill key={p} to={filterTo('work_permit', p)}>
          <IdCard aria-hidden /> {permitLabel(p)}
        </FilterPill>
      ))}
      <FilterPill to={filterTo('min_vacancies', String(x.vacancies))}>
        <Users aria-hidden /> {vacancies(x.vacancies)}
      </FilterPill>
    </>
  )
}

/** The skills an ad names, as pills; `limit` shows only the first few. */
function SkillPills({ skills, filterTo, limit }: { skills: string[]; filterTo: FilterTo; limit?: number }) {
  if (!skills.length) return null
  const shown = limit === undefined ? skills : skills.slice(0, limit)
  return (
    <div role="group" aria-label="Named in the ad" className="flex flex-wrap items-center gap-1.5">
      {shown.map((s) => (
        <FilterPill key={s} to={filterTo('skill', s)} className="border-dashed">
          {s}
        </FilterPill>
      ))}
      {shown.length < skills.length && (
        <span className="text-xs text-muted-foreground">+{skills.length - shown.length} more</span>
      )}
    </div>
  )
}

/** The board's order: newest first, or best fit first with ties newest first. */
function SortBy({ value, onChange }: { value: BoardSort; onChange: (value: BoardSort) => void }) {
  const id = useId()
  return (
    <div className="flex items-center gap-2">
      <Label htmlFor={id} className="text-muted-foreground">
        Sort
      </Label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value as BoardSort)}
        className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <option value="newest">Newest first</option>
        <option value="fit">Best fit first</option>
      </select>
    </div>
  )
}

/** The jobs whose employer asked you to apply and are waiting for your answer. */
function Requests({ requests }: { requests: Connection[] }) {
  return (
    <section aria-labelledby="requests" className="mb-6 space-y-3 rounded-xl border border-primary/40 bg-accent/40 p-4">
      <h2 id="requests" className="flex items-center gap-2 font-semibold">
        <Mail className="size-4 text-primary" aria-hidden />
        Asked to apply
      </h2>
      <ul className="space-y-2">
        {requests.map((c) => (
          <li key={c.job} className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span>
              <span className="font-medium">{c.listing?.company}</span> asked you to apply for{' '}
              <span className="font-medium">{c.listing?.title}</span>
              {c.progress?.requested_at && <span className="text-muted-foreground"> · {day(c.progress.requested_at)}</span>}
            </span>
            <Button size="sm" asChild>
              <Link to={c.job}>Answer</Link>
            </Button>
          </li>
        ))}
      </ul>
    </section>
  )
}

function ListingCard({
  listing: x,
  connection,
  fit,
  filterTo,
  action,
}: {
  listing: Listing
  connection?: Connection
  fit?: Fit
  filterTo: FilterTo
  action?: ReactNode
}) {
  const stage = connection?.stage
  const connected = stage !== undefined
  return (
    <Card className={cn('transition-colors hover:border-primary/40', connected && 'border-primary/40')}>
      <CardHeader className="gap-1">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <CardTitle className="text-base">
            <Link to={x.name} className="outline-none hover:underline focus-visible:underline focus-visible:ring-3 focus-visible:ring-ring/50 rounded-sm">
              {x.title}
            </Link>
          </CardTitle>
          {stage && (
            <span className="flex flex-wrap items-center gap-1.5">
              <StageBadge stage={stage} />
              {connection && <UnreadBadge count={connection.unread_messages} />}
            </span>
          )}
        </div>
        <Meta listing={x} filterTo={filterTo} />
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="line-clamp-2 text-sm text-muted-foreground">{adSummary(x.ad)}</p>
        <div className="flex flex-wrap gap-1.5">
          <Pills listing={x} filterTo={filterTo} />
        </div>
        <SkillPills skills={x.skills} filterTo={filterTo} limit={CARD_SKILLS} />
        {fit && <FitSummary fit={fit} fitTo={(band) => filterTo('fit', band)} />}
        {x.counts && <Counts counts={x.counts} className="text-xs" />}
        {action}
      </CardContent>
    </Card>
  )
}

/**
 * Connect or withdraw from a card on the board, by the listing's rules: approved
 * profiles only, and no withdrawing once revealed.
 */
function CardConnect({
  listing: x,
  connection,
  approved,
  busy,
  error,
  onChange,
}: {
  listing: Listing
  connection?: Connection
  approved: boolean
  busy: boolean
  error: unknown
  onChange: (connect: boolean) => void
}) {
  let action: ReactNode
  if (connection?.progress?.revealed_at) {
    action = (
      <p className="text-xs text-muted-foreground">
        {x.company} revealed you on {day(connection.progress.revealed_at)}; the connection stays.
      </p>
    )
  } else if (connection) {
    action = (
      <Button variant="outline" size="sm" disabled={busy} aria-label={`Withdraw: ${x.title}`} onClick={() => onChange(false)}>
        {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Link2Off aria-hidden />} Withdraw
      </Button>
    )
  } else {
    action = (
      <WhyDisabled reason={!approved && 'Approve your profile first'}>
        <Button
          size="sm"
          disabled={!approved || busy}
          aria-label={`Connect my profile: ${x.title}`}
          onClick={() => onChange(true)}
        >
          {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Link2 aria-hidden />} Connect my profile
        </Button>
      </WhyDisabled>
    )
  }
  return (
    <div className="space-y-2 border-t pt-3">
      {action}
      <ErrorAlert error={error} title={connection ? "Couldn't withdraw" : "Couldn't connect"} />
    </div>
  )
}

/** Company and place, on one line; each place is a pill that filters by it. */
function Meta({ listing: x, filterTo }: { listing: Listing; filterTo: FilterTo }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
      <span className="inline-flex items-center gap-1.5">
        <Building2 className="size-4" aria-hidden />
        {x.company}
      </span>
      <span className="inline-flex flex-wrap items-center gap-1.5">
        <MapPin className="size-4" aria-hidden />
        {x.locations.length
          ? x.locations.map((l) => (
              <FilterPill key={l} to={filterTo('location', l)}>
                {l}
              </FilterPill>
            ))
          : 'Anywhere'}
      </span>
    </div>
  )
}

/** On a listing, a pill goes back to the board filtered by it alone. */
const boardFilteredBy: FilterTo = (key, value) => `..?${new URLSearchParams({ [key]: value })}`

/** One listing in full: the ad and vacancies, and connecting your profile to it. */
export function JobListing() {
  const { name, summary } = useCandidate()
  const { job = '' } = useParams()
  const listing = useResource(() => api.listing(job), job)
  const connections = useResource(() => api.connections(name), `${name}:${job}`)
  const fit = useResource(() => api.fit(name, job), `${name}:${job}`)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)

  const back = (
    <Button variant="ghost" size="sm" asChild className="mb-4 -ml-2">
      <Link to="..">
        <ArrowLeft aria-hidden /> All jobs
      </Link>
    </Button>
  )
  if (!listing.data) {
    return (
      <>
        {back}
        {listing.error ? <ErrorAlert error={listing.error} title="Couldn't open the job" /> : <Loading label="Loading the job" />}
      </>
    )
  }
  const x = listing.data
  const connection = connections.data?.find((c) => c.job === job) ?? null

  async function change(connect: boolean) {
    setBusy(true)
    setError(null)
    try {
      await changeConnection(name, job, x.company, connect)
      await Promise.all([connections.reload(), fit.reload()])
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      {back}
      <PageHeader title={x.title}>
        <Meta listing={x} filterTo={boardFilteredBy} />
      </PageHeader>
      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <Card>
          <CardContent>
            <AdText text={x.ad} title={x.title} />
          </CardContent>
        </Card>
        <aside className="space-y-4" aria-label="About this job">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">At a glance</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 text-sm">
                <dt className="text-muted-foreground">Vacancies</dt>
                <dd>
                  <FilterPill to={boardFilteredBy('min_vacancies', String(x.vacancies))}>{vacancies(x.vacancies)}</FilterPill>
                </dd>
                <dt className="text-muted-foreground">Seniority</dt>
                <dd>
                  <FilterPill variant="secondary" to={boardFilteredBy('seniority', x.seniority)}>
                    {seniorityLabel(x.seniority)}
                  </FilterPill>
                </dd>
                <dt className="text-muted-foreground">Work mode</dt>
                <dd className="flex flex-wrap gap-1.5">
                  {x.work_modes.length
                    ? x.work_modes.map((m) => (
                        <FilterPill key={m} to={boardFilteredBy('work_mode', m)}>
                          {workModeLabel(m)}
                        </FilterPill>
                      ))
                    : 'Any'}
                </dd>
                <dt className="text-muted-foreground">Work permit</dt>
                <dd className="flex flex-wrap gap-1.5">
                  {x.work_permits.length
                    ? x.work_permits.map((p) => (
                        <FilterPill key={p} to={boardFilteredBy('work_permit', p)}>
                          {permitLabel(p)}
                        </FilterPill>
                      ))
                    : 'None asked for'}
                </dd>
                <dt className="text-muted-foreground">Posted</dt>
                <dd>{day(x.posted_at)}</dd>
              </dl>
              {x.skills.length > 0 && (
                <div className="mt-3 space-y-1.5">
                  <p className="text-sm text-muted-foreground">Skills the ad names</p>
                  <SkillPills skills={x.skills} filterTo={boardFilteredBy} />
                </div>
              )}
              {x.counts && <Counts counts={x.counts} className="mt-3 flex-col" />}
              {x.demo && (
                <p className="mt-3 text-xs text-muted-foreground">A demo job: the company is invented.</p>
              )}
            </CardContent>
          </Card>
          {connection?.progress && connection.stage !== 'revealed' && (
            <ApplicationCard
              candidate={name}
              connection={connection}
              company={x.company}
              onAnswered={() => Promise.all([connections.reload(), listing.reload()]).then(() => undefined)}
            />
          )}
          {connection?.progress?.revealed_at && (
            <Card role="region" aria-label={`Messages with ${x.company}`} className="border-primary/40">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <MessagesSquare className="size-4 text-primary" aria-hidden /> Messages
                </CardTitle>
              </CardHeader>
              <CardContent>
                <MessageThread
                  label={`Thread with ${x.company}`}
                  me="candidate"
                  other={x.company}
                  threadKey={`${name}:${job}`}
                  load={() => api.candidateThread(name, job)}
                  markRead={() => api.candidateRead(name, job)}
                  send={(text) => api.candidateSend(name, job, text)}
                  onRead={() => void connections.reload()}
                />
              </CardContent>
            </Card>
          )}
          {fit.data && <FitCard fit={fit.data} />}
          <ConnectCard
            company={x.company}
            approved={summary.approved}
            connection={connection}
            loading={!connections.data && !connections.error}
            busy={busy}
            onChange={change}
          />
          <ErrorAlert error={error} title={connection ? "Couldn't withdraw" : "Couldn't connect"} />
          <ErrorAlert error={connections.error} title="Couldn't load your connections" />
        </aside>
      </div>
    </>
  )
}

function ConnectCard({
  company,
  approved,
  connection,
  loading,
  busy,
  onChange,
}: {
  company: string
  approved: boolean
  connection: Connection | null
  loading: boolean
  busy: boolean
  onChange: (connect: boolean) => void
}) {
  if (loading) return <Loading label="Loading your connections" />
  if (connection?.progress?.revealed_at) {
    return (
      <Alert role="region" aria-label="Your connection" className="border-primary/40">
        <Eye aria-hidden />
        <AlertTitle>Revealed on {day(connection.progress.revealed_at)}</AlertTitle>
        <AlertDescription>
          <p>
            {company} has seen your name, contact details and the quotes behind your scores. You
            connected on {day(connection.connected_at)}; once revealed, the connection stays.
          </p>
        </AlertDescription>
      </Alert>
    )
  }
  if (connection) {
    return (
      <Alert role="region" aria-label="Your connection" className="border-primary/40">
        <ShieldCheck aria-hidden />
        <AlertTitle>Connected on {day(connection.connected_at)}</AlertTitle>
        <AlertDescription className="space-y-3">
          <p>
            {company} can match and rank your profile, without your name or contact details.
            You can withdraw until they reveal you.
          </p>
          <Button variant="outline" size="sm" disabled={busy} onClick={() => onChange(false)}>
            <Link2Off aria-hidden /> Withdraw
          </Button>
        </AlertDescription>
      </Alert>
    )
  }
  return (
    <Card role="region" aria-label="Connect my profile">
      <CardHeader>
        <CardTitle className="text-base">Interested?</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground">
          Connecting lets {company} match and rank your approved profile anonymously. They only
          see your name if they reveal you, and you can withdraw until then.
        </p>
        <WhyDisabled reason={!approved && 'Approve your profile first'} className="w-full">
          <Button className="w-full" disabled={!approved || busy} onClick={() => onChange(true)}>
            <Link2 aria-hidden /> Connect my profile
          </Button>
        </WhyDisabled>
        {!approved && (
          <p className="text-xs text-muted-foreground">
            Approve your profile first: <Link to="../../review" className="text-primary underline-offset-4 hover:underline">go to your review</Link>.
          </p>
        )}
      </CardContent>
    </Card>
  )
}

/** How well you fit the job: the band, requirements you miss, and your place once connected. */
function FitCard({ fit }: { fit: Fit }) {
  return (
    <Card role="region" aria-label="How well you fit">
      <CardHeader>
        <CardTitle className="text-base">How well you fit</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {fit.band ? (
          <div className="space-y-1.5">
            <FitBadge band={fit.band} to={boardFilteredBy('fit', fit.band)} />
            <p className="text-muted-foreground">From your own levels, compared with what the job asks for.</p>
          </div>
        ) : (
          <p className="text-muted-foreground">Your fit shows once you have a profile.</p>
        )}
        {fit.missed.length > 0 && (
          <div className="space-y-1.5">
            <p className="font-medium">You don't meet</p>
            <MissedFilters fit={fit} />
            <p className="text-muted-foreground">
              You can still connect, but you'll rank after everyone who meets every requirement.
            </p>
          </div>
        )}
        {fit.connected ? (
          fit.place ? (
            <p>
              <span className="font-medium">{placeText(fit.place)}</span>{' '}
              <span className="text-muted-foreground">
                connected candidates, in the latest ranking on {day(fit.place.ranked_at)}.
              </span>
            </p>
          ) : (
            <p className="text-muted-foreground">
              Not ranked yet: your place shows once the employer ranks the connected candidates.
            </p>
          )
        ) : (
          <p className="text-muted-foreground">Connect to see your place among the connected candidates.</p>
        )}
      </CardContent>
    </Card>
  )
}

/** The employer asked you to apply: write or upload your application, or decline. */
function ApplicationCard({
  candidate,
  connection,
  company,
  onAnswered,
}: {
  candidate: string
  connection: Connection
  company: string
  onAnswered: () => Promise<void>
}) {
  const [letter, setLetter] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState<'apply' | 'decline' | null>(null)
  const [error, setError] = useState<unknown>(null)
  const letterId = useId()
  const filesId = useId()
  const p = connection.progress
  if (!p) return null

  async function answer(choice: 'apply' | 'decline') {
    setBusy(choice)
    setError(null)
    try {
      if (choice === 'apply') {
        await api.apply(candidate, connection.job, letter, files)
        toast.success(`Your application is sent to ${company}.`)
      } else {
        await api.decline(candidate, connection.job)
        toast.success(`You declined ${company}'s request.`)
      }
      await onAnswered()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(null)
    }
  }

  if (p.answer === 'applied') {
    return (
      <Card role="region" aria-label="Your application" className="border-primary/40">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Check className="size-4 text-primary" aria-hidden /> You applied
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-muted-foreground">
            Sent to {company}
            {p.answered_at && ` on ${day(p.answered_at)}`}.
          </p>
          {p.letter && <p className="line-clamp-6 whitespace-pre-wrap">{p.letter}</p>}
          {p.files.length > 0 && (
            <ul className="space-y-1" aria-label="Files sent">
              {p.files.map((f) => (
                <li key={f.id}>
                  <a
                    href={api.ownApplicationFileUrl(candidate, connection.job, f.id)}
                    download={f.name}
                    className="inline-flex items-center gap-1.5 text-primary underline-offset-4 hover:underline"
                  >
                    <Download className="size-3.5" aria-hidden /> {f.name}
                  </a>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    )
  }
  if (p.answer === 'declined') {
    return (
      <Alert role="region" aria-label="Your application">
        <X aria-hidden />
        <AlertTitle>You declined</AlertTitle>
        <AlertDescription>
          {company} asked you to apply{p.answered_at && `, and you declined on ${day(p.answered_at)}`}.
        </AlertDescription>
      </Alert>
    )
  }
  return (
    <Card role="region" aria-label="Asked to apply" className="border-primary/60 ring-3 ring-primary/15">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Mail className="size-4 text-primary" aria-hidden /> {company} asks you to apply
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <p className="text-muted-foreground">
          They revealed you and would like your application
          {p.requested_at && ` (asked on ${day(p.requested_at)})`}. Write a cover letter, add files
          such as your CV, or both.
        </p>
        <div className="space-y-1.5">
          <Label htmlFor={letterId}>Cover letter</Label>
          <Textarea
            id={letterId}
            value={letter}
            rows={6}
            placeholder={`Dear ${company}, …`}
            onChange={(e) => setLetter(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={filesId}>Files</Label>
          <Input
            id={filesId}
            type="file"
            multiple
            accept=".pdf,.md,.txt,.docx,.odt,.rtf"
            onChange={(e) => setFiles([...(e.target.files ?? [])])}
          />
          <p className="text-xs text-muted-foreground">PDF, Word, Markdown or text; up to 5 files of 10 MB.</p>
        </div>
        <ErrorAlert error={error} title="Couldn't send your answer" />
        <div className="flex flex-wrap gap-2">
          <WhyDisabled reason={!letter.trim() && files.length === 0 && 'Write a cover letter or add a file first'}>
            <Button
              disabled={busy !== null || (!letter.trim() && files.length === 0)}
              onClick={() => answer('apply')}
            >
              {busy === 'apply' ? <Loader2 className="animate-spin" aria-hidden /> : <Send aria-hidden />}
              Apply
            </Button>
          </WhyDisabled>
          <Button variant="outline" disabled={busy !== null} onClick={() => answer('decline')}>
            {busy === 'decline' ? <Loader2 className="animate-spin" aria-hidden /> : <X aria-hidden />}
            Decline
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
