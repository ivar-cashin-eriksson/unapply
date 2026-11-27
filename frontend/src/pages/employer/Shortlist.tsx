import {
  AlertTriangle,
  Check,
  ChevronDown,
  CircleHelp,
  Eye,
  ListOrdered,
  Loader2,
  Mail,
  Quote,
  RefreshCw,
  Users,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { SpiderChart, type Series } from '@/components/SpiderChart'
import { EmptyState, ErrorAlert, Loading, PageHeader } from '@/components/states'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { api, describeError } from '@/lib/api'
import { MAX_COMPARED, type LevelView } from '@/lib/chart'
import { month } from '@/lib/format'
import type {
  AnonymousCandidate,
  Criterion,
  HardFilterCheck,
  IntentKind,
  RankedCandidate,
  Scorer,
  Shortlist as ShortlistData,
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

const FILTERS: Record<HardFilterCheck['name'], string> = {
  location: 'Location',
  work_mode: 'Work mode',
  work_permit: 'Work permit',
  min_years_experience: 'Years of experience',
}

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
        Candidates who approved their profile, ranked against rubric version {summary.rubric_version}. They are
        anonymised: you see an alias, never a name, until you reveal them.
      </PageHeader>
      {loaded.data ? (
        <ShortlistView
          data={loaded.data}
          scorer={scorer}
          reload={loaded.reload}
          set={loaded.set}
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
  set: (data: ShortlistData) => void
  compared: Compared[]
  setCompared: (compared: Compared[]) => void
  view: LevelView
  setView: (view: LevelView) => void
}

function ShortlistView({ data, scorer, reload, set, compared, setCompared, view, setView }: ViewProps) {
  const { name, summary } = useJob()
  const [matching, setMatching] = useState(false)
  const people = new Map(data.candidates.map((c) => [c.profile_id, c]))
  const criteria = new Map(data.rubric.criteria.map((c) => [c.id, c]))
  const reveals = data.intents.filter((i) => i.kind === 'reveal').length

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

  async function ask(candidate: AnonymousCandidate, kind: IntentKind) {
    try {
      const intent = await api.recordIntent(name, candidate.profile_id, kind)
      if (!data.intents.some((i) => i.id === intent.id)) set({ ...data, intents: [...data.intents, intent] })
      toast.success(
        kind === 'reveal'
          ? `Reveal of ${candidate.alias} recorded. No payment is taken yet, and who they are stays hidden until revealing is built.`
          : `Application request to ${candidate.alias} recorded. They aren't contacted yet.`,
      )
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
              Reveals: {reveals} of {data.reveal_quota}
            </span>
            {matchButton}
          </div>
        </div>
        <ol className="space-y-3">
          {data.ranking.candidates.map((r) => {
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
                intents={new Set(data.intents.filter((i) => i.profile_id === c.profile_id).map((i) => i.kind))}
                revealsLeft={reveals < data.reveal_quota}
                onAsk={(kind) => ask(c, kind)}
              />
            )
          })}
        </ol>
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
  candidate: AnonymousCandidate
  criteria: Map<string, Criterion>
  scorer: Scorer
  compared: boolean
  canCompare: boolean
  onCompare: () => void
  intents: Set<IntentKind>
  revealsLeft: boolean
  onAsk: (kind: IntentKind) => Promise<void>
}

function CandidateCard({
  ranked,
  candidate,
  criteria,
  scorer,
  compared,
  canCompare,
  onCompare,
  intents,
  revealsLeft,
  onAsk,
}: CardProps) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<IntentKind | null>(null)
  const failed = (ranked.hard_filters ?? []).filter((f) => f.outcome === 'fail')
  const unknown = (ranked.hard_filters ?? []).filter((f) => f.outcome === 'unknown')
  const detailsId = `details-${candidate.profile_id}`
  const compareId = `compare-${candidate.profile_id}`

  async function ask(kind: IntentKind) {
    setBusy(kind)
    await onAsk(kind)
    setBusy(null)
  }

  return (
    <li>
      <Card className={cn('gap-0 py-0', !ranked.passed_hard_filters && 'bg-muted/40')}>
        <div className="flex flex-wrap items-start gap-4 p-5">
          <span
            className={cn(
              'flex size-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold',
              ranked.passed_hard_filters ? 'bg-accent text-primary' : 'bg-muted text-muted-foreground',
            )}
            aria-label={`Rank ${ranked.rank}`}
          >
            {ranked.rank}
          </span>
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-medium">{candidate.alias}</h3>
              {intents.has('reveal') && (
                <Badge variant="secondary">
                  <Eye aria-hidden /> Reveal requested
                </Badge>
              )}
              {intents.has('request_application') && (
                <Badge variant="secondary">
                  <Mail aria-hidden /> Application requested
                </Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground">{candidate.headline}</p>
            {failed.length > 0 ? (
              <p className="flex items-start gap-1.5 text-sm">
                <X className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
                <span>
                  <span className="font-medium">Fails a hard filter:</span> {failed.map((f) => f.reason).join('; ')}
                </span>
              </p>
            ) : (
              <ScoreBar value={ranked.total} label={`Total for ${candidate.alias}`} />
            )}
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
          <span className="flex-1" />
          <Button
            variant="outline"
            size="sm"
            disabled={busy !== null || intents.has('reveal') || !revealsLeft}
            title={!revealsLeft && !intents.has('reveal') ? 'All reveals for this job are used' : undefined}
            aria-label={`${intents.has('reveal') ? 'Reveal requested' : 'Reveal'} ${candidate.alias}`}
            onClick={() => ask('reveal')}
          >
            {busy === 'reveal' ? <Loader2 className="animate-spin" aria-hidden /> : intents.has('reveal') ? <Check aria-hidden /> : <Eye aria-hidden />}
            {intents.has('reveal') ? 'Reveal requested' : 'Reveal'}
          </Button>
          <Button
            size="sm"
            disabled={busy !== null || intents.has('request_application')}
            aria-label={`${intents.has('request_application') ? 'Application requested' : 'Request application'} from ${candidate.alias}`}
            onClick={() => ask('request_application')}
          >
            {busy === 'request_application' ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : intents.has('request_application') ? (
              <Check aria-hidden />
            ) : (
              <Mail aria-hidden />
            )}
            {intents.has('request_application') ? 'Application requested' : 'Request application'}
          </Button>
        </div>

        {open && (
          <div id={detailsId} className="space-y-6 border-t px-5 py-5">
            <Reasons ranked={ranked} candidate={candidate} criteria={criteria} scorer={scorer} />
            {ranked.hard_filters && ranked.hard_filters.length > 0 && <Filters checks={ranked.hard_filters} />}
            <Roles candidate={candidate} />
          </div>
        )}
      </Card>
    </li>
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
        className={cn('flex-1 overflow-hidden rounded-full bg-muted', small ? 'h-1.5 max-w-32' : 'h-2 max-w-64')}
      >
        <div className="h-full rounded-full bg-primary" style={{ width: `${percent}%` }} />
      </div>
      <span className={cn('tabular-nums', small ? 'text-xs text-muted-foreground' : 'text-sm font-medium')}>
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
}: {
  ranked: RankedCandidate
  candidate: AnonymousCandidate
  criteria: Map<string, Criterion>
  scorer: Scorer
}) {
  const quotes = new Map(candidate.evidence.map((e) => [e.id, e]))
  const scores = new Map(ranked.criterion_scores.map((s) => [s.criterion_id, s]))
  if (!ranked.passed_hard_filters) {
    return <p className="text-sm text-muted-foreground">Not scored: candidates who fail a hard filter aren't scored.</p>
  }
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

function Roles({ candidate }: { candidate: AnonymousCandidate }) {
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
              · {x.organisation} · {month(x.start) || '?'} – {x.end ? month(x.end) : 'now'}
            </span>
            {x.summary && <p className="text-muted-foreground">{x.summary}</p>}
          </li>
        ))}
      </ul>
    </section>
  )
}
