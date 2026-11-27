import { Briefcase, PlayCircle, Users } from 'lucide-react'
import { Outlet, useParams } from 'react-router'

import { DemoButton } from '@/components/DemoButton'
import { StartPage } from '@/components/StartPage'
import { ErrorAlert, Loading } from '@/components/states'
import { Steps } from '@/components/Steps'
import { Badge } from '@/components/ui/badge'
import { api } from '@/lib/api'
import { useResource } from '@/lib/useResource'
import type { JobContext } from '@/pages/employer/context'

/** The employer's start page: open a job, create one or try the demo. */
export function JobList() {
  return (
    <StartPage
      title="Jobs"
      intro="Paste your job ad, check the rubric we draft from it, and approve it. Candidates never see the rubric. Then see the anonymised shortlist."
      list={api.jobs}
      create={(name) => api.createJob(name, '')}
      to={(name) => `/jobs/${name}/ad`}
      icon={Briefcase}
      noun="job"
      placeholder="senior-data-scientist"
      empty="Create one on the right, or try the Fjord Grocery demo: it replays a recorded rubric, so it costs nothing."
      demo={
        <>
          <DemoButton create={api.createDemoJob} to={(n) => `/jobs/${n}/ad`} variant="outline">
            <PlayCircle aria-hidden /> Try the Fjord Grocery demo
          </DemoButton>
          <DemoButton create={api.createShortlistDemo} to={(n) => `/jobs/${n}/shortlist`} variant="outline">
            <Users aria-hidden /> Try the shortlist demo
          </DemoButton>
        </>
      }
    />
  )
}

/** A job's steps: the ad, the rubric, then the shortlist. */
export function JobFlow() {
  const { name = '' } = useParams()
  const summary = useResource(() => api.job(name), name)
  if (!summary.data) {
    return summary.error ? <ErrorAlert error={summary.error} title={`Couldn't open ${name}`} /> : <Loading />
  }
  const s = summary.data
  const steps = [
    { to: 'ad', label: 'Job ad', done: s.has_rubric },
    { to: 'rubric', label: 'Rubric', done: s.approved, locked: !s.has_rubric },
    { to: 'shortlist', label: 'Shortlist', done: false, locked: !s.approved },
  ]
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
        <Briefcase className="size-4" aria-hidden />
        <span className="font-medium text-foreground">
          {s.ad.title && s.ad.company ? `${s.ad.title} · ${s.ad.company}` : name}
        </span>
        {s.demo && (
          <Badge variant="secondary" title="Replays recorded answers: free">
            Demo
          </Badge>
        )}
      </div>
      <Steps steps={steps} label="Job steps" />
      <Outlet context={{ name, summary: s, refresh: summary.reload } satisfies JobContext} />
    </>
  )
}
