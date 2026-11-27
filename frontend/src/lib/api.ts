// A small typed client for the unapply API, served under /api (see vite.config.ts).
//
// Paid model calls are never allowed from here: no request adds `allow_api`. Demos
// replay recorded answers, and a server whose operator switched paid calls on
// (UNAPPLY_ALLOW_API_CALLS=1) allows them for everyone.

import type {
  Answers,
  Board,
  BoardDemo,
  BoardQuery,
  CandidateProfile,
  CandidateSummary,
  Connection,
  Extraction,
  Intent,
  IntentKind,
  JobAd,
  JobSummary,
  Listing,
  MaterialFile,
  Questions,
  Ranking,
  ReviewForm,
  Rubric,
  RubricExtraction,
  RubricForm,
  Scorer,
  Shortlist,
  ShortlistDemo,
} from '@/lib/types'

export const BASE = '/api'

const UNREACHABLE = "Can't reach the server. Is `uv run unapply api` running?"

/** An error answer from the API, with its status and the API's message. */
export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }

  /** Whether the server refused a paid model call. */
  get paidCallRefused(): boolean {
    return this.status === 403
  }
}

interface ValidationError {
  loc?: unknown[]
  msg?: string
}

/** Turn FastAPI's error body (a message, or a list of validation errors) into text. */
export function errorDetail(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return (detail as ValidationError[])
        .map((d) => {
          // The first part of the location is "body", which says nothing.
          const where = Array.isArray(d.loc) ? d.loc.slice(1).join(' › ') : ''
          return where ? `${where}: ${d.msg}` : String(d.msg ?? d)
        })
        .join('; ')
    }
  }
  return fallback
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(BASE + path, init)
  } catch {
    throw new ApiError(0, UNREACHABLE)
  }
  if (!response.ok) {
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      // Not JSON, such as the dev server's proxy error when the API is down.
    }
    const fallback =
      response.status >= 500 && body === null
        ? UNREACHABLE
        : `${response.status} ${response.statusText}`
    throw new ApiError(response.status, errorDetail(body, fallback))
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

function json<T>(method: string, path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

const c = (name: string) => `/candidates/${encodeURIComponent(name)}`
const j = (name: string) => `/jobs/${encodeURIComponent(name)}`

export const api = {
  // Candidates
  candidates: () => json<string[]>('GET', '/candidates'),
  createCandidate: (name: string, github: string | null) =>
    json<CandidateSummary>('POST', '/candidates', { name, github }),
  createDemoCandidate: () => json<CandidateSummary>('POST', '/demos/candidate'),
  candidate: (name: string) => json<CandidateSummary>('GET', c(name)),
  setGithub: (name: string, github: string | null) =>
    json<CandidateSummary>('PATCH', c(name), { github }),
  upload: (name: string, files: File[]) => {
    const body = new FormData()
    for (const f of files) body.append('files', f, f.name)
    return request<MaterialFile[]>(`${c(name)}/material`, { method: 'POST', body })
  },
  removeFile: (name: string, file: string) =>
    json<void>('DELETE', `${c(name)}/material/${encodeURIComponent(file)}`),
  extract: (name: string) => json<Extraction>('POST', `${c(name)}/extract`),
  review: (name: string) => json<ReviewForm>('GET', `${c(name)}/review`),
  saveReview: (name: string, form: ReviewForm) =>
    json<CandidateProfile>('PUT', `${c(name)}/review`, form),
  demoReview: (name: string) => json<ReviewForm>('GET', `${c(name)}/demo/review`),
  questions: (name: string) => json<Questions>('GET', `${c(name)}/questions`),
  prepareQuestions: (name: string) => json<Questions>('POST', `${c(name)}/questions`),
  discardQuestions: (name: string) => json<void>('DELETE', `${c(name)}/questions`),
  answer: (name: string, answers: Answers) =>
    json<{ answered: number }>('POST', `${c(name)}/answers`, answers),
  demoAnswers: (name: string) => json<Answers>('GET', `${c(name)}/demo/answers`),
  profile: (name: string) => json<CandidateProfile>('GET', `${c(name)}/profile`),

  // Jobs
  jobs: () => json<string[]>('GET', '/jobs'),
  createJob: (name: string, ad: string) =>
    json<JobSummary>('POST', '/jobs', { name, ad }),
  createDemoJob: () => json<JobSummary>('POST', '/demos/job'),
  job: (name: string) => json<JobSummary>('GET', j(name)),
  setAd: (name: string, ad: JobAd) => json<JobSummary>('PUT', `${j(name)}/ad`, ad),
  extractRubric: (name: string) =>
    json<RubricExtraction>('POST', `${j(name)}/extract`),
  rubric: (name: string) => json<Rubric>('GET', `${j(name)}/rubric`),
  saveRubric: (name: string, form: RubricForm) =>
    json<Rubric>('PUT', `${j(name)}/rubric`, form),

  // Matching and the shortlist
  createShortlistDemo: () => json<ShortlistDemo>('POST', '/demos/shortlist'),
  match: (name: string, scorer: Scorer) =>
    json<Ranking>('POST', `${j(name)}/match?scorer=${scorer}`),
  shortlist: (name: string, scorer: Scorer) =>
    json<Shortlist>('GET', `${j(name)}/shortlist?scorer=${scorer}`),
  recordIntent: (name: string, profileId: string, kind: IntentKind) =>
    json<Intent>('POST', `${j(name)}/intents`, { profile_id: profileId, kind }),

  // The job board: listings (never the rubric), and the candidate's connections
  board: (query: BoardQuery = {}) => {
    const params = new URLSearchParams()
    for (const [key, value] of Object.entries(query)) if (value) params.set(key, value)
    const qs = params.toString()
    return json<Board>('GET', qs ? `/board?${qs}` : '/board')
  },
  listing: (job: string) => json<Listing>('GET', `/board/${encodeURIComponent(job)}`),
  createBoardDemo: () => json<BoardDemo>('POST', '/demos/board'),
  connections: (name: string) => json<Connection[]>('GET', `${c(name)}/connections`),
  connect: (name: string, job: string) =>
    json<Connection>('PUT', `${c(name)}/connections/${encodeURIComponent(job)}`),
  withdraw: (name: string, job: string) =>
    json<void>('DELETE', `${c(name)}/connections/${encodeURIComponent(job)}`),
}

/** A message for an error, saying what to do about a refused paid call. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.paidCallRefused) {
      return (
        'This step needs a paid model call, and paid calls are off on this ' +
        'server. Try the demo, which replays recorded answers for free.'
      )
    }
    return error.detail
  }
  return error instanceof Error ? error.message : String(error)
}
