import { Lock, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'

import { Field } from '@/components/fields'
import { ErrorAlert, PageHeader, Working } from '@/components/states'
import { WhyDisabled } from '@/components/WhyDisabled'
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
  const [openings, setOpenings] = useState(String(summary.ad.vacancies))
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const fixed = summary.demo
  const count = Number(openings)
  const validCount = Number.isInteger(count) && count >= 1 && count <= 1000
  const countChanged = validCount && count !== summary.ad.vacancies

  async function extract() {
    setBusy(true)
    setError(null)
    try {
      if (!fixed) {
        await api.setAd(name, {
          ad,
          company: company.trim() || null,
          title: title.trim() || null,
          vacancies: count,
        })
      } else if (countChanged) {
        await api.setAd(name, { ...summary.ad, vacancies: count })
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

  /** Save only the vacancies: they show on the job board at once. */
  async function saveVacancies() {
    setSaving(true)
    setError(null)
    try {
      const base = fixed ? summary.ad : { ad, company: company.trim() || null, title: title.trim() || null }
      await api.setAd(name, { ...base, vacancies: count })
      toast.success(`Saved: ${count === 1 ? '1 vacancy' : `${count} vacancies`}.`)
      await refresh()
    } catch (e) {
      setError(e)
    } finally {
      setSaving(false)
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
        <Field label="Vacancies" hint="How many people you hire for this job. Candidates see it on the job board.">
          {(id) => (
            <div className="flex items-center gap-2">
              <Input
                id={id}
                type="number"
                min={1}
                max={1000}
                step={1}
                value={openings}
                aria-invalid={!validCount}
                className="w-24"
                onChange={(e) => setOpenings(e.target.value)}
              />
              {summary.has_rubric && countChanged && (
                <Button variant="outline" size="sm" disabled={saving} onClick={saveVacancies}>
                  Save vacancies
                </Button>
              )}
            </div>
          )}
        </Field>
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
          <WhyDisabled
            reason={
              (!ad.trim() && 'Paste the job ad first') ||
              (!validCount && 'Enter a number of vacancies from 1 to 1000')
            }
          >
            <Button size="lg" disabled={!ad.trim() || !validCount || busy} onClick={extract}>
              <Sparkles aria-hidden />
              {summary.has_rubric ? 'Draft the rubric again' : 'Draft the rubric'}
            </Button>
          </WhyDisabled>
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
