import {
  AlertTriangle,
  Check,
  ChevronDown,
  CircleHelp,
  Clock,
  Download,
  Eye,
  EyeOff,
  ListOrdered,
  Loader2,
  Mail,
  MessagesSquare,
  Phone,
  Quote,
  RefreshCw,
  Sparkles,
  Users,
  X,
  type LucideIcon,
} from 'lucide-react'
import { Fragment, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { AskPanel } from '@/components/AskPanel'
import { CandidateAvatar } from '@/components/CandidateAvatar'
import { Counts } from '@/components/Counts'
import { MessageThread, UnreadBadge } from '@/components/MessageThread'
import { SpiderChart, type Series } from '@/components/SpiderChart'
import { EmptyState, ErrorAlert, Loading, PageHeader } from '@/components/states'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { api, describeError } from '@/lib/api'
import { MAX_COMPARED, type LevelView } from '@/lib/chart'
import { day, FILTERS, month } from '@/lib/format'
import type {
  Contact,
  Criterion,
  HardFilterCheck,
  RankedCandidate,
  Scorer,
  ShortlistCandidate,
  Shortlist as ShortlistData,
  Stage,
} from '@/lib/types'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'
import { useJob } from '@/pages/employer/context'

const ON = 'data-[state=on]:border-primary data-[state=on]:bg-primary data-[state=on]:text-primary-foreground'

const SCORERS: { value: Scorer; label: string; title: string }[] = [
  { value: 'baseline', label: 'Baseline', title: 'Plain code from levels and evidence: free and fully repeatable' },
  { value: 'llm', label: 'LLM', title: 'A model reads each anonymised profile against each criterion' },
]

const VIEWS: { value: LevelView; label: string }[] = [
  { value: 'estimated', label: 'Estimated' },
  { value: 'own', label: 'Own' },
  { value: 'both', label: 'Both' },
]

/** Step 3: the anonymised, ranked shortlist, with reasons, a comparison and next steps. */
export function Shortlist() {
  const { summary } = useJob()
  if (!summary.approved) {
    return (
      <EmptyState
        icon={ListOrdered}
        title="Approve the rubric first"
        action={
          <Button asChild>
            <Link to="../rubric">Go to the rubric</Link>
          </Button>
        }
      >
        Candidates are matched only against an approved rubric, so the shortlist always says what it was ranked on.
      </EmptyState>
    )
  }
  return <ShortlistPage />
}

function ShortlistPage() {
  const { name, summary } = useJob()
  const [scorer, setScorer] = useState<Scorer>('baseline')
  // Kept here, so switching scorers keeps the comparison: profiles stay the same.
  const [compared, setCompared] = useState<Compared[]>([])
  const [view, setView] = useState<LevelView>('both')
  const loaded = useResource(() => api.shortlist(name, scorer), `${name}:${scorer}:${summary.rubric_version}`)
  return (
    <div className="space-y-8">
      <PageHeader
        title="Shortlist"
        actions={
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            spacing={1}
            aria-label="Scorer"
            value={scorer}
            onValueChange={(v) => v && setScorer(v as Scorer)}
          >
            {SCORERS.map((s) => (
              <ToggleGroupItem key={s.value} value={s.value} title={s.title} className={`rounded-full px-3 ${ON}`}>
                {s.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        }
      >
        Candidates who connected their approved profile, ranked against rubric version {summary.rubric_version}. They
        are anonymised: you see an alias and a pattern, never a name, a photo or their quotes, until you reveal them.
        Then you can ask them to apply.
      </PageHeader>
      {loaded.data ? (
        <ShortlistView
          data={loaded.data}
          scorer={scorer}
          reload={loaded.reload}
          compared={compared}
          setCompared={setCompared}
          view={view}
          setView={setView}
        />
      ) : loaded.error ? (
        <ErrorAlert error={loaded.error} title="Couldn't load the shortlist" />
      ) : (
        <Loading label="Loading the shortlist" />
      )}
    </div>
  )
}

/** A candidate compared, by profile id, with the colour slot they keep while compared. */
interface Compared {
  id: string
  slot: number
}

interface ViewProps {
  data: ShortlistData
  scorer: Scorer
  reload: () => Promise<void>
  compared: Compared[]
  setCompared: (compared: Compared[]) => void
  view: LevelView
  setView: (view: LevelView) => void
}

function ShortlistView({ data, scorer, reload, compared, setCompared, view, setView }: ViewProps) {
  const { name, summary } = useJob()
  const [matching, setMatching] = useState(false)
  const people = new Map(data.candidates.map((c) => [c.profile_id, c]))
  const criteria = new Map(data.rubric.criteria.map((c) => [c.id, c]))
  const reveals = data.counts.revealed

  async function match() {
    setMatching(true)
    try {
      const ranking = await api.match(name, scorer)
      toast.success(`Ranked ${ranking.candidates.length} candidate${ranking.candidates.length === 1 ? '' : 's'}.`)
      await reload()
    } catch (e) {
      toast.error(describeError(e))
    } finally {
      setMatching(false)
    }
  }

  function toggle(id: string) {
    if (compared.some((c) => c.id === id)) {
      setCompared(compared.filter((c) => c.id !== id))
      return
    }
    const used = new Set(compared.map((c) => c.slot))
    const slot = [...Array(MAX_COMPARED).keys()].find((s) => !used.has(s))
    if (slot !== undefined) setCompared([...compared, { id, slot }])
  }

  /** The employer's next step on a candidate: reveal, then request an application. */
  async function next(candidate: ShortlistCandidate) {
    const stage = candidate.progress.stage
    try {
      if (stage === 'connected') {
        await api.reveal(name, candidate.profile_id)
        toast.success(`${candidate.alias} is revealed. No payment is taken in this version.`)
      } else if (stage === 'revealed') {
        await api.requestApplication(name, candidate.profile_id)
        toast.success(`${candidate.contact?.name ?? candidate.alias} is asked to apply.`)
      }
      await reload()
    } catch (e) {
      toast.error(describeError(e))
    }
  }

  const matchButton = (
    <Button onClick={match} disabled={matching} variant={data.ranking.candidates.length ? 'outline' : 'default'}>
      {matching ? <Loader2 className="animate-spin" aria-hidden /> : <RefreshCw aria-hidden />}
      {data.ranking.candidates.length ? 'Match again' : 'Match candidates'}
    </Button>
  )

  if (!data.ranking.candidates.length) {
    return (
      <EmptyState icon={Users} title="No one is ranked yet" action={matchButton}>
        Match every candidate with an approved profile against this rubric.{' '}
        {scorer === 'llm' && summary.demo
          ? 'In the demo, the LLM scorer replays recorded answers, so it costs nothing.'
          : scorer === 'llm'
            ? 'The LLM scorer makes paid model calls, which this server may refuse.'
            : 'The baseline is plain code and costs nothing.'}{' '}
        Matching locks this rubric version.
      </EmptyState>
    )
  }

  function card(r: RankedCandidate) {
    const c = people.get(r.profile_id)
    if (!c) return null
    const slot = compared.find((x) => x.id === c.profile_id)?.slot
    return (
      <CandidateCard
        key={r.match_id}
        ranked={r}
        candidate={c}
        criteria={criteria}
        scorer={scorer}
        compared={slot !== undefined}
        canCompare={slot !== undefined || compared.length < MAX_COMPARED}
        onCompare={() => toggle(c.profile_id)}
        revealsLeft={reveals < data.reveal_quota}
        onNext={() => next(c)}
        onRead={() => void reload()}
      />
    )
  }
  const passing = data.ranking.candidates.filter((r) => r.passed_hard_filters)
  const failing = data.ranking.candidates.filter((r) => !r.passed_hard_filters)

  const series: Series[] = compared.flatMap(({ id, slot }) => {
    const c = people.get(id)
    return c ? [{ id, label: c.alias, slot, levels: c.skills }] : []
  })

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,28rem)]">
      <section aria-labelledby="ranked" className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="ranked" className="text-lg font-semibold">
            {data.ranking.candidates.length} ranked
          </h2>
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">
              Reveals used: {reveals} of {data.reveal_quota}
            </span>
            {matchButton}
          </div>
        </div>
        <Counts counts={data.counts} vacancies={data.vacancies} />
        <ScoreKey scorer={scorer} />
        <ol className="space-y-3" aria-label="Meet the requirements">
          {passing.map(card)}
        </ol>
        {failing.length > 0 && (
          <>
            <div className="flex items-center gap-3 pt-4" role="separator" aria-labelledby="failing">
              <span className="h-px flex-1 bg-destructive/30" />
              <span id="failing" className="text-sm font-medium text-destructive">
                Don't meet the requirements · {failing.length}
              </span>
              <span className="h-px flex-1 bg-destructive/30" />
            </div>
            <p className="text-sm text-muted-foreground">
              Scored like everyone else, but each fails a hard filter, so they rank after everyone who meets them,
              whatever their score.
            </p>
            <ol className="space-y-3" aria-label="Don't meet the requirements">
              {failing.map(card)}
            </ol>
          </>
        )}
      </section>

      <aside className="lg:sticky lg:top-6 lg:self-start">
        <Card>
          <CardHeader>
            <CardTitle>Compare</CardTitle>
            <CardDescription>
              Levels in the rubric's skills, from 1 (aware) to 5 (expert). Estimated levels come from the evidence; own
              levels are what candidates said.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              spacing={1}
              aria-label="Levels shown"
              value={view}
              onValueChange={(v) => v && setView(v as LevelView)}
            >
              {VIEWS.map((v) => (
                <ToggleGroupItem key={v.value} value={v.value} className={`rounded-full px-3 ${ON}`}>
                  {v.label}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
            {series.length ? (
              <SpiderChart skills={data.skills} series={series} view={view} />
            ) : (
              <p className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
                Tick “Compare” on up to {MAX_COMPARED} candidates to see them side by side.
              </p>
            )}
          </CardContent>
        </Card>
      </aside>
    </div>
  )
}

interface CardProps {
  ranked: RankedCandidate
  candidate: ShortlistCandidate
  criteria: Map<string, Criterion>
  scorer: Scorer
  compared: boolean
  canCompare: boolean
  onCompare: () => void
  revealsLeft: boolean
  onNext: () => Promise<void>
  /** Called once the candidate's messages are read, to update the unread count. */
  onRead: () => void
}

/** The one action button at each stage; only the first two are actions. */
const NEXT: Record<Stage, { label: string; icon: LucideIcon; action: boolean }> = {
  connected: { label: 'Reveal', icon: Eye, action: true },
  revealed: { label: 'Request application', icon: Mail, action: true },
  requested: { label: 'Waiting for application', icon: Clock, action: false },
  applied: { label: 'Applied', icon: Check, action: false },
  declined: { label: 'Declined', icon: X, action: false },
}

const STAGE_BADGE: Record<Stage, string | null> = {
  connected: null,
  revealed: 'Revealed',
  requested: 'Asked to apply',
  applied: 'Applied',
  declined: 'Declined',
}

function CandidateCard({
  ranked,
  candidate,
  criteria,
  scorer,
  compared,
  canCompare,
  onCompare,
  revealsLeft,
  onNext,
  onRead,
}: CardProps) {
  const { name: job } = useJob()
  const [open, setOpen] = useState(false)
  const [talking, setTalking] = useState(false)
  // Questions stay mounted once opened, so closing them keeps the conversation.
  const [asking, setAsking] = useState(false)
  const [askOpened, setAskOpened] = useState(false)
  const [busy, setBusy] = useState(false)
  const stage = candidate.progress.stage
  const step = NEXT[stage]
  const revealed = stage !== 'connected'
  const quotaUsed = stage === 'connected' && !revealsLeft
  const failed = (ranked.hard_filters ?? []).filter((f) => f.outcome === 'fail')
  const unknown = (ranked.hard_filters ?? []).filter((f) => f.outcome === 'unknown')
  const detailsId = `details-${candidate.profile_id}`
  const compareId = `compare-${candidate.profile_id}`
  const threadId = `thread-${candidate.profile_id}`
  const askId = `ask-${candidate.profile_id}`
  const who = candidate.contact?.name ?? candidate.alias

  async function act() {
    setBusy(true)
    await onNext()
    setBusy(false)
  }
  const StepIcon = busy ? Loader2 : step.icon

  return (
    <li>
      <Card
        className={cn('gap-0 py-0', !ranked.passed_hard_filters && 'border-destructive/30 bg-destructive/5')}
        data-failed={ranked.passed_hard_filters ? undefined : true}
      >
        <div className="flex flex-wrap items-start gap-4 p-5">
          <span
            className={cn(
              'flex size-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold',
              ranked.passed_hard_filters ? 'bg-accent text-primary' : 'bg-destructive/10 text-destructive',
            )}
            aria-label={`Rank ${ranked.rank}`}
          >
            {ranked.rank}
          </span>
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <CandidateAvatar avatar={candidate.avatar} className="size-8" />
              {candidate.contact ? (
                <h3 className="font-medium">
                  {candidate.contact.name}{' '}
                  <span className="text-sm font-normal text-muted-foreground">({candidate.alias})</span>
                </h3>
              ) : (
                <h3 className="font-medium">{candidate.alias}</h3>
              )}
              {STAGE_BADGE[stage] && (
                <Badge variant={stage === 'declined' ? 'outline' : 'secondary'}>{STAGE_BADGE[stage]}</Badge>
              )}
              <UnreadBadge count={candidate.progress.unread_messages} />
            </div>
            {candidate.contact && <ContactLine contact={candidate.contact} />}
            <p className="text-sm text-muted-foreground">{candidate.headline}</p>
            {failed.map((f) => (
              <p key={f.name} className="flex items-start gap-1.5 text-sm">
                <X className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
                <span>
                  <span className="font-medium">Doesn't meet {FILTERS[f.name].toLowerCase()}:</span> {f.reason}
                </span>
              </p>
            ))}
            <Scores ranked={ranked} scorer={scorer} alias={candidate.alias} />
            {unknown.length > 0 && (
              <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
                <CircleHelp className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                Not known: {unknown.map((f) => FILTERS[f.name].toLowerCase()).join(', ')} (not excluded)
              </p>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Checkbox
              id={compareId}
              aria-label={`Compare ${candidate.alias}`}
              checked={compared}
              disabled={!canCompare}
              onCheckedChange={onCompare}
            />
            <label htmlFor={compareId} className="text-sm">
              Compare
            </label>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t px-5 py-3">
          <Button
            variant="ghost"
            size="sm"
            aria-expanded={open}
            aria-controls={detailsId}
            aria-label={`${open ? 'Hide' : 'Why'} for ${candidate.alias}`}
            onClick={() => setOpen(!open)}
          >
            <ChevronDown className={cn('transition-transform', open && 'rotate-180')} aria-hidden />
            {open ? 'Hide' : 'Why'}
          </Button>
          {revealed && (
            <Button
              variant="ghost"
              size="sm"
              aria-expanded={talking}
              aria-controls={threadId}
              aria-label={`Messages with ${who}`}
              onClick={() => {
                // One of messages and questions shows at a time.
                setTalking(!talking)
                setAsking(false)
              }}
            >
              <MessagesSquare aria-hidden /> Messages
            </Button>
          )}
          {revealed && (
            <Button
              variant="ghost"
              size="sm"
              aria-expanded={asking}
              aria-controls={askId}
              aria-label={`Ask about ${who}`}
              onClick={() => {
                setAsking(!asking)
                setAskOpened(true)
                setTalking(false)
              }}
            >
              <Sparkles aria-hidden /> Ask
            </Button>
          )}
          <span className="flex-1" />
          <Button
            size="sm"
            variant={step.action ? 'default' : 'ghost'}
            disabled={busy || !step.action || quotaUsed}
            title={quotaUsed ? 'All reveals for this job are used' : undefined}
            aria-label={`${step.label}: ${candidate.contact?.name ?? candidate.alias}`}
            onClick={act}
          >
            <StepIcon className={cn(busy && 'animate-spin')} aria-hidden />
            {step.label}
          </Button>
        </div>

        {talking && (
          <div id={threadId} className="border-t px-5 py-4">
            <MessageThread
              label={`Thread with ${who}`}
              me="employer"
              other={who}
              threadKey={`${job}:${candidate.profile_id}`}
              load={() => api.employerThread(job, candidate.profile_id)}
              markRead={() => api.employerRead(job, candidate.profile_id)}
              send={(text) => api.employerSend(job, candidate.profile_id, text)}
              onRead={onRead}
            />
          </div>
        )}

        {revealed && askOpened && (
          <div id={askId} hidden={!asking} className="border-t px-5 py-4">
            <AskPanel job={job} profileId={candidate.profile_id} who={who} />
          </div>
        )}

        {stage === 'applied' && <Application candidate={candidate} />}

        {open && (
          <div id={detailsId} className="space-y-6 border-t px-5 py-5">
            <Reasons ranked={ranked} candidate={candidate} criteria={criteria} scorer={scorer} revealed={revealed} />
            {ranked.hard_filters && ranked.hard_filters.length > 0 && <Filters checks={ranked.hard_filters} />}
            <Roles candidate={candidate} />
          </div>
        )}
      </Card>
    </li>
  )
}

const SCORER_TOTAL: Record<Scorer, string> = { baseline: 'Baseline total', llm: 'LLM total' }

/** Says what the three scores on each card are. */
function ScoreKey({ scorer }: { scorer: Scorer }) {
  return (
    <p className="text-sm text-muted-foreground">
      <span className="font-medium text-foreground">{SCORER_TOTAL[scorer]}</span> sets the rank.{' '}
      <span className="font-medium text-foreground">Own rating</span> scores the candidate's own levels and{' '}
      <span className="font-medium text-foreground">Estimated from evidence</span> the levels their material supports,
      both with the baseline.
    </p>
  )
}

/** The scorer's total, which sets the rank, and the baseline on own and on estimated levels. */
function Scores({ ranked, scorer, alias }: { ranked: RankedCandidate; scorer: Scorer; alias: string }) {
  const rows = [
    ['Own rating', ranked.own_total],
    ['Estimated from evidence', ranked.estimated_total],
  ] as const
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-4 gap-y-1.5 pt-1">
      <dt className="text-sm font-medium">{SCORER_TOTAL[scorer]}</dt>
      <dd>
        <ScoreBar value={ranked.total} label={`Total for ${alias}`} />
      </dd>
      {rows.map(([name, value]) => (
        <Fragment key={name}>
          <dt className="text-xs text-muted-foreground">{name}</dt>
          <dd>
            {value === null ? (
              <span className="text-xs text-muted-foreground">Profile changed since matching</span>
            ) : (
              <ScoreBar value={value} label={`${name} for ${alias}`} small />
            )}
          </dd>
        </Fragment>
      ))}
    </dl>
  )
}

/** A score from 0 to 1 as a bar and a percentage. */
function ScoreBar({ value, label, small }: { value: number; label: string; small?: boolean }) {
  const percent = Math.round(value * 100)
  return (
    <div className="flex items-center gap-3">
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className={cn('max-w-64 flex-1 overflow-hidden rounded-full bg-muted', small ? 'h-1.5' : 'h-2')}
      >
        <div className="h-full rounded-full bg-primary" style={{ width: `${percent}%` }} />
      </div>
      <span className={cn('w-9 text-right tabular-nums', small ? 'text-xs text-muted-foreground' : 'text-sm font-medium')}>
        {percent}%
      </span>
    </div>
  )
}

function Reasons({
  ranked,
  candidate,
  criteria,
  scorer,
  revealed,
}: {
  ranked: RankedCandidate
  candidate: ShortlistCandidate
  criteria: Map<string, Criterion>
  scorer: Scorer
  revealed: boolean
}) {
  const quotes = new Map(candidate.evidence.map((e) => [e.id, e]))
  const scores = new Map(ranked.criterion_scores.map((s) => [s.criterion_id, s]))
  return (
    <section className="space-y-3" aria-label={`Reasons for ${candidate.alias}`}>
      <h4 className="text-sm font-medium">Per criterion</h4>
      <ul className="space-y-4">
        {[...criteria.values()].map((c) => {
          const s = scores.get(c.id)
          return (
            <li key={c.id} className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">{c.description}</span>
                <Badge variant={c.kind === 'must_have' ? 'default' : 'secondary'}>
                  {c.kind === 'must_have' ? 'Must-have' : 'Nice-to-have'}
                </Badge>
                <span className="text-xs text-muted-foreground">weight {c.weight}</span>
              </div>
              {s ? (
                <>
                  <ScoreBar value={s.score} label={`${c.description}: score`} small />
                  <p className="text-sm text-muted-foreground">{s.rationale}</p>
                  {!revealed && s.evidence_ids.length > 0 && (
                    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <EyeOff className="size-3.5" aria-hidden />
                      {quoteCount(s.evidence_ids.length)}, shown once you reveal the candidate
                    </p>
                  )}
                  {s.evidence_ids.map((id) => {
                    const q = quotes.get(id)
                    return q ? (
                      <blockquote key={id} className="flex gap-2 border-l-2 border-primary/30 pl-3 text-sm">
                        <Quote className="mt-0.5 size-3.5 shrink-0 text-primary/60" aria-hidden />
                        <span>
                          {q.quote} <span className="text-xs text-muted-foreground">({q.source})</span>
                        </span>
                      </blockquote>
                    ) : null
                  })}
                </>
              ) : (
                <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
                  <AlertTriangle className="size-3.5" aria-hidden />
                  {scorer === 'baseline' && !c.skill
                    ? "Not scored: it names no skill, and the baseline only reads skills."
                    : 'Not scored.'}
                </p>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function Filters({ checks }: { checks: HardFilterCheck[] }) {
  const icon = { pass: Check, fail: X, unknown: CircleHelp }
  return (
    <section className="space-y-2" aria-label="Hard filters">
      <h4 className="text-sm font-medium">Hard filters</h4>
      <ul className="space-y-1">
        {checks.map((f) => {
          const Icon = icon[f.outcome]
          return (
            <li key={f.name} className="flex items-start gap-2 text-sm">
              <Icon
                className={cn(
                  'mt-0.5 size-4 shrink-0',
                  f.outcome === 'pass' && 'text-primary',
                  f.outcome === 'fail' && 'text-destructive',
                  f.outcome === 'unknown' && 'text-muted-foreground',
                )}
                aria-hidden
              />
              <span>
                <span className="font-medium">
                  {FILTERS[f.name]}: {f.outcome === 'pass' ? 'meets it' : f.outcome === 'fail' ? 'fails' : 'not known'}
                </span>{' '}
                <span className="text-muted-foreground">· {f.reason}</span>
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function Roles({ candidate }: { candidate: ShortlistCandidate }) {
  if (!candidate.experiences.length) return null
  return (
    <section className="space-y-2" aria-label="Experience">
      <h4 className="text-sm font-medium">Experience</h4>
      <ul className="space-y-2">
        {candidate.experiences.map((x, i) => (
          <li key={i} className="text-sm">
            <span className="font-medium">{x.title}</span>
            <span className="text-muted-foreground">
              {' '}
              · {x.organisation} · {month(x.start, x.start_precision) || '?'} –{' '}
              {x.end ? month(x.end, x.end_precision) : 'now'}
            </span>
            {x.summary && <p className="text-muted-foreground">{x.summary}</p>}
          </li>
        ))}
      </ul>
    </section>
  )
}

/** "1 quote supports this", "3 quotes support this". */
function quoteCount(n: number): string {
  return n === 1 ? '1 quote supports this' : `${n} quotes support this`
}

/** A revealed candidate's contact details. */
function ContactLine({ contact }: { contact: Contact }) {
  if (!contact.email && !contact.phone) return null
  return (
    <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm" aria-label="Contact details">
      {contact.email && (
        <a
          href={`mailto:${contact.email}`}
          className="inline-flex items-center gap-1.5 text-primary underline-offset-4 hover:underline"
        >
          <Mail className="size-3.5" aria-hidden />
          {contact.email}
        </a>
      )}
      {contact.phone && (
        <span className="inline-flex items-center gap-1.5">
          <Phone className="size-3.5" aria-hidden />
          {contact.phone}
        </span>
      )}
    </p>
  )
}

/** What the candidate sent when they applied: their letter and files. */
function Application({ candidate }: { candidate: ShortlistCandidate }) {
  const { name } = useJob()
  const p = candidate.progress
  return (
    <section
      aria-label={`Application from ${candidate.contact?.name ?? candidate.alias}`}
      className="space-y-3 border-t bg-accent/40 px-5 py-4"
    >
      <h4 className="text-sm font-medium">
        Application
        {p.answered_at && <span className="font-normal text-muted-foreground"> · {day(p.answered_at)}</span>}
      </h4>
      {p.letter && <p className="text-sm whitespace-pre-wrap">{p.letter}</p>}
      {p.files.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label="Files">
          {p.files.map((f) => (
            <li key={f.id}>
              <Button variant="outline" size="sm" asChild>
                <a href={api.applicationFileUrl(name, candidate.profile_id, f.id)} download={f.name}>
                  <Download aria-hidden /> {f.name}
                </a>
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
