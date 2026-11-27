import { Lock, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { Field } from '@/components/fields'
import { ErrorAlert, PageHeader, Working } from '@/components/states'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { api } from '@/lib/api'
import { useJob } from '@/pages/employer/context'

/** Step 1: the job ad, and drafting a rubric from it. */
export function JobAd() {
  const { name, summary, refresh } = useJob()
  const navigate = useNavigate()
  const [ad, setAd] = useState(summary.ad.ad)
  const [company, setCompany] = useState(summary.ad.company ?? '')
  const [title, setTitle] = useState(summary.ad.title ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const fixed = summary.demo

  async function extract() {
    setBusy(true)
    setError(null)
    try {
      if (!fixed) {
        await api.setAd(name, { ad, company: company.trim() || null, title: title.trim() || null })
      }
      const result = await api.extractRubric(name)
      const r = result.job.rubric
      toast.success(
        `Rubric drafted: ${r.criteria.length} criteria` +
          (result.dropped.length ? `, ${result.dropped.length} dropped for not quoting the ad.` : '.'),
      )
      await refresh()
      navigate('../rubric')
    } catch (e) {
      setError(e)
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader title="The job ad">
        Paste the ad as you would post it. We draft hard filters and weighted
        criteria from it, each quoting the ad; you edit and approve them next.
      </PageHeader>
      {fixed && (
        <Alert className="mb-6" role="note">
          <Lock aria-hidden />
          <AlertTitle>This is the Fjord Grocery demo</AlertTitle>
          <AlertDescription>
            Its ad is fixed, so the recorded rubric fits it. Drafting the rubric costs nothing.
          </AlertDescription>
        </Alert>
      )}
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Job title" hint="Read from the ad if empty.">
            {(id) => <Input id={id} value={title} disabled={fixed} onChange={(e) => setTitle(e.target.value)} />}
          </Field>
          <Field label="Company" hint="Read from the ad if empty.">
            {(id) => <Input id={id} value={company} disabled={fixed} onChange={(e) => setCompany(e.target.value)} />}
          </Field>
        </div>
        <Field label="Ad">
          {(id) => (
            <Textarea
              id={id}
              rows={18}
              value={ad}
              readOnly={fixed}
              placeholder="Paste the job ad here."
              className="font-mono text-sm leading-relaxed"
              onChange={(e) => setAd(e.target.value)}
            />
          )}
        </Field>
        <ErrorAlert error={error} title="Couldn't draft the rubric" />
        <div className="flex flex-wrap items-center gap-3">
          <Button size="lg" disabled={!ad.trim() || busy} onClick={extract}>
            <Sparkles aria-hidden />
            {summary.has_rubric ? 'Draft the rubric again' : 'Draft the rubric'}
          </Button>
          {busy && <Working>Reading the ad. This can take a minute.</Working>}
        </div>
        {summary.has_rubric && (
          <p className="text-sm text-muted-foreground">
            Drafting again replaces the rubric, unless candidates were matched against it.
          </p>
        )}
      </div>
    </>
  )
}
