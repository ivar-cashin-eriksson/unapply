import { CircleHelp, Loader2, Quote, Sparkles } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'

import { ErrorAlert, Loading } from '@/components/states'
import { WhyDisabled } from '@/components/WhyDisabled'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { api, ApiError } from '@/lib/api'
import { MAX_HISTORY, MAX_QUESTION_CHARS, type CandidateAnswer } from '@/lib/types'
import { useResource } from '@/lib/useResource'

interface Props {
  job: string
  profileId: string
  /** Who the questions are about, such as "Astrid Holm". */
  who: string
}

/**
 * Ask a model about a revealed candidate. It answers from the candidate's own
 * material only, citing their quotes, and says when the material doesn't answer.
 * The conversation lives only here, on the open page: nothing is stored, and the
 * earlier questions are sent with each new one. Demo candidates offer suggested
 * questions with recorded answers; any other question is a paid call, which the
 * app never allows, so a server with paid calls off refuses it.
 */
export function AskPanel({ job, profileId, who }: Props) {
  const options = useResource(() => api.askOptions(job, profileId), `${job}:${profileId}`)
  const [turns, setTurns] = useState<CandidateAnswer[]>([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const list = useRef<HTMLOListElement>(null)
  const boxId = useId()

  useEffect(() => {
    const el = list.current
    if (el) el.scrollTop = el.scrollHeight
  }, [turns.length])

  async function ask(question: string) {
    if (!question.trim() || busy) return
    setBusy(true)
    setError(null)
    try {
      const history = turns.slice(-MAX_HISTORY).map((t) => ({ question: t.question, answer: t.answer }))
      const answer = await api.ask(job, profileId, question, history)
      setTurns([...turns, answer])
      setText('')
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  if (!options.data) {
    return options.error ? (
      <ErrorAlert error={options.error} title="Couldn't open the questions" />
    ) : (
      <Loading label="Loading the questions" />
    )
  }
  const suggested = options.data.suggested
  const asked = new Set(turns.map((t) => t.question))
  const tooLong = text.trim().length > MAX_QUESTION_CHARS
  return (
    <div className="space-y-3" role="region" aria-label={`Questions about ${who}`}>
      <p className="text-xs text-muted-foreground">
        Answers come from {who}'s own material only, with the quotes they rest on. Check them against the quotes.
        Nothing is saved: the conversation is gone when you leave the page.
      </p>
      {turns.length > 0 && (
        <ol ref={list} className="max-h-[28rem] space-y-4 overflow-y-auto pr-1" aria-label="Answers">
          {turns.map((t, i) => (
            <li key={i} className="space-y-2">
              <p className="text-sm font-medium">
                <span className="sr-only">You asked: </span>
                {t.question}
              </p>
              <div className="space-y-2 rounded-lg bg-muted px-3 py-2 text-sm">
                {!t.answered && (
                  <Badge variant="outline" className="bg-background">
                    <CircleHelp aria-hidden /> The material doesn't answer this
                  </Badge>
                )}
                <p className="whitespace-pre-wrap">{t.answer}</p>
                {t.evidence.map((q) => (
                  <blockquote key={q.id} className="flex gap-2 border-l-2 border-primary/30 pl-3">
                    <Quote className="mt-0.5 size-3.5 shrink-0 text-primary/60" aria-hidden />
                    <span>
                      {q.quote} <span className="text-xs text-muted-foreground">({q.source})</span>
                    </span>
                  </blockquote>
                ))}
              </div>
            </li>
          ))}
        </ol>
      )}
      {suggested.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs text-muted-foreground">Demo questions, answered for free:</p>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Suggested questions">
            {suggested.map((q) => (
              <WhyDisabled key={q} reason={asked.has(q) && 'Already asked; the answer is above'}>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-auto whitespace-normal py-1.5 text-left"
                  disabled={busy || asked.has(q)}
                  onClick={() => void ask(q)}
                >
                  {q}
                </Button>
              </WhyDisabled>
            ))}
          </div>
        </div>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void ask(text)
        }}
        className="space-y-2"
      >
        <Label htmlFor={boxId} className="sr-only">
          Question about {who}
        </Label>
        <Textarea
          id={boxId}
          value={text}
          rows={2}
          placeholder={`Ask about ${who}'s experience…`}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void ask(text)
          }}
        />
        {tooLong && <p className="text-xs text-destructive">A question is at most {MAX_QUESTION_CHARS} characters.</p>}
        {error instanceof ApiError && error.paidCallRefused ? (
          <p role="alert" className="text-sm text-muted-foreground">
            Answering your own question needs a paid model call, and paid calls are off on this server.
            {suggested.length > 0 && ' Try one of the demo questions above.'}
          </p>
        ) : (
          <ErrorAlert error={error} title="Couldn't answer the question" />
        )}
        <div className="flex justify-end">
          <Button type="submit" size="sm" disabled={busy || !text.trim() || tooLong}>
            {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Sparkles aria-hidden />}
            Ask
          </Button>
        </div>
      </form>
    </div>
  )
}
