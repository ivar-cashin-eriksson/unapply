import { BadgeCheck, Briefcase, Download, FileUp, MapPin, Pencil } from 'lucide-react'
import { Link } from 'react-router'

import { ContactCard } from '@/components/ContactCard'
import { LevelChip } from '@/components/LevelChips'
import { EmptyState, ErrorAlert, Loading, PageHeader } from '@/components/states'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { api } from '@/lib/api'
import { CATEGORIES, categoryLabel, period, WORK_MODES } from '@/lib/format'
import type { CandidateProfile, CandidateSkill } from '@/lib/types'
import { useResource } from '@/lib/useResource'
import { TRANSPARENCY, useCandidate } from '@/pages/candidate/context'

/** Step 4: the profile as employers will see it once approved. No assessment. */
export function Profile() {
  const { name, summary } = useCandidate()
  const loaded = useResource(() => api.profile(name), `${name}:${summary.history.length}`)

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
  if (!loaded.data) {
    return loaded.error ? <ErrorAlert error={loaded.error} /> : <Loading label="Loading your profile" />
  }
  const profile = loaded.data

  return (
    <>
      <PageHeader
        title={profile.headline || 'Your profile'}
        actions={
          <>
            <Button variant="outline" asChild>
              <Link to="../review">
                <Pencil aria-hidden /> Edit
              </Link>
            </Button>
            <Button variant="outline" onClick={() => download(name, profile)}>
              <Download aria-hidden /> Download
            </Button>
          </>
        }
      >
        {profile.approved_by_candidate_at ? (
          <span className="inline-flex items-center gap-1.5 text-sm">
            <BadgeCheck className="size-4 text-primary" aria-hidden />
            Approved on {new Date(profile.approved_by_candidate_at).toLocaleDateString()}
          </span>
        ) : (
          <span className="text-sm">A draft: employers see it once you approve it.</span>
        )}
      </PageHeader>

      {!profile.approved_by_candidate_at && (
        <Alert className="mb-6" role="note">
          <BadgeCheck aria-hidden />
          <AlertTitle>Not approved yet</AlertTitle>
          <AlertDescription>
            <span>
              Check it and approve it in <Link to="../review" className="underline">Review</Link>.
            </span>
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_18rem]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Briefcase className="size-4 text-primary" aria-hidden /> Experience
            </CardTitle>
          </CardHeader>
          <CardContent>
            {profile.experiences.length ? (
              <ol className="relative space-y-6 border-l pl-6">
                {profile.experiences.map((x) => (
                  <li key={x.id} className="relative">
                    <span className="absolute top-1.5 -left-[1.95rem] size-3 rounded-full border-2 border-background bg-primary" aria-hidden />
                    <p className="font-medium">
                      {x.title} <span className="font-normal text-muted-foreground">· {x.organisation}</span>
                    </p>
                    {period(x.start, x.end, x.start_precision, x.end_precision) && (
                      <p className="text-sm text-muted-foreground">{period(x.start, x.end, x.start_precision, x.end_precision)}</p>
                    )}
                    {x.summary && <p className="mt-1.5 text-sm leading-relaxed">{x.summary}</p>}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-sm text-muted-foreground">No experience listed.</p>
            )}
          </CardContent>
        </Card>
        <div className="space-y-6">
          <LookingFor profile={profile} />
          <ContactCard candidate={name} demo={summary.demo} />
        </div>
      </div>

      <section aria-labelledby="skills-title" className="mt-8 space-y-4">
        <h2 id="skills-title" className="text-lg font-semibold">
          Skills
        </h2>
        <SkillGroups skills={profile.skills} />
      </section>
      <p className="mt-8 text-sm text-muted-foreground">{TRANSPARENCY}</p>
    </>
  )
}

function LookingFor({ profile }: { profile: CandidateProfile }) {
  const p = profile.preferences
  const modes = p.work_modes.map((m) => WORK_MODES.find((w) => w.value === m)?.label ?? m)
  const rows: [string, string][] = [
    ['Where', p.locations.join(', ') || 'Anywhere'],
    ['How', modes.join(', ') || 'Any work mode'],
    ['Salary', p.salary_min ? `From ${p.salary_min.toLocaleString()} ${p.salary_currency ?? ''}`.trim() : 'Not given'],
    ['Work permits', p.work_permits.join(', ') || 'Not given'],
  ]
  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <MapPin className="size-4 text-primary" aria-hidden /> Looking for
        </CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="space-y-3 text-sm">
          {rows.map(([k, v]) => (
            <div key={k}>
              <dt className="text-muted-foreground">{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
          {p.dealbreakers.length > 0 && (
            <div>
              <dt className="text-muted-foreground">Dealbreakers</dt>
              <dd>
                <ul className="list-disc pl-4">
                  {p.dealbreakers.map((d) => (
                    <li key={d}>{d}</li>
                  ))}
                </ul>
              </dd>
            </div>
          )}
        </dl>
      </CardContent>
    </Card>
  )
}

function SkillGroups({ skills }: { skills: CandidateSkill[] }) {
  const groups = [...CATEGORIES.map((c) => c.value), null]
    .map((category) => ({
      category,
      skills: skills
        .filter((s) => s.category === category)
        .sort((a, b) => (b.self_level ?? 0) - (a.self_level ?? 0) || a.name.localeCompare(b.name)),
    }))
    .filter((g) => g.skills.length)
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {groups.map((g) => (
        <Card key={g.category ?? 'other'} className="py-0">
          <CardContent className="space-y-3 p-5">
            <h3 className="text-sm font-medium text-muted-foreground">{categoryLabel(g.category)}</h3>
            <ul className="space-y-2">
              {g.skills.map((s) => (
                <li key={s.name} className="flex items-center justify-between gap-3">
                  <span>{s.name}</span>
                  {s.self_level ? <LevelChip level={s.self_level} /> : <Badge variant="outline">Not rated</Badge>}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

/** Save the profile as the candidate sees it, as JSON. */
function download(name: string, profile: CandidateProfile) {
  const blob = new Blob([JSON.stringify(profile, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${name}-profile.json`
  a.click()
  URL.revokeObjectURL(url)
}
