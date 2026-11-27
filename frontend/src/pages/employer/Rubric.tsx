import { BadgeCheck, FileText, Plus, Quote, RotateCcw, Trash2 } from 'lucide-react'
import { useId, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Field, ListInput, WorkModes } from '@/components/fields'
import { LevelChips } from '@/components/LevelChips'
import { EmptyState, ErrorAlert, Loading, PageHeader } from '@/components/states'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { api } from '@/lib/api'
import { KINDS } from '@/lib/format'
import type { CriterionEdit, CriterionKind, Rubric as RubricData, RubricForm } from '@/lib/types'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'
import { rubricForm, useJob } from '@/pages/employer/context'

const ON = 'data-[state=on]:border-primary data-[state=on]:bg-primary data-[state=on]:text-primary-foreground'
const WEIGHTS = ['minor', 'small', 'medium', 'large', 'essential']

/** Step 2: edit the hard filters and criteria, and approve. Any change raises the version. */
export function Rubric() {
  const { name, summary } = useJob()
  const loaded = useResource(() => api.rubric(name), `${name}:${summary.history.length}`)

  if (!summary.has_rubric) {
    return (
      <EmptyState
        icon={FileText}
        title="No rubric yet"
        action={
          <Button asChild>
            <Link to="../ad">Go to the job ad</Link>
          </Button>
        }
      >
        Draft one from the job ad first.
      </EmptyState>
    )
  }
  if (!loaded.data) {
    return loaded.error ? <ErrorAlert error={loaded.error} /> : <Loading label="Loading the rubric" />
  }
  return <RubricEditor key={summary.history.length} rubric={loaded.data} />
}

function RubricEditor({ rubric }: { rubric: RubricData }) {
  const { name, summary, refresh } = useJob()
  const [form, setForm] = useState<RubricForm>(() => rubricForm(rubric, summary))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const quotes = new Map(rubric.criteria.map((c) => [c.id, c.source_quote]))
  const update = (patch: Partial<RubricForm>) => setForm({ ...form, ...patch })
  const filters = form.hard_filters
  const setFilters = (patch: Partial<RubricForm['hard_filters']>) =>
    update({ hard_filters: { ...filters, ...patch } })
  const setCriterion = (i: number, patch: Partial<CriterionEdit>) =>
    update({ criteria: form.criteria.map((c, j) => (j === i ? { ...c, ...patch } : c)) })

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const saved = await api.saveRubric(name, form)
      toast.success(
        saved.approved_at ? `Rubric version ${saved.version} approved.` : `Saved as version ${saved.version}.`,
      )
      await refresh()
    } catch (e) {
      setError(e)
    } finally {
      setSaving(false)
    }
  }

  const groups = KINDS.map((k) => ({ kind: k.value, label: k.label }))
  return (
    <>
      <PageHeader
        title="Rubric"
        actions={
          <div className="flex items-center gap-2">
            <Badge variant="outline">Version {rubric.version}</Badge>
            {rubric.approved_at ? <Badge>Approved</Badge> : <Badge variant="secondary">Draft</Badge>}
          </div>
        }
      >
        Hard filters exclude candidates; criteria score them, weighted from 1 (minor)
        to 5 (essential). Candidates never see this. Any change makes a new version.
      </PageHeader>

      <div className="space-y-8 pb-28">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Job title">
            {(id) => <Input id={id} value={form.title} onChange={(e) => update({ title: e.target.value })} />}
          </Field>
          <Field label="Company">
            {(id) => <Input id={id} value={form.company} onChange={(e) => update({ company: e.target.value })} />}
          </Field>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Hard filters</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-6 sm:grid-cols-2">
            <Field label="Locations" hint="Empty means anywhere. Separate with commas.">
              {(id) => <ListInput id={id} value={filters.locations} onChange={(locations) => setFilters({ locations })} />}
            </Field>
            <div className="space-y-1.5">
              <span className="text-sm font-medium">Work modes</span>
              <WorkModes value={filters.work_modes} label="Work modes offered" onChange={(work_modes) => setFilters({ work_modes })} />
              <p className="text-xs text-muted-foreground">None chosen means any.</p>
            </div>
            <Field label="Work permits" hint='Country codes, or "EU", the candidate must have.'>
              {(id) => (
                <ListInput
                  id={id}
                  value={filters.required_work_permits}
                  onChange={(required_work_permits) => setFilters({ required_work_permits })}
                />
              )}
            </Field>
            <Field label="Minimum years of experience" hint="Empty for no minimum.">
              {(id) => (
                <Input
                  id={id}
                  inputMode="numeric"
                  className="w-28"
                  value={filters.min_years_experience ?? ''}
                  onChange={(e) => {
                    const digits = e.target.value.replace(/\D/g, '').slice(0, 2)
                    setFilters({ min_years_experience: digits ? Number(digits) : null })
                  }}
                />
              )}
            </Field>
          </CardContent>
        </Card>

        {groups.map((g) => (
          <section key={g.kind} aria-labelledby={`${g.kind}-title`} className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 id={`${g.kind}-title`} className="text-lg font-semibold">
                {g.label}s
              </h2>
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  update({
                    criteria: [
                      ...form.criteria,
                      { id: null, keep: true, kind: g.kind, description: '', skill: null, min_level: null, weight: 3 },
                    ],
                  })
                }
              >
                <Plus aria-hidden /> Add a {g.label.toLowerCase()}
              </Button>
            </div>
            <ul className="space-y-3">
              {form.criteria.map((c, i) =>
                c.kind !== g.kind ? null : (
                  <li key={c.id ?? `new-${i}`}>
                    <CriterionCard
                      criterion={c}
                      quote={c.id ? (quotes.get(c.id) ?? null) : null}
                      onChange={(patch) => setCriterion(i, patch)}
                      onRemove={() =>
                        c.id
                          ? setCriterion(i, { keep: !c.keep })
                          : update({ criteria: form.criteria.filter((_, j) => j !== i) })
                      }
                    />
                  </li>
                ),
              )}
            </ul>
          </section>
        ))}
        <ErrorAlert error={error} title="Couldn't save the rubric" />
      </div>

      <div className="fixed inset-x-0 bottom-0 z-30 border-t bg-background/95 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-center gap-3">
            <Checkbox id="approve" checked={form.approve} onCheckedChange={(v) => update({ approve: v === true })} />
            <Label htmlFor="approve" className="leading-snug">
              <span>
                I approve this rubric
                <span className="block text-xs font-normal text-muted-foreground">
                  {form.criteria.filter((c) => c.keep).length} criteria · candidates are matched only against an approved rubric
                </span>
              </span>
            </Label>
          </div>
          <Button size="lg" onClick={save} disabled={saving}>
            <BadgeCheck aria-hidden />
            {saving ? 'Saving…' : form.approve ? 'Save and approve' : 'Save'}
          </Button>
        </div>
      </div>
    </>
  )
}

function CriterionCard({
  criterion: c,
  quote,
  onChange,
  onRemove,
}: {
  criterion: CriterionEdit
  quote: string | null
  onChange: (patch: Partial<CriterionEdit>) => void
  onRemove: () => void
}) {
  const what = c.description || 'the new criterion'
  const descId = useId()
  return (
    <Card className={cn('py-0', !c.keep && 'opacity-55')}>
      <CardContent className="space-y-4 p-5">
        <div className="flex items-start gap-3">
          <div className="flex-1 space-y-1.5">
            <Label htmlFor={descId} className="sr-only">
              Description
            </Label>
            <Input
              id={descId}
              value={c.description}
              disabled={!c.keep}
              placeholder="What is asked for"
              className={cn('font-medium', !c.keep && 'line-through')}
              onChange={(e) => onChange({ description: e.target.value })}
            />
            {quote && (
              <p className="flex gap-1.5 text-sm text-muted-foreground">
                <Quote className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                <span>“{quote}”</span>
              </p>
            )}
            {!quote && c.keep && <p className="text-xs text-muted-foreground">Added by you: no quote from the ad.</p>}
          </div>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={c.keep ? `Remove ${what}` : `Keep ${what}`}
            title={c.keep ? 'Remove' : 'Keep after all'}
            onClick={onRemove}
          >
            {c.keep ? <Trash2 aria-hidden /> : <RotateCcw aria-hidden />}
          </Button>
        </div>
        <fieldset disabled={!c.keep} className="grid gap-4 md:grid-cols-[10rem_1fr_1fr]">
          <Field label="Skill" hint="Optional.">
            {(id) => (
              <Input
                id={id}
                value={c.skill ?? ''}
                placeholder="No skill"
                onChange={(e) => onChange({ skill: e.target.value || null })}
              />
            )}
          </Field>
          <div className="space-y-1.5">
            <span className="text-sm font-medium">Lowest level</span>
            <LevelChips
              compact
              value={c.min_level}
              label={`Lowest level for ${what}`}
              disabled={!c.keep}
              onChange={(min_level) => onChange({ min_level })}
            />
          </div>
          <div className="space-y-1.5">
            <span className="text-sm font-medium">Weight</span>
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              spacing={1}
              aria-label={`Weight of ${what}`}
              value={String(c.weight)}
              disabled={!c.keep}
              onValueChange={(v) => v && onChange({ weight: Number(v) })}
            >
              {WEIGHTS.map((label, i) => (
                <ToggleGroupItem
                  key={label}
                  value={String(i + 1)}
                  aria-label={`${i + 1} ${label}`}
                  title={`${i + 1} · ${label}`}
                  className={`rounded-full ${ON}`}
                >
                  {i + 1}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
            <p className="text-xs text-muted-foreground">{WEIGHTS[c.weight - 1]}</p>
          </div>
        </fieldset>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Kind:</span>
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            spacing={1}
            aria-label={`Kind of ${what}`}
            value={c.kind}
            disabled={!c.keep}
            onValueChange={(v) => v && onChange({ kind: v as CriterionKind })}
          >
            {KINDS.map((k) => (
              <ToggleGroupItem key={k.value} value={k.value} className={`rounded-full px-3 ${ON}`}>
                {k.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
      </CardContent>
    </Card>
  )
}
