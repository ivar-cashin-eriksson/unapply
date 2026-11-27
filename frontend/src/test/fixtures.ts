// Small synthetic API answers for the component tests, shaped like John Doe's demo
// and the Fjord Grocery job. No real person's data.
import type {
  AnonymousCandidate,
  Board,
  CandidateProfile,
  CandidateSummary,
  Connection,
  JobSummary,
  Listing,
  Questions,
  RankedCandidate,
  ReviewForm,
  Rubric,
  Shortlist,
  SkillLevel,
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
        start_precision: 'month',
        end_precision: 'month',
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
      vacancies: 1,
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

const SHORTLIST_SKILLS = ['python', 'sql', 'spark']

function person(id: string, levels: [SkillLevel | null, SkillLevel | null][]): AnonymousCandidate {
  return {
    profile_id: id,
    alias: `Candidate ${id.slice(0, 4).toUpperCase()}`,
    avatar: parseInt(id.slice(0, 4), 16) % 1920,
    headline: `Data scientist ${id}`,
    experiences: [
      {
        title: 'Data Scientist',
        organisation: 'Example Retail',
        start: '2019-03-01',
        end: null,
        start_precision: 'month',
        end_precision: 'month',
        summary: 'Forecasts demand.',
      },
    ],
    evidence: [{ id: `${id}-e1`, source: 'cv', quote: `Built forecasts in Python (${id})` }],
    skills: SHORTLIST_SKILLS.map((skill, i) => ({
      skill,
      own_level: levels[i][0],
      estimated_level: levels[i][1],
      confidence: levels[i][1] === null ? null : 0.8,
      via: skill === 'sql' && id === 'b0b0' ? 'dbt' : null,
    })),
  }
}

function ranked(
  id: string,
  rank: number,
  total: number,
  [own, estimated]: [number | null, number | null],
  passed = true,
): RankedCandidate {
  return {
    rank,
    total,
    own_total: own,
    estimated_total: estimated,
    profile_id: id,
    match_id: `match-${id}`,
    passed_hard_filters: passed,
    hard_filters: [
      { name: 'location', outcome: 'pass', reason: 'Lives in Copenhagen.' },
      passed
        ? { name: 'work_permit', outcome: 'unknown', reason: "The profile doesn't say." }
        : { name: 'work_permit', outcome: 'fail', reason: 'No permit to work in the EU.' },
    ],
    criterion_scores: [
      { criterion_id: 'c-python', score: total, rationale: `python: level used for ${id}.`, evidence_ids: [`${id}-e1`] },
      { criterion_id: 'c-sql', score: 0.5, rationale: 'sql: some evidence.', evidence_ids: [] },
      { criterion_id: 'c-spark', score: 0.25, rationale: 'spark: no evidence.', evidence_ids: [] },
    ],
    model: 'baseline-v1',
    scored_at: '2026-11-27T10:00:00',
    problems: [],
  }
}

/** A shortlist of three: two who pass, and one who fails a hard filter with the highest score. */
export function shortlist(patch: Partial<Shortlist> = {}): Shortlist {
  return {
    ranking: {
      job: 'fjord-grocery',
      rubric_version: 1,
      scorer: 'baseline',
      candidates: [
        ranked('a1a1', 1, 0.9, [0.95, 0.85]),
        ranked('b0b0', 2, 0.6, [0.8, 0.4]),
        ranked('c2c2', 3, 0.95, [null, null], false),
      ],
    },
    rubric: {
      version: 1,
      hard_filters: { locations: ['Copenhagen'], work_modes: [], required_work_permits: ['EU'], min_years_experience: null },
      criteria: [
        { id: 'c-python', kind: 'must_have', description: 'Strong Python', skill: 'python', min_level: 4, weight: 5, source_quote: null },
        { id: 'c-sql', kind: 'must_have', description: 'SQL', skill: 'sql', min_level: null, weight: 3, source_quote: null },
        { id: 'c-spark', kind: 'nice_to_have', description: 'Spark', skill: 'spark', min_level: null, weight: 1, source_quote: null },
        { id: 'c-retail', kind: 'nice_to_have', description: 'Retail experience', skill: null, min_level: null, weight: 2, source_quote: null },
      ],
      approved_at: '2026-11-27T09:00:00',
    },
    skills: SHORTLIST_SKILLS,
    candidates: [
      person('a1a1', [[5, 4], [4, 4], [2, 1]]),
      person('b0b0', [[4, 3], [3, 3], [null, null]]),
      person('c2c2', [[3, 3], [3, 2], [3, 3]]),
    ],
    intents: [],
    reveal_quota: 10,
    ...patch,
  }
}

export function listing(patch: Partial<Listing> = {}): Listing {
  return {
    name: 'board-fjord-grocery',
    company: 'Fjord Grocery ApS',
    title: 'Senior Data Scientist, Pricing and Forecasting',
    ad: [
      '# Senior Data Scientist, Pricing and Forecasting',
      '',
      '**Fjord Grocery ApS** · Copenhagen (hybrid)',
      '',
      'Fjord Grocery runs 85 grocery stores across Denmark.',
      '',
      '## What we are looking for',
      '',
      '- Strong Python and SQL.',
      '- Hands-on experience with time series forecasting in production.',
    ].join('\n'),
    vacancies: 1,
    locations: ['Copenhagen'],
    work_modes: ['hybrid'],
    seniority: 'senior',
    posted_at: '2026-11-27T09:00:00',
    demo: true,
    ...patch,
  }
}

export const DAIRY = listing({
  name: 'board-smoerblomst-dairy',
  company: 'Smørblomst Mejeri',
  title: 'Junior Data Scientist',
  ad: '# Junior Data Scientist\n\nWe forecast how much milk our customers will order.',
  vacancies: 2,
  seniority: 'junior',
  posted_at: '2026-11-27T08:50:00',
})

export function board(patch: Partial<Board> = {}): Board {
  return {
    listings: [listing(), DAIRY],
    total: 2,
    locations: ['Copenhagen'],
    work_modes: ['hybrid'],
    seniorities: ['junior', 'senior'],
    ...patch,
  }
}

export function connection(patch: Partial<Connection> = {}): Connection {
  return { job: 'board-fjord-grocery', connected_at: '2026-11-27T10:15:00', listing: listing(), ...patch }
}
