import { useOutletContext } from 'react-router'

import type { JobSummary, Rubric, RubricForm } from '@/lib/types'

export interface JobContext {
  name: string
  summary: JobSummary
  /** Load the summary again, after a step changed it. */
  refresh: () => Promise<void>
}

/** The job's summary, for the step pages. */
export function useJob(): JobContext {
  return useOutletContext<JobContext>()
}

/** The form for a rubric as stored: every criterion kept, weights 1 to 5. */
export function rubricForm(rubric: Rubric, summary: JobSummary): RubricForm {
  return {
    approve: rubric.approved_at !== null,
    company: summary.ad.company ?? '',
    title: summary.ad.title ?? '',
    hard_filters: rubric.hard_filters,
    criteria: rubric.criteria.map((c) => ({
      id: c.id,
      keep: true,
      kind: c.kind,
      description: c.description,
      skill: c.skill,
      min_level: c.min_level,
      weight: Math.min(5, Math.max(1, Math.round(c.weight))),
    })),
  }
}
