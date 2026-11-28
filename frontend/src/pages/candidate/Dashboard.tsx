import { type ReactNode, useId, useState } from 'react'
import { ArrowDown, ArrowUp, Briefcase, FileUp, Lightbulb, Sprout, Users } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'

import { FitBadge } from '@/components/FitBadge'
import { GroupSpider } from '@/components/GroupSpider'
import { LevelChip } from '@/components/LevelChips'
import { LevelDistribution } from '@/components/LevelDistribution'
import { StageBadge } from '@/components/StageBadge'
import { WhyDisabled } from '@/components/WhyDisabled'
import { EmptyState, ErrorAlert, Loading, PageHeader } from '@/components/states'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { api } from '@/lib/api'
import { categoryLabel } from '@/lib/format'
import type {
  CandidateJobs,
  Dashboard as DashboardData,
  DashboardSkill,
  Group,
  GroupComparison,
  JobOutcome,
} from '@/lib/types'
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

/** The dashboard's sheets, kept in the address as `?sheet=` so they can be linked. */
const SHEETS = ['profile', 'jobs', 'compare'] as const
type Sheet = (typeof SHEETS)[number]

function DashboardPage() {
  const { name, summary } = useCandidate()
  const key = `${name}:${summary.history.length}`
  const loaded = useResource(() => api.dashboard(name), key)
  const jobs = useResource(() => api.candidateJobs(name), key)
  const [params, setParams] = useSearchParams()
  const asked = params.get('sheet') as Sheet | null
  const sheet: Sheet = asked && SHEETS.includes(asked) ? asked : 'profile'
  const open = (next: Sheet, job?: string) => {
    const p = new URLSearchParams(params)
    p.set('sheet', next)
    if (job) p.set('job', job)
    else if (next !== 'compare') p.delete('job')
    setParams(p, { replace: true })
  }
  const jobsOr = (view: (data: CandidateJobs) => ReactNode) =>
    jobs.data ? (
      view(jobs.data)
    ) : jobs.error ? (
      <ErrorAlert error={jobs.error} title="Couldn't load your jobs" />
    ) : (
      <Loading label="Loading your jobs" />
    )
  return (
    <div className="space-y-8">
      <PageHeader title="Your dashboard">
        Your skills by area with your own levels and how often your material mentions each, how your levels compare
        with other candidates&apos; own levels, how far you got on the jobs you connected to, and how you compare with
        the others on each job.
      </PageHeader>
      <Tabs value={sheet} onValueChange={(v) => open(v as Sheet)}>
        <TabsList className="flex-wrap">
          <TabsTrigger value="profile">Your profile</TabsTrigger>
          <TabsTrigger value="jobs">Your jobs</TabsTrigger>
          <TabsTrigger value="compare">Compared on jobs</TabsTrigger>
        </TabsList>
        <TabsContent value="profile" className="space-y-8 pt-4">
          {loaded.data ? (
            <DashboardView data={loaded.data} />
          ) : loaded.error ? (
            <ErrorAlert error={loaded.error} title="Couldn't load your dashboard" />
          ) : (
            <Loading label="Loading your dashboard" />
          )}
        </TabsContent>
        <TabsContent value="jobs" className="space-y-4 pt-4">
          {jobsOr((data) => (
            <JobsView data={data} onCompare={(job) => open('compare', job)} />
          ))}
        </TabsContent>
        <TabsContent value="compare" className="space-y-6 pt-4">
          {jobsOr((data) => (
            <CompareView data={data} job={params.get('job')} onJob={(job) => open('compare', job)} />
          ))}
        </TabsContent>
      </Tabs>
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
function JobsView({ data, onCompare }: { data: CandidateJobs; onCompare: (job: string) => void }) {
  if (!data.jobs.length) return <NoJobs />
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
          <JobRow key={j.job} outcome={j} onCompare={() => onCompare(j.job)} />
        ))}
      </ul>
    </>
  )
}

function NoJobs() {
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

function JobRow({ outcome: j, onCompare }: { outcome: JobOutcome; onCompare: () => void }) {
  const title = j.listing?.title ?? j.job
  return (
    <li className="flex flex-wrap items-start justify-between gap-2 rounded-xl border bg-card p-4">
      <div className="min-w-0">
        <p className="font-medium">
          <Link to={`../jobs/${encodeURIComponent(j.job)}`} className="hover:underline">
            {title}
          </Link>
        </p>
        <p className="text-sm text-muted-foreground">{j.listing?.company ?? 'No longer on the board'}</p>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {j.fit?.band && <FitBadge band={j.fit.band} />}
        <StageBadge stage={j.stage} />
        {j.groups.length > 0 && (
          <Button variant="outline" size="sm" onClick={onCompare} aria-label={`Compare with others: ${title}`}>
            Compare with others
          </Button>
        )}
      </div>
    </li>
  )
}

/** What each group of others on a job is called, and how a sentence names them. */
const GROUPS: { value: Group; label: string; them: string }[] = [
  { value: 'revealed', label: 'Revealed', them: 'those the employer revealed' },
  { value: 'requested', label: 'Asked to apply', them: 'those the employer asked to apply' },
  { value: 'applied', label: 'Applied', them: 'those who applied' },
]

/** The candidate next to the groups of others on one job at a time. */
function CompareView({ data, job, onJob }: { data: CandidateJobs; job: string | null; onJob: (job: string) => void }) {
  const id = useId()
  const [picked, setPicked] = useState<Group>('revealed')
  if (!data.jobs.length) return <NoJobs />
  const comparable = data.jobs.filter((j) => j.groups.length)
  const rule = `A group shows once at least ${data.min_group} others on the job are in it, so no one can be singled out.`
  if (!comparable.length) {
    return (
      <p role="note" className="flex items-start gap-2 text-sm text-muted-foreground">
        <Users className="mt-0.5 size-4 shrink-0" aria-hidden />
        <span>
          Nothing to compare yet. Here you&apos;ll see yourself next to the other candidates a job revealed, asked to
          apply, or who applied, whatever your own stage. {rule}
        </span>
      </p>
    )
  }
  const current = comparable.find((j) => j.job === job) ?? comparable[0]
  const group = current.groups.find((g) => g.group === picked) ?? current.groups[0]
  const names = GROUPS.find((g) => g.value === group.group)!
  return (
    <>
      <p className="text-sm text-muted-foreground">
        You next to the other candidates on a job, whatever your own stage, from everyone&apos;s own levels. {rule}
      </p>
      <div className="flex flex-wrap items-end gap-4">
        <div className="min-w-64 space-y-1.5">
          <Label htmlFor={id}>Job</Label>
          <select
            id={id}
            value={current.job}
            onChange={(e) => onJob(e.target.value)}
            className="h-8 w-full rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            {comparable.map((j) => (
              <option key={j.job} value={j.job}>
                {j.listing ? `${j.listing.title} · ${j.listing.company}` : j.job}
              </option>
            ))}
          </select>
        </div>
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          spacing={1}
          aria-label="Compare with"
          value={group.group}
          onValueChange={(v) => v && setPicked(v as Group)}
        >
          {GROUPS.map((g) => {
            const there = current.groups.some((x) => x.group === g.value)
            return (
              <WhyDisabled key={g.value} reason={!there && `Fewer than ${data.min_group} others`} className="rounded-full">
                <ToggleGroupItem value={g.value} disabled={!there} className="rounded-full px-3">
                  {g.label}
                </ToggleGroupItem>
              </WhyDisabled>
            )
          })}
        </ToggleGroup>
      </div>
      <GroupView group={group} label={names.label} them={names.them} />
    </>
  )
}

function GroupView({ group: g, label, them }: { group: GroupComparison; label: string; them: string }) {
  return (
    <div role="group" aria-label={`Compared with: ${label}`} className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ArrowUp className="size-4 text-primary" aria-hidden /> Where you stand out
            </CardTitle>
            <CardDescription>Compared with {them}.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <SkillList label="You rated higher than most of them" skills={g.higher} />
            <SkillList label="You list, few of them do" skills={g.rare} />
            {!g.higher.length && !g.rare.length && (
              <p className="text-sm text-muted-foreground">
                Nothing yet: most of them list your skills, at your levels or higher.
              </p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ArrowDown className="size-4 text-primary" aria-hidden /> Where they&apos;re ahead
            </CardTitle>
            <CardDescription>Skills common among {them}.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <SkillList label="Not in your profile" skills={g.missing} />
            <SkillList label="You rated lower than most of them" skills={g.lower} />
            {!g.missing.length && !g.lower.length && (
              <p className="text-sm text-muted-foreground">None: you list them all, at their levels or higher.</p>
            )}
          </CardContent>
        </Card>
      </div>
      <section aria-labelledby={`${g.group}-chart`} className="space-y-2">
        <h3 id={`${g.group}-chart`} className="text-sm font-medium">
          Your levels next to theirs
        </h3>
        <p className="text-xs text-muted-foreground">The skills they list most, where enough of them gave a level.</p>
        <GroupSpider skills={g.skills} label={label} />
      </section>
    </div>
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
