// The API's request and response bodies (src/unapply/api/models.py and the schemas
// in src/unapply/schemas/). Candidate types never carry the assessment: no
// estimates, no claim support.

export type SkillLevel = 1 | 2 | 3 | 4 | 5
export type SkillCategory =
  | 'technology'
  | 'method'
  | 'domain'
  | 'soft_skill'
  | 'language'
  | 'certification'
export type WorkMode = 'onsite' | 'hybrid' | 'remote'
export type CriterionKind = 'must_have' | 'nice_to_have'
export type SourceKind = 'cv' | 'linkedin' | 'github' | 'free_text' | 'interview'

export interface MaterialFile {
  name: string
  size: number
}

export interface CandidateSummary {
  name: string
  demo: boolean
  github: string | null
  material: MaterialFile[]
  has_profile: boolean
  approved: boolean
  questions_waiting: number
  history: string[]
}

export interface Source {
  id: string
  kind: SourceKind
  uri: string | null
  uploaded_at: string
}

export interface Evidence {
  id: string
  source_id: string
  quote: string
  locator: string | null
}

/** How much of a date is known (`unapply.schemas.DatePrecision`). */
export type DatePrecision = 'year' | 'month'

export interface Experience {
  id: string
  title: string
  organisation: string
  /** ISO date, "YYYY-MM-DD": the first day of the month, or of the year. */
  start: string | null
  end: string | null
  /** Whether `start` is known to the month or only to the year. */
  start_precision: DatePrecision
  end_precision: DatePrecision
  summary: string
  skills: string[]
  evidence_ids: string[]
}

export interface Preferences {
  locations: string[]
  work_modes: WorkMode[]
  salary_min: number | null
  salary_currency: string | null
  work_permits: string[]
  dealbreakers: string[]
}

export interface CandidateSkill {
  name: string
  category: SkillCategory | null
  self_level: SkillLevel | null
  evidence_ids: string[]
}

export interface CandidateProfile {
  id: string
  headline: string
  sources: Source[]
  evidence: Evidence[]
  experiences: Experience[]
  skills: CandidateSkill[]
  preferences: Preferences
  approved_by_candidate_at: string | null
}

export interface Extraction {
  profile: CandidateProfile
  rejected_quotes: number
  unsupported: string[]
}

export interface ExperienceEdit {
  id: string
  keep: boolean
  title: string
  organisation: string
  /** "YYYY" or "YYYY-MM", or null if unknown (for `end`: now or unknown). */
  start: string | null
  end: string | null
  summary: string
  /** "source: quote" lines; shown only. */
  evidence: string[]
}

export interface SkillEdit {
  name: string
  category: SkillCategory | null
  level: SkillLevel | null
  keep: boolean
  evidence: string[]
}

export interface NewSkill {
  name: string
  category: SkillCategory
  level: SkillLevel | null
  note: string
}

export interface ReviewForm {
  approve: boolean
  headline: string
  preferences: Preferences
  experiences: ExperienceEdit[]
  skills: SkillEdit[]
  add_skills: NewSkill[]
}

export interface Question {
  skill: string
  why: string
  text: string
}

export interface AnsweredQuestion {
  skill: string
  text: string
  answer: string
}

export interface Questions {
  waiting: Question[]
  answered: AnsweredQuestion[]
}

export interface Answers {
  answers: Record<string, string>
}

export interface JobAd {
  ad: string
  company: string | null
  title: string | null
  /** How many people the job hires, 1 or more; shown to candidates. */
  vacancies: number
}

export interface JobSummary {
  name: string
  demo: boolean
  ad: JobAd
  has_rubric: boolean
  rubric_version: number | null
  approved: boolean
  history: string[]
}

export interface HardFilters {
  locations: string[]
  work_modes: WorkMode[]
  required_work_permits: string[]
  min_years_experience: number | null
}

export interface Criterion {
  id: string
  kind: CriterionKind
  description: string
  skill: string | null
  min_level: SkillLevel | null
  weight: number
  source_quote: string | null
}

export interface Rubric {
  version: number
  hard_filters: HardFilters
  criteria: Criterion[]
  approved_at: string | null
}

export interface Job {
  id: string
  company: string
  title: string
  ad_text: string
  rubric: Rubric
  reveal_quota: number
  vacancies: number
  created_at: string
}

export interface RubricExtraction {
  job: Job
  dropped: string[]
}

export interface CriterionEdit {
  id: string | null
  keep: boolean
  kind: CriterionKind
  description: string
  skill: string | null
  min_level: SkillLevel | null
  /** 1 (minor) to 5 (essential). */
  weight: number
}

export interface RubricForm {
  approve: boolean
  company: string
  title: string
  hard_filters: HardFilters
  criteria: CriterionEdit[]
}

// Matching and the employer's shortlist (src/unapply/api/models.py and
// src/unapply/matching/shortlist.py). Employers see candidates anonymised: an
// alias, never a name. Unlike candidate types, these carry estimated levels.

export type Scorer = 'baseline' | 'llm'
export type IntentKind = 'reveal' | 'request_application'

export interface CriterionScore {
  criterion_id: string
  /** 0 to 1. */
  score: number
  rationale: string
  evidence_ids: string[]
}

export interface HardFilterCheck {
  name: 'location' | 'work_mode' | 'work_permit' | 'min_years_experience'
  outcome: 'pass' | 'fail' | 'unknown'
  reason: string
}

export interface RankedCandidate {
  rank: number
  /** Weighted mean of the criterion scores, 0 to 1; sets the rank. Failed filters are scored too, and rank last. */
  total: number
  /** The baseline's total on own levels only; null if the profile changed since the match. */
  own_total: number | null
  /** The baseline's total on estimated levels only; null like `own_total`. */
  estimated_total: number | null
  profile_id: string
  match_id: string
  passed_hard_filters: boolean
  /** Null if the profile changed since the match. */
  hard_filters: HardFilterCheck[] | null
  criterion_scores: CriterionScore[]
  model: string
  scored_at: string
  problems: string[]
}

export interface Ranking {
  job: string
  rubric_version: number
  scorer: Scorer
  candidates: RankedCandidate[]
}

export interface SkillLevels {
  skill: string
  own_level: SkillLevel | null
  estimated_level: SkillLevel | null
  confidence: number | null
  /** The candidate's related skill the levels come from, such as "dbt" for "sql". */
  via: string | null
}

export interface AnonymousEvidence {
  id: string
  /** "cv", "linkedin", "github", "free_text" or "candidate statement". */
  source: string
  quote: string
}

export interface AnonymousExperience {
  title: string
  organisation: string
  start: string | null
  end: string | null
  start_precision: DatePrecision
  end_precision: DatePrecision
  summary: string
}

export interface AnonymousCandidate {
  profile_id: string
  /** Such as "Cobalt Otter": from the profile id, unique on the job. */
  alias: string
  /** The alias's number, to draw the avatar from (`lib/avatar`). */
  avatar: number
  headline: string
  /** Role summaries are empty until the candidate is revealed. */
  experiences: AnonymousExperience[]
  /** Empty until the candidate is revealed: quotes stay hidden till then. */
  evidence: AnonymousEvidence[]
  /** One per rubric skill, in `Shortlist.skills` order. */
  skills: SkillLevels[]
}

/** How far a connected candidate got on a job, in order. */
export type Stage = 'connected' | 'revealed' | 'requested' | 'applied' | 'declined'

export interface ApplicationFile {
  id: number
  name: string
  size: number
  uploaded_at: string
}

/** A shortlisted candidate's progress, as the employer sees it: no names. */
export interface EmployerProgress {
  profile_id: string
  stage: Stage
  revealed_at: string | null
  requested_at: string | null
  answered_at: string | null
  /** The application, once sent. */
  letter: string
  files: ApplicationFile[]
}

/** Who a candidate is: shown to an employer only once they reveal them. */
export interface Contact {
  name: string
  email: string | null
  phone: string | null
}

export interface ShortlistCandidate extends AnonymousCandidate {
  progress: EmployerProgress
  /** Null until revealed. */
  contact: Contact | null
}

/** How far a job's candidates got. */
export interface ListingCounts {
  connected: number
  revealed: number
  /** Asked to apply, whatever they answered. */
  requested: number
  applied: number
}

/** A candidate's own progress on a job, with their application. */
export interface Progress {
  candidate: string
  job: string
  stage: Stage
  revealed_at: string | null
  requested_at: string | null
  answer: 'applied' | 'declined' | null
  answered_at: string | null
  letter: string
  files: ApplicationFile[]
}

export interface Intent {
  id: number
  job_id: string
  profile_id: string
  kind: IntentKind
  recorded_at: string
}

export interface Shortlist {
  ranking: Ranking
  /** The rubric version ranked against. */
  rubric: Rubric
  skills: string[]
  candidates: ShortlistCandidate[]
  /** The early reveal and application requests, which revealed no one: history. */
  intents: Intent[]
  reveal_quota: number
  counts: ListingCounts
  vacancies: number
}

export interface ShortlistDemo {
  name: string
  candidates: number
}

// The job board

export type Seniority = 'junior' | 'mid' | 'senior' | 'lead'

/** A job as candidates see it: the ad and its vacancies, never the rubric. */
export interface Listing {
  name: string
  company: string
  title: string
  ad: string
  vacancies: number
  locations: string[]
  work_modes: WorkMode[]
  /** Work permits the ad asks for, as ISO country codes or "EU"; empty means none. */
  work_permits: string[]
  seniority: Seniority
  /** The taxonomy's skills the ad names, never the rubric's. */
  skills: string[]
  posted_at: string
  demo: boolean
  counts: ListingCounts | null
}

export interface Board {
  listings: Listing[]
  /** Listings on the board before filtering. */
  total: number
  locations: string[]
  work_modes: WorkMode[]
  seniorities: Seniority[]
  work_permits: string[]
  /** Every number of vacancies on the board, smallest first. */
  vacancies: number[]
  skills: string[]
}

export interface BoardQuery {
  q?: string
  location?: string
  work_mode?: WorkMode
  seniority?: Seniority
  /** Jobs open to someone with this permit: asking for none, or only for ones it covers. */
  work_permit?: string
  /** Jobs hiring at least this many. */
  min_vacancies?: number
  /** Jobs whose ad names every one of these skills, by any name the taxonomy knows. */
  skill?: string[]
  /** The candidate whose fit `fit` and `sort: 'fit'` use; needed for either. */
  candidate?: string
  fit?: FitFilter
  sort?: BoardSort
}

/** The board's fit filter: one band, or the jobs with a requirement the candidate doesn't meet. */
export type FitFilter = FitBand | 'not_met'

/** The board's order: newest first, or best fit first (ties newest first). */
export type BoardSort = 'newest' | 'fit'

/** A job the candidate connected their profile to: their consent for it. */
export interface Connection {
  job: string
  connected_at: string
  listing: Listing | null
  stage: Stage
  /** Null until the employer reveals the candidate. */
  progress: Progress | null
}

/** How well the candidate fits a job, from their own levels only. */
export type FitBand = 'strong' | 'good' | 'partial' | 'low'

/** A hard filter the candidate doesn't meet, named as the ad states it. */
export interface MissedFilter {
  filter: string
  /** Such as "Work permit: EU required". */
  label: string
}

/** The candidate's place in the job's latest ranking. */
export interface Place {
  rank: number
  /** How many connected candidates were ranked. */
  of: number
  ranked_at: string
}

/** How well the candidate fits a job: never a score, criterion or weight. */
export interface Fit {
  job: string
  /** Null if the candidate has no profile yet. */
  band: FitBand | null
  missed: MissedFilter[]
  connected: boolean
  /** Once connected and ranked; null before. */
  place: Place | null
}

/** Skills common among the candidates a job revealed, which the candidate lacks: names only. */
export interface RevealedSkills {
  /** Common skills the profile doesn't list. */
  missing: string[]
  /** Common skills the candidate rated lower than most of the revealed did. */
  lower: string[]
}

/** A job the candidate is connected to, how far they got and their fit. */
export interface JobOutcome {
  job: string
  /** Null if the job is no longer on the board. */
  listing: Listing | null
  connected_at: string
  stage: Stage
  fit: Fit | null
  /** Only where they weren't revealed and at least `min_group` others were. */
  revealed_skills: RevealedSkills | null
}

/** The candidate's jobs and their success rate (`GET /candidates/<name>/jobs`). */
export interface CandidateJobs {
  candidate: string
  /** Newest connection first. */
  jobs: JobOutcome[]
  connected: number
  revealed: number
  /** Asked to apply, whatever they answered. */
  requested: number
  applied: number
  /** From 0 to 1; null with no connections. */
  revealed_rate: number | null
  requested_rate: number | null
  min_group: number
}

export interface BoardDemo {
  /** The demo jobs on the board, newest first. */
  jobs: string[]
}

/** How the matched candidates did on one hard filter (`GET /jobs/<name>/overview`). */
export interface FilterCount {
  name: HardFilterCheck['name']
  passed: number
  failed: number
  /** The profile doesn't say: not excluded. */
  unknown: number
}

/** Candidates per tenth of a score from 0 to 1; the last bin includes 1. */
export interface Distribution {
  bins: number[]
  median: number | null
}

export interface RubricSkillCount {
  skill: string
  /** Candidates with the skill itself. */
  candidates: number
  /** Candidates without it, but with a skill that counts for it ("dbt" for "sql"). */
  related: number
}

export interface SkillCount {
  skill: string
  candidates: number
}

/** A job's candidates in aggregate: counts only, never one candidate. */
export interface Overview {
  job: string
  rubric_version: number
  scorer: Scorer
  connected: number
  matched: number
  passed_hard_filters: number
  /** Those failed most first. */
  filters: FilterCount[]
  totals: Distribution
  own: Distribution
  estimated: Distribution
  /** In rubric order. */
  rubric_skills: RubricSkillCount[]
  /** Skills outside the rubric, most common first. */
  other_skills: SkillCount[]
  counts: ListingCounts
  vacancies: number
}

/** Other candidates' own levels in a skill, in aggregate (at least five of them). */
export interface Comparison {
  candidates: number
  /** How many gave each level: index 0 is level 1, index 4 is level 5. */
  levels: number[]
  median: number
}

/** One of the candidate's skills on their dashboard: own level and quote counts only. */
export interface DashboardSkill {
  name: string
  self_level: SkillLevel | null
  /** Quotes from their documents that mention it. */
  documents: number
  /** Their own statements about it: answers and review notes. */
  statements: number
  comparison: Comparison | null
}

export interface DashboardArea {
  category: SkillCategory | null
  skills: DashboardSkill[]
}

export interface FollowingSkill {
  skill: string
  because: string[]
}

/** The candidate's overview of their own profile, never the assessment. */
export interface Dashboard {
  candidate: string
  approved: boolean
  skills: number
  rated: number
  documents: number
  statements: number
  areas: DashboardArea[]
  /** Other candidates compared with; 0 when fewer than `min_group`. */
  compared_with: number
  min_group: number
  in_demand: string[]
  following: FollowingSkill[]
}
