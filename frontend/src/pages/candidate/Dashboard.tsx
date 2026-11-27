import { Briefcase, FileUp, Lightbulb, Sprout, Users } from 'lucide-react'
import { Link } from 'react-router'

import { FitBadge } from '@/components/FitBadge'
import { LevelChip } from '@/components/LevelChips'
import { LevelDistribution } from '@/components/LevelDistribution'
import { StageBadge } from '@/components/StageBadge'
import { EmptyState, ErrorAlert, Loading, PageHeader } from '@/components/states'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { api } from '@/lib/api'
import { categoryLabel } from '@/lib/format'
import type { CandidateJobs, Dashboard as DashboardData, DashboardSkill, JobOutcome } from '@/lib/types'
import { useResource } from '@/lib/useResource'
import { TRANSPARENCY, useCandidate } from '@/pages/candidate/context'

/** Step 5: the candidate's own profile in overview: skills, how they compare, what to develop. */
export function Dashboard() {
  const { summary } = useCandidate()
  if (!summary.has_profile) {
    return (
      <EmptyState
        icon={FileUp}
        title="No profile yet"
        action={
          <Button asChild>
            <Link to="../material">Go to your material</Link>
          </Button>
        }
      >
        Build a profile from your material first.
      </EmptyState>
    )
  }
  return <DashboardPage />
}

function DashboardPage() {
  const { name, summary } = useCandidate()
  const loaded = useResource(() => api.dashboard(name), `${name}:${summary.history.length}`)
  return (
    <div className="space-y-8">
      <PageHeader title="Your dashboard">
        Your skills by area with your own levels and how often your material mentions each, how your levels compare
        with other candidates&apos; own levels, skills worth developing, and how far you got on the jobs you connected
        to.
      </PageHeader>
      {loaded.data ? (
        <DashboardView data={loaded.data} />
      ) : loaded.error ? (
        <ErrorAlert error={loaded.error} title="Couldn't load your dashboard" />
      ) : (
        <Loading label="Loading your dashboard" />
      )}
      <YourJobs />
      <p className="text-sm text-muted-foreground">{TRANSPARENCY}</p>
    </div>
  )
}

function DashboardView({ data }: { data: DashboardData }) {
  return (
    <>
      <dl aria-label="Your profile in numbers" className="grid gap-4 sm:grid-cols-4">
        <Stat label="Skills" value={data.skills} note={`${data.rated} with your level`} />
        <Stat label="Quotes from your documents" value={data.documents} />
        <Stat label="Your own statements" value={data.statements} note="Answers and notes" />
        <Stat
          label="Compared with"
          value={data.compared_with || '–'}
          note={data.compared_with ? 'other candidates' : `Needs at least ${data.min_group} others`}
        />
      </dl>

      {data.compared_with === 0 && (
        <p role="note" className="flex items-start gap-2 text-sm text-muted-foreground">
          <Users className="mt-0.5 size-4 shrink-0" aria-hidden />
          Comparisons appear once at least {data.min_group} other candidates have approved profiles, so no one can be
          singled out.
        </p>
      )}

      <section aria-labelledby="areas-title" className="space-y-4">
        <h2 id="areas-title" className="text-lg font-semibold">
          Your skills by area
        </h2>
        <div className="grid gap-4 lg:grid-cols-2">
          {data.areas.map((a) => (
            <Card key={a.category ?? 'other'} className="py-0">
              <CardContent className="space-y-3 p-5">
                <h3 className="text-sm font-medium text-muted-foreground">{categoryLabel(a.category)}</h3>
                <ul aria-label={categoryLabel(a.category)} className="divide-y">
                  {a.skills.map((s) => (
                    <SkillRow key={s.name} skill={s} compared={data.compared_with > 0} min={data.min_group} />
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <Tips data={data} />
    </>
  )
}

function SkillRow({ skill: s, compared, min }: { skill: DashboardSkill; compared: boolean; min: number }) {
  return (
    <li className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 py-2.5 sm:grid-cols-[1fr_auto_8rem]">
      <div className="min-w-0">
        <p className="truncate font-medium">{s.name}</p>
        <p className="text-xs text-muted-foreground">{mentions(s)}</p>
      </div>
      <div>{s.self_level ? <LevelChip level={s.self_level} /> : <Badge variant="outline">Not rated</Badge>}</div>
      <div className="col-span-2 sm:col-span-1">
        {s.comparison ? (
          <LevelDistribution comparison={s.comparison} own={s.self_level} skill={s.name} />
        ) : compared ? (
          <p className="text-xs text-muted-foreground">Fewer than {min} others rated it</p>
        ) : null}
      </div>
    </li>
  )
}

/** "3 quotes from your documents, 1 of your statements". */
function mentions(s: DashboardSkill): string {
  const parts = []
  if (s.documents) parts.push(`${s.documents} quote${s.documents === 1 ? '' : 's'} from your documents`)
  if (s.statements) parts.push(`${s.statements} of your statements`)
  return parts.join(', ') || 'Not mentioned in your material'
}

function Tips({ data }: { data: DashboardData }) {
  return (
    <section aria-labelledby="tips-title" className="space-y-4">
      <h2 id="tips-title" className="text-lg font-semibold">
        Skills to develop
      </h2>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Lightbulb className="size-4 text-primary" aria-hidden /> Asked for on the job board
            </CardTitle>
            <CardDescription>The skills jobs on the board ask for most that your profile doesn&apos;t list.</CardDescription>
          </CardHeader>
          <CardContent>
            {data.in_demand.length ? (
              <ol aria-label="Asked for on the job board" className="flex flex-wrap gap-2">
                {data.in_demand.map((s) => (
                  <li key={s}>
                    <Badge variant="secondary">{s}</Badge>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-sm text-muted-foreground">
                Nothing yet: your profile lists every skill the jobs on the board ask for, or there are no jobs yet.
              </p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Sprout className="size-4 text-primary" aria-hidden /> Follow from your skills
            </CardTitle>
            <CardDescription>
              Skills that come with ones you have. If you have them, add them in{' '}
              <Link to="../review" className="underline">
                Review
              </Link>
              .
            </CardDescription>
          </CardHeader>
          <CardContent>
            {data.following.length ? (
              <ul aria-label="Follow from your skills" className="space-y-2 text-sm">
                {data.following.map((f) => (
                  <li key={f.skill}>
                    <span className="font-medium">{f.skill}</span>
                    <span className="text-muted-foreground"> · from {f.because.join(', ')}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">Nothing to add: your profile has them all.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </section>
  )
}

/** The jobs the candidate connected to, how far they got, and their success rate. */
function YourJobs() {
  const { name, summary } = useCandidate()
  const loaded = useResource(() => api.candidateJobs(name), `${name}:${summary.history.length}`)
  return (
    <section aria-labelledby="your-jobs-title" className="space-y-4">
      <h2 id="your-jobs-title" className="text-lg font-semibold">
        Your jobs
      </h2>
      {loaded.data ? (
        <JobsView data={loaded.data} />
      ) : loaded.error ? (
        <ErrorAlert error={loaded.error} title="Couldn't load your jobs" />
      ) : (
        <Loading label="Loading your jobs" />
      )}
    </section>
  )
}

function JobsView({ data }: { data: CandidateJobs }) {
  if (!data.jobs.length) {
    return (
      <p className="flex items-start gap-2 text-sm text-muted-foreground">
        <Briefcase className="mt-0.5 size-4 shrink-0" aria-hidden />
        <span>
          You haven&apos;t connected to a job yet. Find one on the{' '}
          <Link to="../jobs" className="underline">
            job board
          </Link>
          .
        </span>
      </p>
    )
  }
  return (
    <>
      <dl aria-label="Your success rate" className="grid gap-4 sm:grid-cols-3">
        <Stat label="Connected" value={data.connected} note={`job${data.connected === 1 ? '' : 's'}`} />
        <Stat label="Revealed" value={percent(data.revealed_rate)} note={`${data.revealed} of ${data.connected}`} />
        <Stat
          label="Asked to apply"
          value={percent(data.requested_rate)}
          note={`${data.requested} of ${data.connected}`}
        />
      </dl>
      <ul aria-label="Jobs you connected to" className="space-y-3">
        {data.jobs.map((j) => (
          <JobRow key={j.job} outcome={j} min={data.min_group} />
        ))}
      </ul>
    </>
  )
}

function JobRow({ outcome: j, min }: { outcome: JobOutcome; min: number }) {
  const tips = j.revealed_skills
  return (
    <li className="space-y-3 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium">
            <Link to={`../jobs/${encodeURIComponent(j.job)}`} className="hover:underline">
              {j.listing?.title ?? j.job}
            </Link>
          </p>
          <p className="text-sm text-muted-foreground">{j.listing?.company ?? 'No longer on the board'}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {j.fit?.band && <FitBadge band={j.fit.band} />}
          <StageBadge stage={j.stage} />
        </div>
      </div>
      {tips ? (
        <div role="group" aria-label={`Common among those revealed: ${j.listing?.title ?? j.job}`} className="space-y-2">
          <p className="text-sm text-muted-foreground">
            Skills common among the candidates this job revealed, from their own levels:
          </p>
          <SkillList label="Not in your profile" skills={tips.missing} />
          <SkillList label="You rated lower than most of them" skills={tips.lower} />
          {!tips.missing.length && !tips.lower.length && (
            <p className="text-sm text-muted-foreground">None: you list them all, at their levels or higher.</p>
          )}
        </div>
      ) : (
        j.stage === 'connected' && (
          <p className="text-xs text-muted-foreground">
            Skills common among the candidates revealed show once at least {min} others are revealed.
          </p>
        )
      )}
    </li>
  )
}

function SkillList({ label, skills }: { label: string; skills: string[] }) {
  if (!skills.length) return null
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span>{label}:</span>
      <ul aria-label={label} className="flex flex-wrap gap-1.5">
        {skills.map((s) => (
          <li key={s}>
            <Badge variant="secondary">{s}</Badge>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** A rate from 0 to 1 as a whole percentage; a dash when there is none. */
function percent(rate: number | null): string {
  return rate === null ? '–' : `${Math.round(rate * 100)}%`
}

function Stat({ label, value, note }: { label: string; value: number | string; note?: string }) {
  return (
    <div className="rounded-xl border bg-card p-4">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tabular-nums">{value}</dd>
      {note && <dd className="text-xs text-muted-foreground">{note}</dd>}
    </div>
  )
}
