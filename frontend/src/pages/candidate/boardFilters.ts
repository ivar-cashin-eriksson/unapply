import { FIT_FILTERS, minVacancies, seniorityLabel, workModeLabel } from '@/lib/format'
import type { BoardQuery, FitFilter, Seniority, WorkMode } from '@/lib/types'

/**
 * The job board's filters, kept in the address (`?seniority=junior&skill=python`), so
 * a pill on a listing can link to the board filtered by it and the back button works.
 * Free-text search and the sort stay on the page.
 *
 * Every filter is something a listing shows candidates; none is from the rubric, and
 * there is no filter by skill level.
 */
export type FilterKey = 'location' | 'work_mode' | 'seniority' | 'fit' | 'work_permit' | 'min_vacancies' | 'skill'

/** Filters in the order their chips show. `skill` may repeat; the others hold one value. */
export const FILTER_KEYS: FilterKey[] = ['fit', 'location', 'work_mode', 'seniority', 'work_permit', 'min_vacancies', 'skill']

/** One active filter. */
export interface ActiveFilter {
  key: FilterKey
  value: string
}

/** The filters in an address's search params, in chip order. */
export function activeFilters(params: URLSearchParams): ActiveFilter[] {
  return FILTER_KEYS.flatMap((key) => {
    const values = key === 'skill' ? params.getAll(key) : [params.get(key) ?? '']
    return values.filter(Boolean).map((value) => ({ key, value }))
  })
}

/** The params with a filter added: a skill joins the others, any other key is replaced. */
export function withFilter(params: URLSearchParams, key: FilterKey, value: string): URLSearchParams {
  const next = new URLSearchParams(params)
  if (key === 'skill') {
    if (!next.getAll(key).includes(value)) next.append(key, value)
  } else if (value) {
    next.set(key, value)
  } else {
    next.delete(key)
  }
  return next
}

/** The params without one filter. */
export function withoutFilter(params: URLSearchParams, key: FilterKey, value: string): URLSearchParams {
  return new URLSearchParams([...params].filter(([k, v]) => !(k === key && v === value)))
}

/** The board's API query for the filters in the address (without the search words). */
export function filterQuery(params: URLSearchParams): BoardQuery {
  const skills = params.getAll('skill').filter(Boolean)
  const vacancies = Number(params.get('min_vacancies'))
  return {
    location: params.get('location') || undefined,
    work_mode: (params.get('work_mode') as WorkMode | null) || undefined,
    seniority: (params.get('seniority') as Seniority | null) || undefined,
    work_permit: params.get('work_permit') || undefined,
    min_vacancies: Number.isInteger(vacancies) && vacancies > 0 ? vacancies : undefined,
    skill: skills.length ? skills : undefined,
  }
}

/** What a filter's chip says, such as "Seniority: Junior" or "At least 2 vacancies". */
export function filterLabel({ key, value }: ActiveFilter): string {
  switch (key) {
    case 'fit':
      return `Fit: ${FIT_FILTERS.find((f) => f.value === (value as FitFilter))?.label ?? value}`
    case 'location':
      return `Location: ${value}`
    case 'work_mode':
      return `Work mode: ${workModeLabel(value as WorkMode)}`
    case 'seniority':
      return `Seniority: ${seniorityLabel(value as Seniority)}`
    case 'work_permit':
      return `Work permit: ${value}`
    case 'min_vacancies':
      return minVacancies(Number(value))
    case 'skill':
      return `Skill: ${value}`
  }
}
