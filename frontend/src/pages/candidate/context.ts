import { useOutletContext } from 'react-router'

import type { CandidateSummary } from '@/lib/types'

export interface CandidateContext {
  name: string
  summary: CandidateSummary
  /** Load the summary again, after a step changed it. */
  refresh: () => Promise<void>
}

/** The candidate's view of where they are, for the step pages. */
export function useCandidate(): CandidateContext {
  return useOutletContext<CandidateContext>()
}

/** Whether the candidate has answered questions before. */
export function interviewed(summary: CandidateSummary): boolean {
  return summary.history.includes('interviewed')
}

export const TRANSPARENCY =
  'Your evidence is assessed to match you with jobs. You can ask for that assessment at any time.'
