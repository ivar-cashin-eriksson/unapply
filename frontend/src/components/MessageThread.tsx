import { Loader2, MessagesSquare, Send } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'

import { ErrorAlert, Loading } from '@/components/states'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { MAX_MESSAGE_CHARS, type Message, type Sender, type Thread } from '@/lib/types'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

interface Props {
  /** Says what the thread is, such as "Messages with Fjord Grocery". */
  label: string
  /** Who is reading: their messages go on the right. */
  me: Sender
  /** What to call the other side, such as "Fjord Grocery" or "John Doe". */
  other: string
  /** Changes when the thread does. */
  threadKey: string
  load: () => Promise<Thread>
  markRead: () => Promise<Thread>
  send: (text: string) => Promise<Message>
  /** Called once the other side's messages are marked read, to update unread counts. */
  onRead?: () => void
}

/**
 * A thread between an employer and a candidate they revealed, oldest first and
 * newest at the bottom, with a box to write in. Opening it marks the other
 * side's messages read; those that were unread are marked "New" until it is
 * opened again.
 */
export function MessageThread({ label, me, other, threadKey, load, markRead, send, onRead }: Props) {
  const thread = useResource(load, threadKey)
  const [fresh, setFresh] = useState<Set<number>>(new Set())
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const list = useRef<HTMLOListElement>(null)
  const boxId = useId()

  // Mark what the other side wrote as read once it is shown, remembering which were new.
  useEffect(() => {
    if (!thread.data || thread.data.unread === 0) return
    const unread = thread.data.messages.filter((m) => m.sender !== me && m.read_at === null)
    markRead().then(
      (read) => {
        setFresh(new Set(unread.map((m) => m.id)))
        thread.set(read)
        onRead?.()
      },
      () => undefined, // Still unread; it is marked next time.
    )
    // Runs again on every new thread; once marked read, nothing is left to mark.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [thread.data])

  const count = thread.data?.messages.length ?? 0
  useEffect(() => {
    const el = list.current
    if (el) el.scrollTop = el.scrollHeight
  }, [count])

  async function submit(e?: React.FormEvent) {
    e?.preventDefault()
    if (!text.trim() || busy) return
    setBusy(true)
    setError(null)
    try {
      const sent = await send(text)
      const messages = thread.data?.messages ?? []
      thread.set({ messages: [...messages, sent], unread: 0 })
      setText('')
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  if (!thread.data) {
    return thread.error ? (
      <ErrorAlert error={thread.error} title="Couldn't load the messages" />
    ) : (
      <Loading label="Loading the messages" />
    )
  }
  const messages = thread.data.messages
  const tooLong = text.trim().length > MAX_MESSAGE_CHARS
  return (
    <div className="space-y-3" role="region" aria-label={label}>
      {messages.length ? (
        <ol ref={list} className="max-h-80 space-y-2 overflow-y-auto pr-1" aria-label="Messages">
          {messages.map((m) => {
            const mine = m.sender === me
            return (
              <li key={m.id} className={cn('flex', mine ? 'justify-end' : 'justify-start')}>
                <div
                  className={cn(
                    'max-w-[85%] rounded-2xl px-3 py-2 text-sm',
                    mine ? 'bg-primary text-primary-foreground' : 'bg-muted',
                  )}
                >
                  <p className="sr-only">{mine ? 'You' : other} wrote:</p>
                  <p className="whitespace-pre-wrap break-words">{m.text}</p>
                  <p className={cn('mt-1 text-xs', mine ? 'text-primary-foreground/75' : 'text-muted-foreground')}>
                    {mine ? 'You' : other} · {sentAt(m.sent_at)}
                    {fresh.has(m.id) && <span className="ml-1.5 font-medium text-primary">New</span>}
                  </p>
                </div>
              </li>
            )
          })}
        </ol>
      ) : (
        <p className="flex items-center gap-2 rounded-lg border border-dashed px-3 py-4 text-sm text-muted-foreground">
          <MessagesSquare className="size-4 shrink-0" aria-hidden />
          No messages yet. Write the first to {other}.
        </p>
      )}
      <form onSubmit={submit} className="space-y-2">
        <Label htmlFor={boxId} className="sr-only">
          Message to {other}
        </Label>
        <Textarea
          id={boxId}
          value={text}
          rows={3}
          placeholder={`Write to ${other}…`}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void submit()
          }}
        />
        {tooLong && (
          <p className="text-xs text-destructive">A message is at most {MAX_MESSAGE_CHARS} characters.</p>
        )}
        <ErrorAlert error={error} title="Couldn't send the message" />
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">No email is sent: {other} sees it here.</p>
          <Button type="submit" size="sm" disabled={busy || !text.trim() || tooLong}>
            {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Send aria-hidden />}
            Send
          </Button>
        </div>
      </form>
    </div>
  )
}

/** When a message was sent: the time today, else the day and time. */
function sentAt(iso: string): string {
  const d = new Date(iso)
  const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  if (d.toDateString() === new Date().toDateString()) return time
  return `${d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}, ${time}`
}

/** How many messages someone hasn't read; nothing when there are none. */
export function UnreadBadge({ count }: { count: number }) {
  if (count === 0) return null
  return (
    <Badge variant="secondary" className="border-primary/40 text-primary">
      <MessagesSquare aria-hidden /> {count} new message{count === 1 ? '' : 's'}
    </Badge>
  )
}
