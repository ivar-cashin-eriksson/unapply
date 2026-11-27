import { Contact as ContactIcon, Loader2, Save } from 'lucide-react'
import { useId, useState } from 'react'
import { toast } from 'sonner'

import { ErrorAlert, Loading } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api } from '@/lib/api'
import type { Contact } from '@/lib/types'
import { useResource } from '@/lib/useResource'

/** The name and contact details an employer sees only once they reveal you. */
export function ContactCard({ candidate, demo }: { candidate: string; demo: boolean }) {
  const loaded = useResource(() => api.contact(candidate), candidate)
  return (
    <Card className="h-fit" role="region" aria-label="Shown when revealed">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ContactIcon className="size-4 text-primary" aria-hidden /> Shown when revealed
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground">
          Employers see your profile without these until they reveal you on a job you connected to.
        </p>
        {loaded.data ? (
          demo ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
              <dt className="text-muted-foreground">Name</dt>
              <dd>{loaded.data.name}</dd>
              <dt className="text-muted-foreground">Email</dt>
              <dd>{loaded.data.email ?? 'Not given'}</dd>
              <dt className="text-muted-foreground">Phone</dt>
              <dd>{loaded.data.phone ?? 'Not given'}</dd>
            </dl>
          ) : (
            <ContactForm candidate={candidate} initial={loaded.data} onSaved={loaded.set} />
          )
        ) : loaded.error ? (
          <ErrorAlert error={loaded.error} title="Couldn't load your contact details" />
        ) : (
          <Loading label="Loading your contact details" />
        )}
        {demo && <p className="text-xs text-muted-foreground">In the demo, these come from the CV.</p>}
      </CardContent>
    </Card>
  )
}

function ContactForm({
  candidate,
  initial,
  onSaved,
}: {
  candidate: string
  initial: Contact
  onSaved: (contact: Contact) => void
}) {
  const [form, setForm] = useState({ name: initial.name, email: initial.email ?? '', phone: initial.phone ?? '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const id = useId()

  async function save(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const saved = await api.saveContact(candidate, {
        name: form.name,
        email: form.email || null,
        phone: form.phone || null,
      })
      onSaved(saved)
      toast.success('Your contact details are saved.')
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  const fields = [
    { key: 'name', label: 'Full name', type: 'text', autoComplete: 'name' },
    { key: 'email', label: 'Email', type: 'email', autoComplete: 'email' },
    { key: 'phone', label: 'Phone', type: 'tel', autoComplete: 'tel' },
  ] as const
  return (
    <form onSubmit={save} className="space-y-3">
      {fields.map((f) => (
        <div key={f.key} className="space-y-1.5">
          <Label htmlFor={`${id}-${f.key}`}>{f.label}</Label>
          <Input
            id={`${id}-${f.key}`}
            type={f.type}
            autoComplete={f.autoComplete}
            value={form[f.key]}
            required={f.key === 'name'}
            onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
          />
        </div>
      ))}
      <ErrorAlert error={error} title="Couldn't save your contact details" />
      <Button type="submit" size="sm" disabled={busy || !form.name.trim()}>
        {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Save aria-hidden />}
        Save
      </Button>
    </form>
  )
}
