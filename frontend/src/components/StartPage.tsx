import { ArrowRight, Plus, type LucideIcon } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router'

import { EmptyState, ErrorAlert, Loading, PageHeader } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NAME_PATTERN, typedName } from '@/lib/format'
import { useResource } from '@/lib/useResource'

interface Props {
  title: string
  intro: ReactNode
  /** Loads the names to list. */
  list: () => Promise<string[]>
  /** Creates one by name; returns its name. */
  create: (name: string) => Promise<{ name: string }>
  /** Where each one opens. */
  to: (name: string) => string
  icon: LucideIcon
  /** "candidate" or "job", in labels. */
  noun: string
  placeholder: string
  empty: string
  demo: ReactNode
}

/** A side's start page: what exists, a form to create one, and the demo. */
export function StartPage(props: Props) {
  const { title, intro, list, create, to, icon: Icon, noun, placeholder, empty, demo } = props
  const names = useResource(list, title)
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const valid = NAME_PATTERN.test(name)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!valid) return
    setBusy(true)
    setError(null)
    try {
      const created = await create(name)
      navigate(to(created.name))
    } catch (err) {
      setError(err)
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader title={title} actions={demo}>
        {intro}
      </PageHeader>
      <div className="grid gap-8 md:grid-cols-[1fr_20rem]">
        <section aria-labelledby="existing" className="space-y-3">
          <h2 id="existing" className="text-sm font-medium text-muted-foreground">
            Open a {noun}
          </h2>
          {names.loading && !names.data ? (
            <Loading />
          ) : names.error ? (
            <ErrorAlert error={names.error} title={`Couldn't load the ${noun}s`} />
          ) : names.data?.length ? (
            <ul className="grid gap-2 sm:grid-cols-2">
              {names.data.map((n) => (
                <li key={n}>
                  <Link
                    to={to(n)}
                    className="group flex items-center gap-3 rounded-xl border bg-card px-4 py-3 outline-none transition-colors hover:border-primary/40 hover:bg-accent/40 focus-visible:ring-3 focus-visible:ring-ring/50"
                  >
                    <span className="flex size-8 items-center justify-center rounded-lg bg-accent text-primary">
                      <Icon className="size-4" aria-hidden />
                    </span>
                    <span className="flex-1 truncate font-medium">{n}</span>
                    <ArrowRight
                      className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5"
                      aria-hidden
                    />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon={Icon} title={`No ${noun}s yet`}>
              {empty}
            </EmptyState>
          )}
        </section>

        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="text-base">New {noun}</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="new-name">Name</Label>
                <Input
                  id="new-name"
                  value={name}
                  placeholder={placeholder}
                  autoComplete="off"
                  aria-invalid={name !== '' && !valid}
                  onChange={(e) => setName(typedName(e.target.value))}
                />
                <p className="text-xs text-muted-foreground">
                  Lowercase letters, digits, “-” and “_”.
                </p>
              </div>
              <ErrorAlert error={error} title={`Couldn't create the ${noun}`} />
              <Button type="submit" disabled={!valid || busy} className="w-full">
                <Plus aria-hidden /> Create
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </>
  )
}
