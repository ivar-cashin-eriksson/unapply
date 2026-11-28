import { BadgeCheck, FileUp, Plus, Search, Trash2, Wand2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { CategoryDot } from '@/components/CategoryColour'
import { Field, LinesInput, ListInput, Quotes, WorkModes } from '@/components/fields'
import { LevelChips } from '@/components/LevelChips'
import { EmptyState, ErrorAlert, Loading, PageHeader } from '@/components/states'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { categoryBorder } from '@/lib/categoryColour'
import { api, describeError } from '@/lib/api'
import { CATEGORIES, LEVELS } from '@/lib/format'
import type { ExperienceEdit, NewSkill, ReviewForm, SkillCategory, SkillEdit } from '@/lib/types'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'
import { useCandidate } from '@/pages/candidate/context'

/** Step 2: check the draft, rate your own skills, correct and approve. */
export function Review() {
  const { name, summary } = useCandidate()
  const loaded = useResource(() => api.review(name), `${name}:${summary.history.length}`)

  if (!summary.has_profile) {
    return (
      <EmptyState
        icon={FileUp}
        title="No profile to review yet"
        action={
          <Button asChild>
            <Link to="../material">Go to your material</Link>
          </Button>
        }
      >
        Build a profile from your material first.
      </EmptyState>
    )
  }
  if (!loaded.data) {
    return loaded.error ? <ErrorAlert error={loaded.error} /> : <Loading label="Loading your profile" />
  }
  // A save changes the history, which loads the saved review into a new editor.
  return <ReviewEditor key={summary.history.length} initial={loaded.data} />
}

function ReviewEditor({ initial }: { initial: ReviewForm }) {
  const { name, summary, refresh } = useCandidate()
  const [form, setForm] = useState<ReviewForm>(initial)
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  const navigate = useNavigate()

  const update = (patch: Partial<ReviewForm>) => setForm({ ...form, ...patch })
  const kept = form.skills.filter((s) => s.keep)
  const rated = kept.filter((s) => s.level !== null).length

  async function fillDemo() {
    try {
      setForm(await api.demoReview(name))
      toast.info("John's review is filled in. Look it over, then save.")
    } catch (e) {
      toast.error(describeError(e))
    }
  }

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const saved = await api.saveReview(name, form)
      const approved = saved.approved_by_candidate_at !== null
      toast.success(approved ? 'Profile approved.' : "Saved. Approve your profile when it's right.")
      await refresh()
      if (approved) navigate('../questions')
    } catch (e) {
      setError(e)
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Review your profile"
        actions={
          summary.demo && (
            <Button variant="outline" onClick={fillDemo}>
              <Wand2 aria-hidden /> Fill in John's review
            </Button>
          )
        }
      >
        Rate the skills you want employers to see, untick anything that's wrong, and
        add what's missing. Employers only see approved profiles.
      </PageHeader>

      <div className="space-y-6 pb-28">
        <Field label="Headline" hint="One line about you, as employers will read it.">
          {(id) => (
            <Input id={id} value={form.headline} onChange={(e) => update({ headline: e.target.value })} />
          )}
        </Field>

        <Tabs defaultValue="skills">
          <TabsList className="flex-wrap">
            <TabsTrigger value="skills">Skills ({kept.length + form.add_skills.length})</TabsTrigger>
            <TabsTrigger value="experience">
              Experience ({form.experiences.filter((x) => x.keep).length})
            </TabsTrigger>
            <TabsTrigger value="preferences">Preferences</TabsTrigger>
          </TabsList>
          <TabsContent value="skills" className="space-y-8 pt-4">
            {/* Adding comes first: the list of skills found can be long. */}
            <AddSkills skills={form.add_skills} onChange={(add_skills) => update({ add_skills })} />
            <Skills skills={form.skills} onChange={(skills) => update({ skills })} />
          </TabsContent>
          <TabsContent value="experience" className="pt-4">
            <Experiences
              experiences={form.experiences}
              onChange={(experiences) => update({ experiences })}
            />
          </TabsContent>
          <TabsContent value="preferences" className="pt-4">
            <PreferencesForm form={form} onChange={(preferences) => update({ preferences })} />
          </TabsContent>
        </Tabs>
        <ErrorAlert error={error} title="Couldn't save your review" />
      </div>

      <div className="fixed inset-x-0 bottom-0 z-30 border-t bg-background/95 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-center gap-3">
            <Checkbox
              id="approve"
              checked={form.approve}
              onCheckedChange={(v) => update({ approve: v === true })}
            />
            <Label htmlFor="approve" className="leading-snug">
              <span>
                I approve this profile
                <span className="block text-xs font-normal text-muted-foreground">
                  {rated} of {kept.length} skills rated · employers only see approved profiles
                </span>
              </span>
            </Label>
          </div>
          <Button onClick={save} disabled={saving} size="lg">
            <BadgeCheck aria-hidden />
            {saving ? 'Saving…' : form.approve ? 'Save and approve' : 'Save'}
          </Button>
        </div>
      </div>
    </>
  )
}

function Skills({ skills, onChange }: { skills: SkillEdit[]; onChange: (s: SkillEdit[]) => void }) {
  const [filter, setFilter] = useState('')
  const shown = useMemo(
    () => skills.map((s, i) => [s, i] as const).filter(([s]) => s.name.includes(filter.trim().toLowerCase())),
    [skills, filter],
  )
  const set = (i: number, patch: Partial<SkillEdit>) =>
    onChange(skills.map((s, j) => (j === i ? { ...s, ...patch } : s)))

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">
          Your level:{' '}
          {LEVELS.map((l) => `${l.value} ${l.name.toLowerCase()}`).join(', ')}. Leave it
          empty for skills you don't want to rate.
        </p>
        <div className="relative sm:w-64">
          <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            aria-label="Filter skills"
            placeholder="Filter skills"
            className="pl-8"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
      </div>
      {shown.length === 0 && (
        <p className="py-6 text-center text-sm text-muted-foreground">No skill matches “{filter}”.</p>
      )}
      <ul className="space-y-2">
        {shown.map(([s, i]) => (
          <li key={s.name}>
            <Card className={cn('py-0 transition-opacity', categoryBorder(s.category), !s.keep && 'opacity-55')}>
              <CardContent className="flex flex-col gap-3 p-4 md:flex-row md:items-start">
                <div className="flex min-w-0 flex-1 items-start gap-3">
                  <Checkbox
                    className="mt-0.5"
                    checked={s.keep}
                    aria-label={`Keep ${s.name}`}
                    onCheckedChange={(v) => set(i, { keep: v === true })}
                  />
                  <div className="min-w-0 space-y-1.5">
                    <p className={cn('font-medium', !s.keep && 'line-through')}>{s.name}</p>
                    <Quotes lines={s.evidence} label="From your material" />
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-3 md:justify-end">
                  <CategorySelect
                    value={s.category}
                    label={`Category of ${s.name}`}
                    disabled={!s.keep}
                    onChange={(category) => set(i, { category })}
                  />
                  <LevelChips
                    value={s.level}
                    label={`Your level in ${s.name}`}
                    disabled={!s.keep}
                    onChange={(level) => set(i, { level })}
                  />
                </div>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  )
}

function CategorySelect({
  value,
  onChange,
  label,
  disabled,
}: {
  value: SkillCategory | null
  onChange: (c: SkillCategory) => void
  label: string
  disabled?: boolean
}) {
  return (
    <Select value={value ?? undefined} onValueChange={(v) => onChange(v as SkillCategory)} disabled={disabled}>
      <SelectTrigger size="sm" aria-label={label} className="w-36">
        <SelectValue placeholder="Category" />
      </SelectTrigger>
      <SelectContent>
        {CATEGORIES.map((c) => (
          <SelectItem key={c.value} value={c.value}>
            <CategoryDot category={c.value} />
            {c.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function Experiences({
  experiences,
  onChange,
}: {
  experiences: ExperienceEdit[]
  onChange: (x: ExperienceEdit[]) => void
}) {
  const set = (i: number, patch: Partial<ExperienceEdit>) =>
    onChange(experiences.map((x, j) => (j === i ? { ...x, ...patch } : x)))
  if (!experiences.length) {
    return <p className="text-sm text-muted-foreground">No experience was found in your material.</p>
  }
  return (
    <ul className="space-y-3">
      {experiences.map((x, i) => (
        <li key={x.id}>
          <Card className={cn('py-0', !x.keep && 'opacity-55')}>
            <CardContent className="space-y-4 p-5">
              <div className="flex items-center gap-3">
                <Checkbox
                  checked={x.keep}
                  aria-label={`Keep ${x.title} at ${x.organisation}`}
                  onCheckedChange={(v) => set(i, { keep: v === true })}
                />
                <p className={cn('font-medium', !x.keep && 'line-through')}>
                  {x.title || 'Untitled'} · {x.organisation}
                </p>
              </div>
              <fieldset disabled={!x.keep} className="grid gap-4 sm:grid-cols-2">
                <Field label="Title">
                  {(id) => <Input id={id} value={x.title} onChange={(e) => set(i, { title: e.target.value })} />}
                </Field>
                <Field label="Organisation">
                  {(id) => (
                    <Input id={id} value={x.organisation} onChange={(e) => set(i, { organisation: e.target.value })} />
                  )}
                </Field>
                <Field label="Start" hint="YYYY or YYYY-MM">
                  {(id) => (
                    <Input
                      id={id}
                      value={x.start ?? ''}
                      placeholder="2019-08"
                      onChange={(e) => set(i, { start: e.target.value.trim() || null })}
                    />
                  )}
                </Field>
                <Field label="End" hint="YYYY or YYYY-MM; empty means now">
                  {(id) => (
                    <Input
                      id={id}
                      value={x.end ?? ''}
                      placeholder="now"
                      onChange={(e) => set(i, { end: e.target.value.trim() || null })}
                    />
                  )}
                </Field>
                <div className="sm:col-span-2">
                  <Field label="Summary">
                    {(id) => (
                      <Textarea id={id} rows={3} value={x.summary} onChange={(e) => set(i, { summary: e.target.value })} />
                    )}
                  </Field>
                </div>
              </fieldset>
              <Quotes lines={x.evidence} label="From your material" />
            </CardContent>
          </Card>
        </li>
      ))}
    </ul>
  )
}

const NEW_SKILL: NewSkill = { name: '', category: 'technology', level: null, note: '' }

function AddSkills({ skills, onChange }: { skills: NewSkill[]; onChange: (s: NewSkill[]) => void }) {
  const set = (i: number, patch: Partial<NewSkill>) =>
    onChange(skills.map((s, j) => (j === i ? { ...s, ...patch } : s)))
  return (
    <section aria-labelledby="add-skills-title" className="space-y-4">
      <div className="space-y-1">
        <h2 id="add-skills-title" className="font-medium">
          Missing a skill?
        </h2>
        <p className="text-sm text-muted-foreground">
          Add it with your level and say where you used it. Skills you add are kept as
          your own statements.
        </p>
      </div>
      <ul className="space-y-3">
        {skills.map((s, i) => (
          <li key={i}>
            <Card className={cn('py-0', categoryBorder(s.category))}>
              <CardContent className="grid gap-4 p-5 sm:grid-cols-[1fr_auto]">
                <Field label="Skill">
                  {(id) => <Input id={id} value={s.name} placeholder="matlab" onChange={(e) => set(i, { name: e.target.value })} />}
                </Field>
                <div className="space-y-1.5">
                  <span className="text-sm font-medium">Category</span>
                  <CategorySelect value={s.category} label="Category of the new skill" onChange={(category) => set(i, { category })} />
                </div>
                <div className="space-y-1.5 sm:col-span-2">
                  <span className="text-sm font-medium">Your level</span>
                  <LevelChips value={s.level} label={`Your level in ${s.name || 'the new skill'}`} onChange={(level) => set(i, { level })} />
                </div>
                <div className="sm:col-span-2">
                  <Field label="Where you used it" hint="Required: a role, project or course, and when.">
                    {(id) => <Textarea id={id} rows={2} value={s.note} onChange={(e) => set(i, { note: e.target.value })} />}
                  </Field>
                </div>
                <div className="sm:col-span-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Remove ${s.name || 'the new skill'}`}
                    onClick={() => onChange(skills.filter((_, j) => j !== i))}
                  >
                    <Trash2 aria-hidden /> Remove
                  </Button>
                </div>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
      <Button variant="outline" onClick={() => onChange([...skills, { ...NEW_SKILL }])}>
        <Plus aria-hidden /> Add a skill
      </Button>
    </section>
  )
}

function PreferencesForm({
  form,
  onChange,
}: {
  form: ReviewForm
  onChange: (p: ReviewForm['preferences']) => void
}) {
  const p = form.preferences
  const set = (patch: Partial<ReviewForm['preferences']>) => onChange({ ...p, ...patch })
  return (
    <Card className="py-0">
      <CardContent className="grid gap-6 p-5 sm:grid-cols-2">
        <Field label="Locations" hint="Cities or regions, separated by commas.">
          {(id) => <ListInput id={id} value={p.locations} placeholder="Copenhagen, Aarhus" onChange={(locations) => set({ locations })} />}
        </Field>
        <div className="space-y-1.5">
          <span className="text-sm font-medium">Work modes</span>
          <WorkModes value={p.work_modes} label="Work modes you accept" onChange={(work_modes) => set({ work_modes })} />
          <p className="text-xs text-muted-foreground">None chosen means any.</p>
        </div>
        <Field label="Lowest yearly salary" hint="Gross, before tax.">
          {(id) => (
            <div className="flex gap-2">
              <Input
                id={id}
                inputMode="numeric"
                value={p.salary_min ?? ''}
                placeholder="600000"
                onChange={(e) => {
                  const digits = e.target.value.replace(/\D/g, '')
                  set({ salary_min: digits ? Number(digits) : null })
                }}
              />
              <Input
                aria-label="Currency"
                className="w-24"
                value={p.salary_currency ?? ''}
                placeholder="DKK"
                maxLength={3}
                onChange={(e) => set({ salary_currency: e.target.value.toUpperCase() || null })}
              />
            </div>
          )}
        </Field>
        <Field label="Work permits" hint='Country codes, or "EU", separated by commas.'>
          {(id) => <ListInput id={id} value={p.work_permits} placeholder="EU" onChange={(work_permits) => set({ work_permits })} />}
        </Field>
        <div className="sm:col-span-2">
          <Field label="Dealbreakers" hint="One per line, in your own words.">
            {(id) => <LinesInput id={id} value={p.dealbreakers} onChange={(dealbreakers) => set({ dealbreakers })} />}
          </Field>
        </div>
      </CardContent>
    </Card>
  )
}
