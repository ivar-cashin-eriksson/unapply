import { BadgeCheck, MessagesSquare, Send, Wand2, X } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { EmptyState, ErrorAlert, Loading, PageHeader, Working } from '@/components/states'
import { WhyDisabled } from '@/components/WhyDisabled'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { api, describeError } from '@/lib/api'
import type { Questions as QuestionsData } from '@/lib/types'
import { useResource } from '@/lib/useResource'
import { interviewed, TRANSPARENCY, useCandidate } from '@/pages/candidate/context'

/** Step 3: answer questions about skills the documents don't show enough of. */
export function Questions() {
  const { name, summary, refresh } = useCandidate()
  const loaded = useResource(() => api.questions(name), `${name}:${summary.history.length}`)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<'prepare' | 'send' | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [none, setNone] = useState(false)
  const navigate = useNavigate()


  if (!summary.approved) {
    return (
      <EmptyState
        icon={BadgeCheck}
        title="Approve your profile first"
        action={
          <Button asChild>
            <Link to="../review">Review your profile</Link>
          </Button>
        }
      >
        Questions are about the skills you rated, so they come after your review.
      </EmptyState>
    )
  }
  if (!loaded.data) {
    return loaded.error ? <ErrorAlert error={loaded.error} /> : <Loading label="Loading your questions" />
  }
  const data: QuestionsData = loaded.data
  const filled = Object.values(answers).filter((a) => a.trim()).length

  async function prepare() {
    setBusy('prepare')
    setError(null)
    setNone(false)
    try {
      const prepared = await api.prepareQuestions(name)
      loaded.set(prepared)
      setNone(prepared.waiting.length === 0)
      await refresh()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(null)
    }
  }

  async function send() {
    setBusy('send')
    setError(null)
    try {
      const result = await api.answer(name, { answers })
      if (result.answered === 0) {
        toast.info('Write at least one answer first.')
      } else {
        toast.success(`Thanks: ${result.answered} ${result.answered === 1 ? 'answer' : 'answers'} added to your profile.`)
        await refresh()
        navigate('../profile')
      }
    } catch (e) {
      setError(e)
    } finally {
      setBusy(null)
    }
  }

  async function discard() {
    try {
      await api.discardQuestions(name)
      await refresh()
    } catch (e) {
      toast.error(describeError(e))
    }
  }

  async function fillDemo() {
    try {
      setAnswers((await api.demoAnswers(name)).answers)
      toast.info("John's answers are filled in. Read them, then send.")
    } catch (e) {
      toast.error(describeError(e))
    }
  }

  if (data.waiting.length) {
    return (
      <>
        <PageHeader
          title="A few questions"
          actions={
            summary.demo && (
              <Button variant="outline" onClick={fillDemo}>
                <Wand2 aria-hidden /> Fill in John's answers
              </Button>
            )
          }
        >
          Specific answers help most: what you did, at roughly what scale, in which
          role and when. Skip any you'd rather not answer.
        </PageHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            send()
          }}
        >
          {data.waiting.map((q, i) => (
            <Card key={q.skill}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <span className="text-muted-foreground">{i + 1}.</span>
                  <Badge variant="secondary">{q.skill}</Badge>
                </CardTitle>
                <CardDescription>{q.why}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                <Label htmlFor={`answer-${i}`} className="text-base leading-relaxed font-normal">
                  {q.text}
                </Label>
                <Textarea
                  id={`answer-${i}`}
                  rows={4}
                  value={answers[q.skill] ?? ''}
                  placeholder="Your answer"
                  onChange={(e) => setAnswers({ ...answers, [q.skill]: e.target.value })}
                />
              </CardContent>
            </Card>
          ))}
          <ErrorAlert error={error} title="Couldn't send your answers" />
          <div className="flex flex-wrap items-center gap-3">
            <WhyDisabled reason={filled === 0 && 'Answer at least one question first'}>
              <Button type="submit" size="lg" disabled={busy !== null || filled === 0}>
                <Send aria-hidden /> Send {filled || ''} {filled === 1 ? 'answer' : 'answers'}
              </Button>
            </WhyDisabled>
            <Button type="button" variant="ghost" onClick={discard} disabled={busy !== null}>
              <X aria-hidden /> Not now
            </Button>
            {busy === 'send' && <Working>Adding your answers…</Working>}
          </div>
          <p className="text-sm text-muted-foreground">
            Questions you leave empty are dropped. {TRANSPARENCY}
          </p>
        </form>
      </>
    )
  }

  return (
    <>
      <PageHeader title="A few questions">
        We ask about skills your documents say little about. Specific answers help
        most: what you did, at roughly what scale, in which role and when. Answers
        are kept as your own statements, next to the question.
      </PageHeader>
      <div className="space-y-6">
        <EmptyState
          icon={MessagesSquare}
          title={none ? 'No questions for now' : interviewed(summary) ? 'Want to add more?' : 'Ready when you are'}
          action={
            <Button onClick={prepare} disabled={busy !== null}>
              <MessagesSquare aria-hidden />
              {interviewed(summary) ? 'Ask me more questions' : 'Prepare my questions'}
            </Button>
          }
        >
          {none
            ? 'Your documents already cover the skills you rated.'
            : 'Up to eight short questions. It takes a moment to prepare them.'}
        </EmptyState>
        {busy === 'prepare' && <Working>Preparing your questions. This can take a minute.</Working>}
        <ErrorAlert error={error} title="Couldn't prepare questions" />
        <p className="text-sm text-muted-foreground">{TRANSPARENCY}</p>
        {data.answered.length > 0 && <Answered data={data} />}
      </div>
    </>
  )
}

function Answered({ data }: { data: QuestionsData }) {
  return (
    <section aria-labelledby="answered-title" className="space-y-3">
      <h2 id="answered-title" className="text-lg font-semibold">
        Your answers
      </h2>
      {data.answered.map((q, i) => (
        <Card key={i} className="py-0">
          <CardContent className="space-y-2 p-5">
            <Badge variant="secondary">{q.skill}</Badge>
            <p className="text-sm text-muted-foreground">{q.text}</p>
            <p>{q.answer}</p>
          </CardContent>
        </Card>
      ))}
    </section>
  )
}
