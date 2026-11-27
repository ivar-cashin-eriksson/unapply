import { ArrowRight, Briefcase, FileUp, ListChecks, MessagesSquare, PlayCircle, UserRound } from 'lucide-react'
import { Link } from 'react-router'

import { DemoButton } from '@/components/DemoButton'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { api } from '@/lib/api'

const CANDIDATE_STEPS = [
  { icon: FileUp, title: 'Upload', text: 'Your CV, other documents, a LinkedIn export and your GitHub.' },
  { icon: ListChecks, title: 'Review', text: 'Check what was found, rate your own skills and approve.' },
  { icon: MessagesSquare, title: 'Answer', text: "A few questions about skills your documents don't show well." },
]

/** What unapply is, and the way in for each side. */
export function Home() {
  return (
    <div className="space-y-12">
      <section className="space-y-4 pt-6">
        <p className="text-sm font-medium text-primary">Apply without applying</p>
        <h1 className="max-w-2xl text-4xl font-semibold tracking-tight">
          Upload your material once. Write applications only when they count.
        </h1>
        <p className="max-w-2xl text-lg text-muted-foreground">
          We turn your material into a profile you check and approve, ask a few
          questions where your documents say too little, and match you with jobs.
          Employers see an anonymised, explained shortlist, and ask for application
          material only from the people they pick.
        </p>
      </section>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <UserRound className="size-5 text-primary" aria-hidden />
              For candidates
            </CardTitle>
            <CardDescription>Build your profile in three steps.</CardDescription>
          </CardHeader>
          <CardContent className="flex-1">
            <ol className="space-y-4">
              {CANDIDATE_STEPS.map(({ icon: Icon, title, text }, i) => (
                <li key={title} className="flex gap-3">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
                    <Icon className="size-4" aria-hidden />
                  </span>
                  <div>
                    <p className="font-medium">
                      {i + 1}. {title}
                    </p>
                    <p className="text-sm text-muted-foreground">{text}</p>
                  </div>
                </li>
              ))}
            </ol>
          </CardContent>
          <CardFooter className="flex flex-wrap gap-2">
            <Button asChild>
              <Link to="/candidates">
                Start <ArrowRight aria-hidden />
              </Link>
            </Button>
            <DemoButton
              create={api.createDemoCandidate}
              to={(name) => `/candidates/${name}/material`}
              variant="outline"
            >
              <PlayCircle aria-hidden /> Try the John Doe demo
            </DemoButton>
          </CardFooter>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Briefcase className="size-5 text-primary" aria-hidden />
              For employers
            </CardTitle>
            <CardDescription>Turn your job ad into a rubric you control.</CardDescription>
          </CardHeader>
          <CardContent className="flex-1 space-y-3 text-sm text-muted-foreground">
            <p>
              Paste the ad as you would post it. We draft the hard filters (location,
              work mode, work permit, years of experience) and the weighted must-haves
              and nice-to-haves, each quoting your ad.
            </p>
            <p>
              You edit and approve the rubric. Candidates never see it, so they can't
              tailor their profile to it.
            </p>
          </CardContent>
          <CardFooter className="flex flex-wrap gap-2">
            <Button asChild>
              <Link to="/jobs">
                Post a job <ArrowRight aria-hidden />
              </Link>
            </Button>
            <DemoButton
              create={api.createDemoJob}
              to={(name) => `/jobs/${name}/ad`}
              variant="outline"
            >
              <PlayCircle aria-hidden /> Try the Fjord Grocery demo
            </DemoButton>
          </CardFooter>
        </Card>
      </div>

      <p className="text-sm text-muted-foreground">
        The demos replay recorded answers, so they cost nothing.
      </p>
    </div>
  )
}
