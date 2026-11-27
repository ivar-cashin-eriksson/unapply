// Small synthetic API answers for the component tests, shaped like John Doe's demo
// and the Fjord Grocery job. No real person's data.
import type {
  CandidateProfile,
  CandidateSummary,
  JobSummary,
  Questions,
  ReviewForm,
  Rubric,
} from '@/lib/types'

export function candidate(patch: Partial<CandidateSummary> = {}): CandidateSummary {
  return {
    name: 'john-doe',
    demo: true,
    github: 'johndoe-example',
    material: [{ name: 'cv.md', size: 2048 }],
    has_profile: false,
    approved: false,
    questions_waiting: 0,
    history: [],
    ...patch,
  }
}

export function reviewForm(patch: Partial<ReviewForm> = {}): ReviewForm {
  return {
    approve: false,
    headline: 'Data scientist in retail forecasting',
    preferences: {
      locations: ['Copenhagen'],
      work_modes: ['hybrid'],
      salary_min: null,
      salary_currency: null,
      work_permits: ['EU'],
      dealbreakers: [],
    },
    experiences: [
      {
        id: 'exp-1',
        keep: true,
        title: 'Data Scientist',
        organisation: 'Nordic Retail Group',
        start: '2020-03',
        end: null,
        summary: 'Demand forecasting for 400 stores.',
        evidence: ['cv: Built demand forecasts for 400 stores'],
      },
    ],
    skills: [
      {
        name: 'python',
        category: 'technology',
        level: null,
        keep: true,
        evidence: ['cv: Python (pandas, scikit-learn)'],
      },
      {
        name: 'forecasting',
        category: 'method',
        level: 4,
        keep: true,
        evidence: ['cv: Built demand forecasts for 400 stores'],
      },
      { name: 'cobol', category: 'technology', level: null, keep: true, evidence: [] },
    ],
    add_skills: [],
    ...patch,
  }
}

export function profile(patch: Partial<CandidateProfile> = {}): CandidateProfile {
  return {
    id: 'profile-1',
    headline: 'Data scientist in retail forecasting',
    sources: [{ id: 'cv', kind: 'cv', uri: 'cv.md', uploaded_at: '2026-11-01T10:00:00Z' }],
    evidence: [
      { id: 'ev-1', source_id: 'cv', quote: 'Built demand forecasts for 400 stores', locator: null },
    ],
    experiences: [
      {
        id: 'exp-1',
        title: 'Data Scientist',
        organisation: 'Nordic Retail Group',
        start: '2020-03-01',
        end: null,
        summary: 'Demand forecasting for 400 stores.',
        skills: ['forecasting'],
        evidence_ids: ['ev-1'],
      },
    ],
    skills: [
      { name: 'python', category: 'technology', self_level: 4, evidence_ids: [] },
      { name: 'forecasting', category: 'method', self_level: 5, evidence_ids: ['ev-1'] },
      { name: 'git', category: 'technology', self_level: null, evidence_ids: [] },
    ],
    preferences: reviewForm().preferences,
    approved_by_candidate_at: '2026-11-02T10:00:00Z',
    ...patch,
  }
}

export function questions(patch: Partial<Questions> = {}): Questions {
  return {
    waiting: [
      {
        skill: 'sql',
        why: 'Your documents mention it but say little about how you used it.',
        text: 'Tell us about a SQL query you wrote that you are proud of.',
      },
      {
        skill: 'spark',
        why: 'Your documents mention it but say little about how you used it.',
        text: 'Where have you used Spark, and on how much data?',
      },
    ],
    answered: [],
    ...patch,
  }
}

export function job(patch: Partial<JobSummary> = {}): JobSummary {
  return {
    name: 'fjord-grocery',
    demo: true,
    ad: {
      ad: 'Senior Data Scientist at Fjord Grocery, Copenhagen. Python and SQL required.',
      company: 'Fjord Grocery',
      title: 'Senior Data Scientist',
    },
    has_rubric: true,
    rubric_version: 1,
    approved: false,
    history: ['extracted'],
    ...patch,
  }
}

export function rubric(patch: Partial<Rubric> = {}): Rubric {
  return {
    version: 1,
    hard_filters: {
      locations: ['Copenhagen'],
      work_modes: ['hybrid'],
      required_work_permits: ['EU'],
      min_years_experience: 4,
    },
    criteria: [
      {
        id: 'c-python',
        kind: 'must_have',
        description: 'Strong Python',
        skill: 'python',
        min_level: 4,
        weight: 5,
        source_quote: 'Python and SQL required',
      },
      {
        id: 'c-spark',
        kind: 'nice_to_have',
        description: 'Spark experience',
        skill: 'spark',
        min_level: null,
        weight: 2,
        source_quote: null,
      },
    ],
    approved_at: null,
    ...patch,
  }
}
