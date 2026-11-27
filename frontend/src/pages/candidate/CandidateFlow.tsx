import { PlayCircle, UserRound } from 'lucide-react'
import { Outlet, useParams } from 'react-router'

import { DemoButton } from '@/components/DemoButton'
import { StartPage } from '@/components/StartPage'
import { ErrorAlert, Loading } from '@/components/states'
import { Steps } from '@/components/Steps'
import { Badge } from '@/components/ui/badge'
import { api } from '@/lib/api'
import { useResource } from '@/lib/useResource'
import { interviewed, type CandidateContext } from '@/pages/candidate/context'

/** The candidate's start page: open one, create one or try the demo. */
export function CandidateList() {
  return (
    <StartPage
      title="Candidates"
      intro="Upload your material once, check the profile we build from it, and answer a few questions. Employers only see profiles you approve."
      list={api.candidates}
      create={(name) => api.createCandidate(name, null)}
      to={(name) => `/candidates/${name}/material`}
      icon={UserRound}
      noun="candidate"
      placeholder="jane-doe"
      empty="Create one on the right, or try the John Doe demo: it replays recorded answers, so it costs nothing."
      demo={
        <DemoButton create={api.createDemoCandidate} to={(n) => `/candidates/${n}/material`} variant="outline">
          <PlayCircle aria-hidden /> Try the John Doe demo
        </DemoButton>
      }
    />
  )
}

/** A candidate's steps: material, review, questions, profile, dashboard and the job board. */
export function CandidateFlow() {
  const { name = '' } = useParams()
  const summary = useResource(() => api.candidate(name), name)

  if (!summary.data) {
    return summary.error ? (
      <ErrorAlert error={summary.error} title={`Couldn't open ${name}`} />
    ) : (
      <Loading />
    )
  }
  const s = summary.data
  const steps = [
    { to: 'material', label: 'Material', done: s.has_profile },
    { to: 'review', label: 'Review', done: s.approved, locked: !s.has_profile },
    { to: 'questions', label: 'Questions', done: interviewed(s), locked: !s.approved },
    { to: 'profile', label: 'Profile', done: s.approved, locked: !s.has_profile },
    { to: 'dashboard', label: 'Dashboard', done: false, locked: !s.has_profile },
    // Anyone can read the board; connecting to a job needs an approved profile.
    { to: 'jobs', label: 'Jobs', done: false },
  ]
  const context: CandidateContext = { name, summary: s, refresh: summary.reload }
  return (
    <>
      <div className="mb-4 flex items-center gap-2 text-sm text-muted-foreground">
        <UserRound className="size-4" aria-hidden />
        <span className="font-medium text-foreground">{name}</span>
        {s.demo && (
          <Badge variant="secondary" title="Replays recorded answers: free">
            Demo
          </Badge>
        )}
      </div>
      <Steps steps={steps} label="Your steps" />
      <Outlet context={context} />
    </>
  )
}
