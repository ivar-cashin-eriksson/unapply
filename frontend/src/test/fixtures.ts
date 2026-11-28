// Small synthetic API answers for the component tests, shaped like John Doe's demo
// and the Fjord Grocery job. No real person's data.
import type {
  Board,
  CandidateJobs,
  CandidateProfile,
  CandidateSummary,
  Connection,
  Dashboard,
  Fit,
  JobSummary,
  Listing,
  Overview,
  Questions,
  RankedCandidate,
  ReviewForm,
  Rubric,
  Shortlist,
  ShortlistCandidate,
  SkillLevel,
  Stage,
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

/** A shortlisted candidate before a reveal: no quotes, no role summaries, no contact. */
function person(id: string, levels: [SkillLevel | null, SkillLevel | null][]): ShortlistCandidate {
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
        summary: '',
      },
    ],
    evidence: [],
    skills: SHORTLIST_SKILLS.map((skill, i) => ({
      skill,
      own_level: levels[i][0],
      estimated_level: levels[i][1],
      confidence: levels[i][1] === null ? null : 0.8,
      via: skill === 'sql' && id === 'b0b0' ? 'dbt' : null,
    })),
    progress: {
      profile_id: id,
      stage: 'connected',
      revealed_at: null,
      requested_at: null,
      answered_at: null,
      letter: '',
      files: [],
      unread_messages: 0,
    },
    contact: null,
  }
}

/** The same candidate once revealed at a stage: their name, quotes and role summaries. */
export function revealed(
  c: ShortlistCandidate,
  stage: Exclude<Stage, 'connected'> = 'revealed',
  name = 'Kim Berg',
): ShortlistCandidate {
  const id = c.profile_id
  return {
    ...c,
    experiences: c.experiences.map((x) => ({ ...x, summary: 'Forecasts demand.' })),
    evidence: [{ id: `${id}-e1`, source: 'cv', quote: `Built forecasts in Python (${id})` }],
    contact: { name, email: `${name.split(' ')[0].toLowerCase()}@example.org`, phone: '+45 11 22 33 44' },
    progress: {
      ...c.progress,
      stage,
      revealed_at: '2026-11-27T11:00:00',
      requested_at: stage === 'revealed' ? null : '2026-11-27T11:05:00',
      answered_at: stage === 'applied' || stage === 'declined' ? '2026-11-27T12:00:00' : null,
      letter: stage === 'applied' ? 'Dear Fjord Grocery, I would like to apply.' : '',
      files:
        stage === 'applied' ? [{ id: 7, name: 'cv.pdf', size: 2048, uploaded_at: '2026-11-27T12:00:00' }] : [],
    },
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
    counts: { connected: 3, revealed: 0, requested: 0, applied: 0 },
    vacancies: 1,
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
    work_permits: ['EU'],
    seniority: 'senior',
    skills: ['python', 'sql', 'time series forecasting'],
    posted_at: '2026-11-27T09:00:00',
    demo: true,
    counts: { connected: 13, revealed: 2, requested: 1, applied: 0 },
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
  skills: ['demand forecasting'],
  posted_at: '2026-11-27T08:50:00',
})

export function board(patch: Partial<Board> = {}): Board {
  return {
    listings: [listing(), DAIRY],
    total: 2,
    locations: ['Copenhagen'],
    work_modes: ['hybrid'],
    seniorities: ['junior', 'senior'],
    work_permits: ['EU'],
    vacancies: [1, 2],
    skills: ['demand forecasting', 'python', 'sql', 'time series forecasting'],
    ...patch,
  }
}

export function connection(patch: Partial<Connection> = {}): Connection {
  return {
    job: 'board-fjord-grocery',
    connected_at: '2026-11-27T10:15:00',
    listing: listing(),
    stage: 'connected',
    progress: null,
    unread_messages: 0,
    ...patch,
  }
}

export function fit(patch: Partial<Fit> = {}): Fit {
  return { job: 'board-fjord-grocery', band: 'strong', missed: [], connected: false, place: null, ...patch }
}

/** A connection at a later stage, with the candidate's progress. */
export function progressed(stage: Exclude<Stage, 'connected'>, patch: Partial<Connection> = {}): Connection {
  return connection({
    stage,
    progress: {
      candidate: 'john-doe-demo',
      job: 'board-fjord-grocery',
      stage,
      revealed_at: '2026-11-27T11:00:00',
      requested_at: stage === 'revealed' ? null : '2026-11-27T11:05:00',
      answer: stage === 'applied' || stage === 'declined' ? stage : null,
      answered_at: stage === 'applied' || stage === 'declined' ? '2026-11-27T12:00:00' : null,
      letter: stage === 'applied' ? 'I would like to apply.' : '',
      files: stage === 'applied' ? [{ id: 3, name: 'cv.md', size: 12, uploaded_at: '2026-11-27T12:00:00' }] : [],
    },
    ...patch,
  })
}

/** A job's candidates in aggregate (`GET /jobs/<name>/overview`): counts only. */
export function overview(patch: Partial<Overview> = {}): Overview {
  const bins = (filled: Record<number, number>) => Array.from({ length: 10 }, (_, i) => filled[i] ?? 0)
  return {
    job: 'fjord-grocery',
    rubric_version: 1,
    scorer: 'baseline',
    connected: 4,
    matched: 3,
    passed_hard_filters: 2,
    filters: [
      { name: 'work_permit', passed: 2, failed: 1, unknown: 0 },
      { name: 'location', passed: 2, failed: 0, unknown: 1 },
    ],
    totals: { bins: bins({ 6: 1, 9: 2 }), median: 0.9 },
    own: { bins: bins({ 7: 1, 8: 2 }), median: 0.85 },
    estimated: { bins: bins({ 5: 1, 7: 2 }), median: 0.72 },
    rubric_skills: [
      { skill: 'spark', candidates: 1, related: 0 },
      { skill: 'python', candidates: 3, related: 0 },
      { skill: 'sql', candidates: 2, related: 1 },
    ],
    other_skills: [
      { skill: 'docker', candidates: 2 },
      { skill: 'git', candidates: 1 },
    ],
    counts: { connected: 4, revealed: 2, requested: 1, applied: 1 },
    vacancies: 1,
    ...patch,
  }
}

/** John's dashboard (`GET /candidates/<name>/dashboard`): own levels and quote counts only. */
export function dashboard(patch: Partial<Dashboard> = {}): Dashboard {
  return {
    candidate: 'john-doe',
    approved: true,
    skills: 3,
    rated: 2,
    documents: 7,
    statements: 1,
    areas: [
      {
        category: 'technology',
        skills: [
          {
            name: 'python',
            self_level: 4,
            documents: 4,
            statements: 0,
            comparison: { candidates: 9, levels: [0, 1, 2, 4, 2], median: 4 },
          },
          { name: 'lightgbm', self_level: 3, documents: 2, statements: 1, comparison: null },
        ],
      },
      {
        category: 'domain',
        skills: [{ name: 'retail analytics', self_level: null, documents: 1, statements: 0, comparison: null }],
      },
    ],
    compared_with: 12,
    min_group: 5,
    in_demand: ['excel', 'databricks'],
    following: [{ skill: 'gradient boosting', because: ['lightgbm'] }],
    ...patch,
  }
}

/** The candidate's jobs and success rate (`GET /candidates/<name>/jobs`). */
export function candidateJobs(patch: Partial<CandidateJobs> = {}): CandidateJobs {
  return {
    candidate: 'john-doe',
    jobs: [
      {
        job: 'board-smoerblomst-dairy',
        listing: DAIRY,
        connected_at: '2026-11-27T10:00:00',
        stage: 'connected',
        fit: fit({ job: 'board-smoerblomst-dairy', band: 'good', connected: true }),
        groups: [
          {
            group: 'revealed',
            skills: [
              { skill: 'python', own_level: 4, median: 3 },
              { skill: 'sql', own_level: 2, median: 4 },
              { skill: 'kafka', own_level: null, median: 3.5 },
              { skill: 'dbt', own_level: null, median: 3 },
            ],
            higher: ['python'],
            rare: ['lightgbm'],
            missing: ['kafka', 'dbt'],
            lower: ['sql'],
          },
          {
            group: 'requested',
            skills: [
              { skill: 'python', own_level: 4, median: 4 },
              { skill: 'sql', own_level: 2, median: 4 },
              { skill: 'kafka', own_level: null, median: 4 },
            ],
            higher: [],
            rare: ['lightgbm', 'retail analytics'],
            missing: ['kafka'],
            lower: ['sql'],
          },
        ],
      },
      {
        job: 'board-fjord-grocery',
        listing: listing(),
        connected_at: '2026-11-27T09:30:00',
        stage: 'requested',
        fit: fit({ connected: true }),
        groups: [],
      },
      {
        job: 'board-lynfjord-power',
        listing: null,
        connected_at: '2026-11-27T09:00:00',
        stage: 'connected',
        fit: null,
        groups: [],
      },
    ],
    connected: 3,
    revealed: 1,
    requested: 1,
    applied: 0,
    revealed_rate: 1 / 3,
    requested_rate: 1 / 3,
    min_group: 5,
    ...patch,
  }
}
