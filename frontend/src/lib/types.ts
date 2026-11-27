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

export interface Experience {
  id: string
  title: string
  organisation: string
  /** ISO date, "YYYY-MM-DD". */
  start: string | null
  end: string | null
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
