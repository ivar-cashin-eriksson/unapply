import { BarChart3, ListOrdered } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Histograms, MeterList, type Meter } from '@/components/OverviewCharts'
import { EmptyState, ErrorAlert, Loading, PageHeader } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { api } from '@/lib/api'
import { FILTERS, vacancies as vacancyText } from '@/lib/format'
import type { Overview as OverviewData, Scorer } from '@/lib/types'
import { useResource } from '@/lib/useResource'
import { useJob } from '@/pages/employer/context'

const ON = 'data-[state=on]:border-primary data-[state=on]:bg-primary data-[state=on]:text-primary-foreground'

const SCORERS: { value: Scorer; label: string; title: string }[] = [
  { value: 'baseline', label: 'Baseline', title: 'Totals from plain code: free and fully repeatable' },
  { value: 'llm', label: 'LLM', title: "Totals from the LLM scorer's stored matches" },
]

/** Step 4: the job's candidates in aggregate. Counts only, never one candidate. */
export function Overview() {
  const { summary } = useJob()
  if (!summary.approved) {
    return (
      <EmptyState
        icon={BarChart3}
        title="Approve the rubric first"
        action={
          <Button asChild>
            <Link to="../rubric">Go to the rubric</Link>
          </Button>
        }
      >
        The overview sums up the candidates matched against an approved rubric.
      </EmptyState>
    )
  }
  return <OverviewPage />
}

function OverviewPage() {
  const { name, summary } = useJob()
  const [scorer, setScorer] = useState<Scorer>('baseline')
  const loaded = useResource(() => api.overview(name, scorer), `${name}:${scorer}:${summary.rubric_version}`)
  return (
    <div className="space-y-8">
      <PageHeader
        title="Overview"
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
        Everyone connected to this job, in aggregate, against rubric version {summary.rubric_version}. Only counts:
        no names, aliases or quotes.
      </PageHeader>
      {loaded.data ? (
        <OverviewView data={loaded.data} />
      ) : loaded.error ? (
        <ErrorAlert error={loaded.error} title="Couldn't load the overview" />
      ) : (
        <Loading label="Loading the overview" />
      )}
    </div>
  )
}

function OverviewView({ data }: { data: OverviewData }) {
  const matched = data.matched
  return (
    <>
      <dl aria-label="Candidates" className="grid gap-4 sm:grid-cols-4">
        <Stat label="Connected" value={data.connected} />
        <Stat
          label="Matched"
          value={matched}
          note={data.scorer === 'llm' ? 'by the LLM scorer' : 'by the baseline scorer'}
        />
        <Stat
          label="Meet every requirement"
          value={data.passed_hard_filters}
          note={matched ? `of ${matched} matched` : undefined}
        />
        <Stat label="Vacancies" value={data.vacancies} />
      </dl>

      <Funnel data={data} />

      {matched === 0 ? (
        <EmptyState
          icon={ListOrdered}
          title="No one is matched yet"
          action={
            <Button asChild>
              <Link to="../shortlist">Go to the shortlist</Link>
            </Button>
          }
        >
          Match the connected candidates on the shortlist
          {data.scorer === 'llm' ? ' with the LLM scorer' : ''}, then come back for their scores and skills.
        </EmptyState>
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Scores</CardTitle>
              <CardDescription>
                How many of the {matched} matched candidates scored in each tenth, from 0 to 1, on one shared scale.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Histograms
                series={[
                  {
                    key: 'totals',
                    label: data.scorer === 'llm' ? 'LLM total' : 'Baseline total',
                    description: 'Sets the rank.',
                    distribution: data.totals,
                  },
                  {
                    key: 'own',
                    label: 'Own rating',
                    description: "The baseline on candidates' own levels.",
                    distribution: data.own,
                  },
                  {
                    key: 'estimated',
                    label: 'Estimated from evidence',
                    description: 'The baseline on the estimated levels.',
                    distribution: data.estimated,
                  },
                ]}
              />
            </CardContent>
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Requirements data={data} />
            <RubricSkills data={data} />
          </div>
          <OtherSkills data={data} />
        </>
      )}
    </>
  )
}

function Stat({ label, value, note }: { label: string; value: number; note?: string }) {
  return (
    <div className="rounded-xl border bg-card px-5 py-4">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-3xl font-semibold tabular-nums">{value}</dd>
      {note && <dd className="text-xs text-muted-foreground">{note}</dd>}
    </div>
  )
}

function Funnel({ data }: { data: OverviewData }) {
  const { connected, revealed, requested, applied } = data.counts
  const meters: Meter[] = [
    { label: 'Connected', value: connected, of: connected, figure: `${connected}` },
    { label: 'Revealed', value: revealed, of: connected },
    { label: 'Asked to apply', value: requested, of: connected },
    { label: 'Applied', value: applied, of: connected },
  ]
  return (
    <Card>
      <CardHeader>
        <CardTitle>How far candidates got</CardTitle>
        <CardDescription>
          Out of everyone connected. {vacancyText(data.vacancies)}:{' '}
          {applied >= data.vacancies
            ? `${applied} application${applied === 1 ? '' : 's'}, enough to fill ${data.vacancies === 1 ? 'it' : 'them'}.`
            : `${applied} application${applied === 1 ? '' : 's'} so far.`}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <MeterList label="How far candidates got" meters={meters} />
      </CardContent>
    </Card>
  )
}

function Requirements({ data }: { data: OverviewData }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Requirements not met</CardTitle>
        <CardDescription>
          {data.filters.length
            ? `Matched candidates who don't meet each hard filter, the most failed first. ${data.passed_hard_filters} of ${data.matched} meet every one.`
            : 'The rubric sets no hard filters.'}
        </CardDescription>
      </CardHeader>
      {data.filters.length > 0 && (
        <CardContent>
          <MeterList
            label="Requirements not met"
            meters={data.filters.map((f) => ({
              label: FILTERS[f.name],
              value: f.failed,
              of: data.matched,
              figure: `${f.failed} of ${data.matched}`,
              note: f.unknown ? `${f.unknown} not known (not excluded)` : undefined,
            }))}
          />
        </CardContent>
      )}
    </Card>
  )
}

function RubricSkills({ data }: { data: OverviewData }) {
  // Most common first, so the least common skills the rubric asks for end the list.
  const skills = [...data.rubric_skills].sort((a, b) => b.candidates - a.candidates)
  return (
    <Card>
      <CardHeader>
        <CardTitle>The rubric's skills</CardTitle>
        <CardDescription>Matched candidates who list each skill, the most common first.</CardDescription>
      </CardHeader>
      <CardContent>
        {skills.length ? (
          <MeterList
            label="The rubric's skills"
            meters={skills.map((s) => ({
              label: s.skill,
              value: s.candidates,
              of: data.matched,
              note: s.related ? `${s.related} more with a related skill` : undefined,
            }))}
          />
        ) : (
          <p className="text-sm text-muted-foreground">The rubric's criteria name no skills.</p>
        )}
      </CardContent>
    </Card>
  )
}

function OtherSkills({ data }: { data: OverviewData }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Other common skills</CardTitle>
        <CardDescription>Skills the rubric doesn't ask for that the matched candidates list most.</CardDescription>
      </CardHeader>
      <CardContent>
        {data.other_skills.length ? (
          <MeterList
            label="Other common skills"
            className="sm:columns-2 sm:gap-x-10 [&>li]:mb-3 [&>li]:break-inside-avoid"
            meters={data.other_skills.map((s) => ({ label: s.skill, value: s.candidates, of: data.matched }))}
          />
        ) : (
          <p className="text-sm text-muted-foreground">None: every skill listed is one the rubric asks for.</p>
        )}
      </CardContent>
    </Card>
  )
}
