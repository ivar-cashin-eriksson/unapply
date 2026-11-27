// Labels and formats shared by the pages, matching the Streamlit app's wording.

import type { CriterionKind, DatePrecision, Seniority, SkillCategory, SkillLevel, WorkMode } from '@/lib/types'

/** The shared skill scale, 1 to 5 (`unapply.schemas.SkillLevel`). */
export const LEVELS: { value: SkillLevel; name: string; meaning: string }[] = [
  { value: 1, name: 'Aware', meaning: 'Knows what it is, has tried it' },
  { value: 2, name: 'Basic', meaning: 'Has used it on small tasks with guidance' },
  { value: 3, name: 'Working', meaning: 'Uses it on own work without help' },
  { value: 4, name: 'Advanced', meaning: 'Designs non-trivial systems with it, helps others' },
  { value: 5, name: 'Expert', meaning: 'Deep, recognised expertise' },
]

export function levelName(level: SkillLevel | null): string {
  return LEVELS.find((l) => l.value === level)?.name ?? 'No level'
}

export const CATEGORIES: { value: SkillCategory; label: string }[] = [
  { value: 'technology', label: 'Technology' },
  { value: 'method', label: 'Method' },
  { value: 'domain', label: 'Domain' },
  { value: 'soft_skill', label: 'Soft skill' },
  { value: 'language', label: 'Language' },
  { value: 'certification', label: 'Certification' },
]

export function categoryLabel(category: SkillCategory | null): string {
  return CATEGORIES.find((c) => c.value === category)?.label ?? 'Other'
}

export const WORK_MODES: { value: WorkMode; label: string }[] = [
  { value: 'onsite', label: 'On site' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'remote', label: 'Remote' },
]

export function workModeLabel(mode: WorkMode): string {
  return WORK_MODES.find((m) => m.value === mode)?.label ?? mode
}

/** Seniority on the job board, read from the job title by the API. */
export const SENIORITIES: { value: Seniority; label: string }[] = [
  { value: 'junior', label: 'Junior' },
  { value: 'mid', label: 'Mid-level' },
  { value: 'senior', label: 'Senior' },
  { value: 'lead', label: 'Lead' },
]

export function seniorityLabel(seniority: Seniority): string {
  return SENIORITIES.find((s) => s.value === seniority)?.label ?? seniority
}

/** "1 vacancy", "3 vacancies". */
export function vacancies(n: number): string {
  return n === 1 ? '1 vacancy' : `${n} vacancies`
}

/** An ISO date and time as "27 Nov 2026". */
export function day(iso: string): string {
  const [date] = iso.split('T')
  const [year, m, d] = date.split('-')
  return `${Number(d)} ${MONTHS[Number(m) - 1]} ${year}`
}

export const KINDS: { value: CriterionKind; label: string }[] = [
  { value: 'must_have', label: 'Must-have' },
  { value: 'nice_to_have', label: 'Nice-to-have' },
]

/** File size, such as "12 KB". */
export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/**
 * An ISO date ("2022-03-01") as "Mar 2022", or just the year when it is known only
 * to the year (it is then stored as 1 January, so a month would be made up).
 */
export function month(iso: string | null, precision: DatePrecision = 'month'): string {
  if (!iso) return ''
  const [year, m] = iso.split('-')
  const n = Number(m)
  return precision === 'year' || !n ? year : `${MONTHS[n - 1]} ${year}`
}

/** When something happened, such as "Mar 2022 – now"; empty if unknown. */
export function period(
  start: string | null,
  end: string | null,
  startPrecision: DatePrecision = 'month',
  endPrecision: DatePrecision = 'month',
): string {
  if (!start && !end) return ''
  return `${month(start, startPrecision) || '?'} – ${month(end, endPrecision) || 'now'}`
}

/** A comma-separated list as typed, as a clean list. */
export function splitList(text: string): string[] {
  return text
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

/**
 * A name as typed, made into one the API accepts as far as it can: lowercase,
 * spaces as "-", other characters dropped. Trailing "-" stays, to type on.
 */
export function typedName(text: string): string {
  return text
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9_-]/g, '')
    .slice(0, 64)
}

export const NAME_PATTERN = /^[a-z0-9][a-z0-9_-]{0,63}$/

/** The first paragraph of an ad that isn't a heading or the company line, for a preview. */
export function adSummary(text: string): string {
  for (const block of text.split(/\n\s*\n/)) {
    const line = block.trim()
    if (!line || line.startsWith('#') || /^[-*] /.test(line) || /^\*\*.*\*\*/.test(line)) continue
    return line.replace(/\*\*/g, '').replace(/\s+/g, ' ')
  }
  return ''
}
