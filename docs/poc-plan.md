# POC plan

## What the POC must prove

1. **Ranking quality (primary).** LLM ranking over structured profiles produces shortlists that
   people who hire agree with about as much as they agree with each other.
2. **Candidate willingness.** People will upload a rich profile once instead of writing applications.
3. **Employer willingness to pay.** Companies pay to reveal a ranked, anonymised shortlist.
   Companies are the first paying side.

## Milestones

### M0: Schemas (done)
Pydantic models for Profile, Evidence, SkillRating, Rubric and Match (`src/unapply/schemas/`).

### M1: Candidate ingestion (done)
- Inputs: CV PDF, LinkedIn data export, GitHub URL, free text.
- LLM extraction into `Profile`; every claim gets `Evidence`, and quotes not found
  verbatim in their source are discarded.
- The candidate reviews and approves the profile through a YAML review sheet
  (`unapply review export` / `apply`): own levels, removals, corrections, added skills.
- Result on the author's own material (CV, resume-builder profile, LinkedIn, GitHub):
  48 of the 50 skills in their hand-written list extracted, no invented quotes.
- Dates keep their precision: a date the source gives only as a year is stored and
  shown as a year ("2019"), one with a month as a month ("2019-08"), so January is
  no longer mistaken for a year. Synonyms ("radiotherapy planning" vs "radiation
  therapy planning") are merged through the skill taxonomy (below).
- Folders skip files that describe the folder rather than the candidate (READMEs,
  JSON or YAML schemas); `unapply ingest --exclude` leaves out more. Uploads in the
  API and the frontend are each read; a candidate removes a file to leave it out.

### M2a: Skill estimation and claim support (done)
- `unapply estimate`: one model call estimates every skill's level, confidence and a
  reason from its evidence and the candidate's roles. The model never sees the
  candidate's own levels. Estimates resting only on the candidate's statements are
  capped at confidence 0.3.
- Confidence means how sure the estimate is close to the real level: "familiar with"
  or a course is evidence of a low level, a bare skills-list entry is no information.
- Claim support (deterministic) sorts rated skills into findings: overclaims (own
  level 2+ above a sure estimate), unverified (2+ above, evidence says little),
  underclaims, and skills backed only by the candidate's statement. Shown as counts,
  such as "3 overclaims, 4 unverified, 0 underclaims, 2 only your own statement, of
  26 rated skills". Not shown to the candidate (see the candidate app below).
- John Doe's answer key is met: all three overclaims, four unverified skills and both
  self-stated skills flagged, consistent skills left alone.
- Known limits: evidence for one skill that implies another (dbt implies SQL) isn't
  shared in estimation (the skill taxonomy records the relation, for matching); cross-source consistency (dates in CV vs LinkedIn) isn't checked yet.
- Open question: whether and how findings combine into one score. A mean penalty
  over rated skills (`penalty_score`, kept but not used) lets a few large overclaims
  among many honest ratings still score high (John: 0.93). Counts for now.

### M2b: Gap-filling interview (done)
- Rules choose up to 8 skills: unverified first, then those backed only by the
  candidate's statement, then overclaims (as a chance to show more), highest
  self-rated first, never the same skill twice.
- Sonnet 5.5 words each question from the skill's evidence and the roles, asking for
  one concrete example; a template stands in for any it skips.
- `unapply interview export` / `apply`: answers become the candidate's statements,
  with their question, and clear the answered skills' estimates; `unapply estimate`
  then re-estimates only those, so other estimates don't drift between runs.
- John Doe: a detailed pandas answer raised it from 1 to 4 (confidence 0.55); a vague
  Git answer changed nothing; an honest "only the course" made the deep learning
  estimate surer; a concrete Kubernetes statement stayed capped at confidence 0.3.

### Candidate app (done)
- `unapply app`: a Streamlit app for every candidate step (material, review,
  estimate, interview, profile), on top of the same functions as the CLI. Edits
  become review and interview sheets, so validation is shared.
- Paid API calls are off unless the sidebar toggle is on in that session (and the
  `UNAPPLY_ALLOW_API_CALLS` switch or `--allow-api` for the CLI); every real call is
  logged with an estimated cost. A John Doe demo replays recorded answers for free.
- Tested headlessly with Streamlit's AppTest, clicking through John's whole journey.
- The assessment is hidden from candidates: steps are Material, Review, Questions and
  Profile; estimation runs in the background when questions are prepared and answers
  submitted; interview wording is neutral; the profile and its download leave
  estimates out. Candidates are told their evidence is assessed and can ask for the
  assessment. A developer view adds an internal Assessment page. A test checks that
  no assessment wording appears on any candidate page.

### M3: Job rubric (done)
- `unapply job extract`: a job ad becomes a draft rubric: hard filters (locations,
  work modes, work permits, minimum years) and must-have / nice-to-have criteria with
  skill, minimum level and weight 1 to 5. Every criterion quotes the ad; criteria
  whose quote isn't in it, or that repeat another, are dropped. Instructions in the
  ad are ignored (the fixture ad contains one).
- `unapply job export` / `apply`, and the app's Employer side: the recruiter edits
  filters and criteria and approves; any change raises the rubric's version.
- Demo: the fictional Fjord Grocery ad, which fits John Doe partly, with a recorded
  extraction: Claude found the filters (Copenhagen, hybrid, EU, 4+ years), 6
  must-haves and 4 nice-to-haves, dropped nothing and ignored the injected line.

### M4: Matching (done)
- `src/unapply/matching/`, `unapply match <job> [--scorer baseline|llm]` and the API's
  `/jobs/<name>/match` and `/ranking`. Only approved profiles, only approved rubrics,
  and matching locks the rubric version.
- Deterministic hard filters first: work mode, location, work permit (EU and member
  states) and minimum years of work (month precision, overlapping roles counted
  once, education left out by a title heuristic). Missing information is "unknown",
  not a failure. Candidates who fail a filter are scored too (since issue #12), and rank after everyone who passes.
- Two scorers, each giving a score from 0 to 1 per criterion with a reason and
  evidence ids: a **baseline** in plain code (level against `min_level`, blending
  own and estimated levels by confidence, times an evidence factor; related skills
  through the taxonomy, discounted) and an **LLM scorer** (one call per candidate,
  on the anonymised profile; cited ids checked to be the candidate's).
- Then `Match.total` and a ranking (equal totals share a rank).
- An append-only audit log (`audit_log`, `unapply.matching.audit`): every match
  (rubric version and hash, profile hash, scorer, model, scores, hard filter
  outcomes, time) and every ranking (the rubric and the ranked matches in full), so
  a ranking can be reproduced from the log alone. `unapply audit <job>` checks it.
- John Doe against Fjord Grocery: 0.81 (baseline) and 0.71 (LLM, from a hand-written
  stand-in answer until it is recorded). Both put forecasting, Python and A/B
  testing high and SQL, Spark and deep learning low.
- Known limits: the baseline can't score criteria without a skill (Fjord's "retail or
  e-commerce"); places know only a little geography: a small
  gazetteer (`matching/places.py`) matches a city to its country and native names
  ("Denmark" and "København" match "Copenhagen"), and other places are matched by
  name; hard filter outcomes are kept in the audit log, not with the
  match.
- The MCP server (`src/unapply/mcp_server/`, `unapply mcp <job>`): one per job, with
  read-only tools scoped to the candidates who opted in to it and to the sections
  each shared (`get_experiences`, `get_skills`, `search_evidence(query)`,
  `get_preferences`, plus `get_rubric` and `list_candidates`); anonymised as on the
  job's shortlist, with the same per-job aliases (task 21). Consent per job is `unapply consent grant|withdraw|list`. No agent
  scores over it yet: the LLM scorer still gets the anonymised profile in one call.

### M5: Recruiter view
- Anonymised ranked list with explanations.
- **Spider chart comparing selected candidates** on the rubric's skills, toggling between
  self-reported and estimated levels (and an overlay of both).
- "Reveal" button (no payment yet) and "Request application" button.
- Done: the Shortlist step in the frontend (`frontend/src/pages/employer/Shortlist.tsx`)
  over `GET /jobs/<name>/shortlist` (`src/unapply/matching/shortlist.py`): candidates
  by alias ("Cobalt Otter") and abstract avatar, unique within the job and different
  on every other job (from the profile and job ids together, task 21), with each criterion's score, reason and cited quotes, and hard filter
  outcomes; a spider chart of up to three candidates (estimated, own or both, with a
  table); "Reveal" and "Request application" recorded once each in the `intents`
  table, reveals limited to the job's `reveal_quota`. The shortlist demo stores the
  synthetic pool. Revealing shows no identity yet: that needs payment and consent.
- Done (task 12): each card shows the scorer's total, which sets the rank, beside
  the baseline on own levels only ("Own rating") and on estimated levels only
  ("Estimated from evidence"). Candidates who fail a hard filter are scored by both
  scorers and shown below a "Don't meet the requirements" divider, on a light red
  card naming the failed filters.

- Decided flow (2026-11-27, issues #14 and #16): a
  candidate gets in with one click, **Connect my profile**, which is their consent to
  be ranked anonymously and revealed. The employer pays to reveal anyone connected,
  then can ask anyone revealed to apply properly with written material. One button
  steps through Reveal, then Request application; a request needs a reveal first.
  Quotes stay hidden until reveal. A job has a number of vacancies.
- Done (task 16, `src/unapply/jobs/hiring.py`, `src/unapply/api/hiring.py`): one
  button per card steps through Reveal, Request application, waiting, and Applied or
  Declined. A reveal needs a connected candidate and a reveal left in the quota,
  records a charge intent (nothing is paid) and an audit log entry, and shows the
  candidate's name, contact details, quotes and role summaries, all hidden before
  (tested on every employer route). Requesting before a reveal is refused in the
  API. The candidate applies with a letter and files, or declines; the employer
  sees and downloads the application. Progress is stored per candidate and job
  (`job_progress`, `application_files`, migration `0008`). The early intents stay
  as history.
- Done (task 26, `src/unapply/jobs/ask.py`, `src/unapply/api/ask.py`): **Ask** on a
  revealed candidate's card: the employer asks in plain language and a model answers
  from that candidate's own material only (headline, roles, skills with their own
  levels, quotes; never the rubric, estimates, claim support, preferences or anyone
  else), citing quotes. Cited ids are checked to be the candidate's; an answer
  citing none counts as not answered, and the card says when the material doesn't
  answer. Refused before the reveal (409) and, unless allowed, as a paid call (403).
  Nothing is stored: the page keeps the conversation and sends it back with each
  question. Pool candidates replay hand-written stand-ins for two demo questions
  (`tests/fixtures/pool/questions.yaml`), recorded with `unapply ask`.

### M6: Candidate view
- "You're #4 of 37 for this role." The profile, without the assessment.
- A job board to search listings and connect, with a fit indicator for each (a band
  from own levels before connecting, the place among connected candidates after) and
  each listing's vacancies and counts: connected, revealed, asked to apply,
  applications.
- Done (task 14): the **job board**, the candidate's Jobs step in the frontend
  (`frontend/src/pages/candidate/Jobs.tsx`) over `GET /board` and `GET /board/<job>`
  (`src/unapply/jobs/board.py`): jobs with an approved rubric, searched by words in
  the title, company and ad and filtered by location (remote jobs too), work mode
  and seniority (read from the title); a listing shows the ad and its vacancies,
  never the rubric. **Connect my profile** grants the job consent with its time
  (only approved profiles); only connected candidates are matched and ranked, and
  withdrawing takes the candidate out of the next ranking (earlier audit entries
  stay), refused once they are revealed. A job has `vacancies` (default 1), set
  with the ad. Ten more invented demo jobs (`tests/fixtures/jobs`, listed in
  `board.yaml`, with hand-written stand-in rubrics) sit beside Fjord Grocery, with
  the synthetic pool connected to each.
- Done (task 15): the **fit** on each board card and listing
  (`src/unapply/jobs/fit.py`, `GET /candidates/<name>/fit[/<job>]`): a band from
  the baseline on the candidate's own levels only (on the profile without estimates
  or claim support; strong from 0.8, good from 0.6, partial from 0.3, else low), the
  hard filters they miss named as in the ad, and after connecting their place in
  the job's latest ranking in the audit log.
- Done (task 16): each listing's counts (connected, revealed, asked to apply,
  applications) on the board, the listing and the shortlist; requests to apply on
  top of the board and on the listing, with the application form; once revealed,
  the listing says so and the connection can't be withdrawn.
- Done (task 17, `src/unapply/matching/overview.py`,
  `frontend/src/pages/employer/Overview.tsx`): the job's Overview step, with the
  candidates in aggregate (counts, failed hard filters, score histograms, skills
  against the rubric's, and the funnel against the vacancies). No quotes or
  identities.
- Done (task 19, `src/unapply/dashboard.py`,
  `frontend/src/pages/candidate/Dashboard.tsx`): the candidate's Dashboard step:
  skills by area with own levels and quote counts, own levels compared with other
  candidates' (groups of at least five), and tips from the board's skills and the
  taxonomy. Built from candidate views of the profiles, so no estimate or claim
  support can reach it.
- Done (task 20, `src/unapply/jobs/outcomes.py`): on the Dashboard, the jobs the
  candidate connected to with their stage and fit, their success rate (revealed,
  and asked to apply, out of connected), and for a job where they weren't revealed
  the skills common among the candidates who were (at least five) that they lack
  or rated lower, from own levels only. Reworked after Ivar's review: the
  dashboard has three sheets (profile, jobs, compared on jobs); the comparison
  covers the revealed, those asked to apply and those who applied, whatever the
  candidate's stage, each from five others, with a spider chart against the
  group's median own levels and where the candidate stands out.
- Done (task 22): **Connect my profile** and **Withdraw** on each board card, the
  same action and rules as on the listing (approved profiles only, no withdrawing
  once revealed; a revealed card says the connection stays).
- Done (task 23): the board filters by the candidate's **fit** (a band, or
  "Requirements not met": jobs with a hard filter they miss) and sorts best fit
  first, ties newest first (`GET /board?candidate=&fit=&sort=fit`, worked out in
  `jobs/fit.py`, nothing stored). The board keeps the last results on screen while
  the next search loads.
- Done (task 24): an **Advanced** section on the board with filters for work permit
  (a member state's permit covers "EU"), vacancies (at least so many) and the
  skills an ad names, found in the ad text through the taxonomy so synonyms match
  (`ad_skills` in `jobs/board.py`, never a criterion's). The filters live in the
  address, and every pill on a card or listing (location, work mode, seniority,
  work permit, vacancies, skills, fit) adds its filter, shown as removable chips.
- Done (task 25): **messages** after a reveal: one thread per candidate and job,
  on the employer's shortlist card and the candidate's listing, newest at the
  bottom, with unread counts on the shortlist and board cards; no email or push
  notifications (`jobs/messages.py`, the `messages` table, migration 0009). No
  thread exists before a reveal, enforced in the API, and each side reaches only
  its own threads. Messages are the candidate's data and in their export
  (`GET /candidates/<name>/messages`).

## The key experiment (run alongside M1–M4)

- 30–50 real CVs (with consent) and 4–5 real job ads.
- 2–3 people who hire each shortlist the top 10 by hand for each job.
- Compare the system's ranking with theirs (top-k overlap, Kendall's tau), using agreement
  between the humans as the ceiling.
- Done so far: `unapply evaluate` (`src/unapply/evaluation/`) computes both metrics
  for each scorer against a reference ranking, a YAML file of candidates and ranks
  (`--reference`), and runs on a synthetic pool of 12 candidates for Fjord Grocery
  with an intended ranking (`tests/fixtures/pool/`). On it the baseline scores
  top-3 1.00, top-5 0.80, tau 0.82; it ranks an overclaimer 4th instead of 8th,
  because unsure estimates leave room for the candidate's own levels. The LLM
  scorer's answers are hand-written stand-ins until recorded. `--reference` can be
  repeated, one file per person who hires: each scorer is compared with each and
  with the mean, beside the mean agreement between the people over every pair (the
  ceiling; `rater_agreement` in `evaluation/metrics.py`). `--job` compares a real
  job's ranking from the audit log, as its employer saw it, with the references
  instead (`evaluation/stored.py`), without scoring anyone again. `--sheet` writes
  a blank reference for a person who hires to fill in: the candidates in
  alphabetical order with empty ranks, refused until every rank is filled in.

## Out of scope for the POC

Payments, a separate MCP server per person (one multi-tenant server with consent-scoped tools
instead), production auth, multi-company tenancy, and verification (references, certificates).

## Stack

Python 3.12, uv, Pydantic, SQLAlchemy 2.0 and Alembic (SQLite now, Postgres + pgvector later:
a URL change), FastAPI, the MCP Python SDK, the Claude API, a React frontend (Vite,
TypeScript, Tailwind CSS, shadcn/ui), and Streamlit as the internal developer tool.

### Database (done)
- `src/unapply/db/`: tables for candidates and their profiles (sources, evidence,
  experiences, skills with own level and estimate, claim support), interview questions
  and answers, jobs, rubric versions and criteria, matches and criterion scores, and
  the history of every step. Migrations build them from empty on SQLite and render for
  Postgres.
- A repository saves and loads the existing schemas (John Doe's profile at every step
  and Fjord Grocery's job load back equal). Rubric versions that a match refers to
  can't change. `unapply db init` and `unapply db import <workspace>`.
- The app still works on workspace folders; the API will use the database.

### Skill taxonomy (done)
- `config/skills.yaml`: 86 canonical skills (data science, data engineering, a few
  domains and spoken languages) with synonyms, and two relations: implies ("dbt" →
  "sql", "pytorch" → "deep learning") and broader ("lightgbm" → "gradient boosting").
  Checked on load: a name belongs to one skill, relations name canonical skills, no
  cycles.
- Names are canonicalised at extraction, review and rubric time, so synonyms merge;
  a review merges skills that an older profile kept apart and estimates them again.
- `Taxonomy.implied` and `Taxonomy.supporting` follow the relations, for matching.
  `unapply db init` copies the taxonomy into its tables.

### API (done)
- `src/unapply/api/`: FastAPI routes over the database for candidates (create,
  upload material, extract, review, questions, answers, profile), jobs (create, ad,
  extract rubric, read versions, edit and approve the rubric) and the two demos.
  `unapply api` starts it; OpenAPI docs at `/docs`.
- Candidate routes return the profile without the assessment; the assessment is only
  on `/internal/...` routes, added with `unapply api --internal`.
- Paid model calls are refused (403) unless the request adds `?allow_api=true` or the
  switch is on; a refused request changes nothing. Demos replay recordings.
- Matching routes (M4): `POST /jobs/<name>/match`, `GET /jobs/<name>/ranking`.

### Frontend (done)
- `frontend/`: Vite, React, TypeScript, Tailwind CSS and shadcn/ui, light theme with
  the indigo accent, over the API. Candidate steps: material (drag and drop, GitHub),
  review (headline, skills with level chips and their quotes, experience,
  added skills, preferences, approval), questions, and the profile as employers see
  it. Employer steps: the job ad and the rubric editor (hard filters, criteria with
  their quotes, lowest level, weight 1 to 5, kind, approval; any change is a new
  version). No assessment anywhere.
- Both demos run free in the browser; for anything else the frontend never asks for
  paid calls and says to try the demo when the API refuses one.
- Component tests (Vitest) and both demos end to end in Chromium (Playwright, which
  starts and stops the API and the dev server itself); CI runs lint, build and both.
  Screenshots in `docs/screenshots/`.
- Streamlit stays as the internal developer tool. The recruiter's shortlist and
  spider chart (M5) are in the same frontend.
