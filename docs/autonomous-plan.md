# Autonomous plan

Work through the tasks below in order while Ivar is away, until the usage limit is
reached. Run it with `pwsh scripts/autorun.ps1`: one fresh Claude Code session per
task, so no context carries over. Each session reads this file and
`docs/progress.md`, finishes an unfinished task or takes the first one that isn't
done, logs it, and exits.

## Ground rules

These apply to every task. If a rule and a task disagree, the rule wins.

### No paid API calls

- Never pass `--allow-api`, set `UNAPPLY_ALLOW_API_CALLS=1`, turn on the app's API
  toggle, run tests with `UNAPPLY_LIVE=1`, or call any other paid API.
- Where a feature needs a model answer (tests, demos), write a **hand-written
  stand-in** in the recording format, with
  `"model": "hand-written placeholder, not a model answer: re-record with --record"`.
  Make it as realistic as possible: quotes copied verbatim from the material, plausible
  levels and reasons. List every stand-in in `docs/to-record.md` with the command that
  records it.

### Git

- While working on this plan: one `feat/<task>` (or `fix/`, `chore/`, `docs/`,
  `test/`) branch per task, **from `dev`**. Merge it into `dev` with `--no-ff` when
  the task is done and every check passes (below), push `dev`, then delete the branch
  locally and on GitHub.
- Once every task here is done or blocked: create `user/claude` from `dev`. Any further
  work goes on branches from `user/claude` and is merged into `user/claude`, never into
  `dev`.
- Never commit to, merge into or push `main`. Never force-push. Never rewrite history.
- Commit messages: `<type>: <Summary>`, ending with the co-author line. Commits use the
  repo's local git email (the GitHub noreply address); don't change git config.

### Checks before every merge

1. `uv run ruff check .` and `uv run ruff format --check .`
2. `uv run pytest -q -p no:logging`
3. Once the frontend exists: `npm run lint`, `npm run build` and its tests in
   `frontend/`.

Never weaken, skip or delete a test to make it pass. If a check can't pass, the task is
blocked.

### Data and system

- Never read, change or delete `data/ivar/` or anything else under `data/` that a test
  or demo didn't create. Use only synthetic fixtures under `tests/fixtures/`.
- Node.js is installed per user at
  `C:\Users\ice\AppData\Local\Programs\node\node-v26.13.1-win-x64`. Shells started
  by this session may not have it on PATH: prefix commands with
  `export PATH="/c/Users/ice/AppData/Local/Programs/node/node-v26.13.1-win-x64:$PATH"`
  (bash) or `$env:Path = "...;" + $env:Path` (PowerShell).
- Install Python packages with `uv add`, JavaScript packages with `npm install` inside
  `frontend/`. Install nothing system-wide.
- Don't leave servers running: start them from a script that stops them itself (as
  the screenshot script does), and stop any you start.

### Logging and getting stuck

- After each task, add a line to `docs/progress.md`: date, task, branch, what was done,
  what was tested, anything Ivar should know.
- If a task needs a decision only Ivar can make, or can't be done without breaking a
  rule: write the question under "Questions for Ivar" in `docs/progress.md`, mark the
  task blocked, and go on with the next one. Don't guess at product decisions; take the
  conservative option and note it if a choice is small.
- Keep the code standards in `CONTRIBUTING.md` (NumPy docstrings, type hints, tests),
  and update README, `docs/poc-plan.md` and `AGENTS.md` as things change.

## Tasks

Mark a task done by changing `[ ]` to `[x]` in the same merge that finishes it.

### 1. [x] CI on GitHub

- `.github/workflows/ci.yml`: on push and pull request, set up uv and Python 3.12, run
  `ruff check`, `ruff format --check` and `pytest`. Later tasks add the frontend checks.
- Done when: the workflow file is valid and every check it runs passes locally. (Its
  first run on GitHub happens on push; note in the log if it fails there.)

### 2. [x] Database (SQLite now, Postgres later)

- SQLAlchemy 2.0 models and Alembic migrations. `UNAPPLY_DATABASE_URL`, by default
  `sqlite:///data/unapply.db`; nothing SQLite-specific, so Postgres is a URL change.
- Tables: candidates, sources, evidence, experiences, candidate skills (own level,
  estimate fields), claim support, interview questions and answers, jobs, rubric
  versions (immutable once matched), criteria, matches and criterion scores, a skill
  taxonomy (task 3), an audit log (task 6).
- A repository layer that saves and loads the existing Pydantic schemas, so callers
  don't change. `unapply db init`, and `unapply db import <workspace>` for existing
  workspace folders.
- Done when: saving and loading a `Profile` and a `Job` gives back equal objects
  (John Doe and Fjord Grocery fixtures); migrations build the schema from empty; the
  CLI commands work; README documents it.

### 3. [x] Skill taxonomy

- `config/skills.yaml`: canonical skills with synonyms ("radiation therapy planning"
  → "radiotherapy planning", "scikit learn" → "scikit-learn") and relations: implies
  ("dbt" → "sql", "pytorch" → "deep learning") and broader ("lightgbm" → "gradient
  boosting"). Loaded into the taxonomy tables.
- Canonicalise skill names at extraction, review and rubric time through it.
- Done when: tests show synonyms merge, implied skills are found, and existing
  fixtures still pass.

### 4. [x] API (FastAPI)

- `src/unapply/api/`: endpoints over the database for candidates (create, upload
  material, extract, review, questions, answers, profile), jobs (create, ad, extract
  rubric, edit rubric) and, after task 5, matching. The candidate profile endpoints
  return `candidate_view` (no assessment); assessment endpoints are internal only.
- Paid model calls are refused unless the request is explicitly allowed, exactly like
  `--allow-api`; demo candidates and jobs replay recordings.
- `unapply api` starts it (uvicorn). OpenAPI docs at `/docs`.
- Done when: tests with FastAPI's TestClient cover each endpoint, including refusal of
  paid calls and the hidden assessment.

### 5. [x] Matching (M4)

- Hard filters in plain code: location, work mode, work permit, minimum years (from
  experience dates, counting overlapping roles once).
- A **baseline scorer** with no model: per criterion, skill match through the
  taxonomy, own and estimated levels against `min_level`, evidence count. Fully
  deterministic.
- An **LLM scorer**: per candidate and job, a score per criterion from 0 to 1 with a
  reason and cited evidence ids (checked to belong to the candidate), never seeing the
  candidate's name or contact details. Hand-written stand-in recordings for the
  fixtures.
- `Match.total`, ranking, `unapply match <job> [--scorer baseline|llm]`.
- Done when: John Doe against Fjord Grocery is scored by both scorers with sensible
  results, hard filters are tested at their edges, and everything runs offline.

### 6. [x] Ranking audit log

- Every match and ranking records rubric version, profile version (hash), scorer and
  model, scores and time, in an append-only audit table.
- Done when: a ranking can be reproduced from the log, and a test checks it.

### 7. [x] Synthetic candidate pool and evaluation script

- 12 fictional candidates for Fjord Grocery, from a clear fit to unsuitable, each with
  a short CV, an approved profile (with hand-written stand-in extraction and
  estimation, evidence quoting the CV verbatim) and an **intended rank** with reasons.
  Vary the tricky cases: overclaimers, strong but outside the EU, too junior, a great
  fit using synonyms, a career changer.
- `unapply evaluate`: top-k overlap and Kendall's tau of a ranking against a reference
  ranking (intended now, human shortlists later), for both scorers.
- Done when: the evaluation runs offline on the pool and the results are in the log.

### 8. [x] New frontend (React)

- `frontend/`: Vite, React, TypeScript, Tailwind CSS and shadcn/ui, talking to the API.
  Modern and easy to use: clear steps, generous spacing, good empty and loading states,
  keyboard friendly, light theme with the indigo accent.
- Candidate flow: material upload with drag and drop, review (editable skills and
  experience, levels as chips), questions, profile. No assessment anywhere.
- Employer flow: job ad, rubric editor.
- Demo mode (John Doe, Fjord Grocery) that works without paid calls.
- Tests: component tests (Vitest) and an end-to-end run of both demos (Playwright).
  CI runs lint, build and tests.
- Streamlit stays as the internal developer tool.
- Done when: both demos work end to end in the browser, checked with screenshots, and
  all checks pass.

### 9. [x] Employer views (M5)

- In the new frontend: an anonymised, ranked shortlist with per-criterion
  explanations and cited evidence; a spider chart comparing selected candidates on the
  rubric's skills, toggling own and estimated levels; "Reveal" and "Request
  application" buttons that record intent (no payment).
- Done when: the views work on the synthetic pool in the demo, with tests and
  screenshots.

### 10. [x] Smaller fixes

- Dates: store whether a date is year or month precision, and show it that way.
- Ingestion: skip files that describe a schema rather than the candidate (such as a
  README in a profile folder), or let the candidate exclude files.
- Streamlit review table: show full evidence in a detail view.
- Done when: each is tested.

### 11. [x] MCP server

- Consent-scoped tools over the database for a job's matching agent:
  `get_experiences`, `get_skills`, `search_evidence(query)`, `get_preferences`, only
  for candidates who opted in to that job, never their name or contact details.
- Done when: tested with the MCP SDK's in-process client.

Tasks 12 to 20 come from Ivar's `TODO.md` and requests (2026-11-27). Where a task lists
"decisions to check", take the option written there, note it in the log, and don't
widen it.

### 12. [x] Shortlist: own and estimated scores, and failed filters

- Each ranked candidate shows two scores side by side: one from their own levels and
  one from the estimated levels (the baseline scorer run with only own, then only
  estimated levels), as well as the scorer's total, which still sets the rank. Label
  them clearly ("Own rating", "Estimated from evidence").
- Candidates who fail a hard filter are scored too (both scorers) and shown, with
  their scores, below a divider ("Don't meet the requirements") after everyone who
  passes. Their cards stand out: a light red or hatched background, with the failed
  filters named. They still rank after every passing candidate, whatever their score.
- This reverses task 5's "candidates failing a filter aren't scored": update its
  tests, the audit log entries (failed candidates now have scores) and the
  evaluation, where filter failures keep sharing the last place in the reference.
- Done when: the shortlist demo shows both scores and the divider on the pool, with
  Vitest, pytest and Playwright tests and refreshed screenshots.

### 13. [x] Anonymous candidate identities

- Replace aliases such as "Candidate 3F2A" with human-readable ones (adjective and
  animal or object, such as "Amber Otter"; never person names), and give each
  unrevealed candidate a generated avatar (abstract or geometric SVG, made in the
  frontend). Both come from the profile id, so they are the same in every view, and
  are unique within a job.
- Avatars never suggest gender, age or ethnicity, and nothing is sent to an outside
  avatar service.
- Done when: tested (stable for a profile id, unique on the pool, no clashes with
  candidate names) and visible in the shortlist screenshots.

### 14. [x] More demo jobs, vacancies and a job board

- About ten more fictional job listings beside Fjord Grocery, under
  `tests/fixtures/jobs/<name>/` in the same layout (`ad.md`, a hand-written stand-in
  `extraction.json` with quotes verbatim from the ad, a README). Invented companies
  only, with no real company's name, logo or branding. Vary them: roles (data
  scientist, analyst, ML engineer, data engineer, backend developer, a non-tech role
  or two), seniority, location (Copenhagen and elsewhere in the EU, one outside it),
  work mode, work permit and number of vacancies, so the pool's candidates fit some
  and not others. List the stand-ins in `docs/to-record.md`. Store them with
  approved rubrics like the shortlist demo does.
- **Vacancies:** a job has a number of vacancies (default 1), set by the employer in
  the job ad step and shown to candidates on the listing. A schema change (`Job` in
  `src/unapply/schemas/job.py` and the `jobs` table, with a migration): say so in the
  log.
- **Job board** in the candidate app: browse and search the listings (free text over
  title, company and ad; filters for location, work mode and seniority), and read a
  listing in full (the ad and the vacancies, not the rubric).
- **Connect my profile**, one click per job: the only way in. It is task 11's consent
  for that job, recorded with its time, and lets the job match and rank the profile
  anonymously, and the employer reveal it (task 16). It can be withdrawn; withdrawing
  removes the candidate from the job's next ranking (earlier audit entries stay) and
  is refused once they are revealed. Only approved profiles can connect.
- Decisions to check: matching now uses only candidates who connected, except pool
  candidates, who stay connected to every demo job.
- Done when: the board works in the browser for John's demo (search, read, connect,
  withdraw), each job matches the pool sensibly with the baseline scorer, and it is
  tested with pytest, Vitest and Playwright, with screenshots.

### 15. [ ] How well you fit, for candidates

- On the job board and on each listing, the candidate sees how well they fit the
  role: before connecting, a coarse band ("Strong fit", "Good fit", "Partial fit")
  from the baseline scorer on their own levels only (task 12's own rating), plus any
  hard filter they don't meet, named as in the ad ("Work permit: EU required");
  after connecting, their place among the connected candidates ("You're #4 of 37"),
  as M6 in `docs/poc-plan.md` describes. Worked out with the baseline, so it is free;
  nothing is stored for a job the candidate hasn't connected to.
- Decisions to check: rubrics, estimates and claim support stay hidden, so the band
  uses own levels only and never names a criterion, weight or minimum level; the
  place among connected candidates comes from the job's latest ranking.
- Done when: tested on the pool and John's demo across the new jobs (bands at their
  edges, a failed hard filter, the place after connecting), with no rubric or
  assessment detail on any candidate route.

### 16. [ ] Reveal, request application, apply

- The employer's actions on a candidate go in one order, through **one button** on
  each shortlisted card: **Reveal**, then **Request application**, then (waiting),
  then **Applied** or **Declined**. Requesting an application is only possible once
  the candidate is revealed, enforced in the API and not only in the frontend.
- **Reveal**: anyone connected to the job can be revealed; connecting is the
  candidate's consent, so there is no accept step. The employer then sees the
  candidate's name, contact details and the quotes behind each score. No real
  payment: a charge intent is recorded where payment would happen. Still limited by
  the job's `reveal_quota`, and recorded in the audit log.
- Until a candidate is revealed, every employer page hides their quotes: each
  criterion shows its score, reason and how many quotes support it, not the quotes.
- **Request application** and **apply**: the candidate sees the request in their app
  (job, company, the ad) and applies properly by writing or uploading application
  material (a cover letter, a CV; text or files, no model help yet), or declines.
  The employer then sees the application.
- **Counts on each listing**, shown to candidates on the board and the listing, and
  to the employer: connected, revealed, asked to apply and applications, beside the
  vacancies.
- Replaces the task 9 intents for these two actions; keep the existing intents as
  history.
- Done when: the whole flow works end to end in the browser on the demo (connect,
  reveal, request, apply, and a decline), requesting before revealing is refused,
  nothing identifying and no quote reaches the employer before reveal (tested on
  every employer route), and the counts are right at each step.

### 17. [ ] Employer overview dashboard

- A job's overview page: how many candidates connected and were matched, how many
  meet every hard filter (and which filters fail most), the distribution of totals
  and of own and estimated scores, the most and least common skills among
  candidates compared with the rubric's skills, and the funnel from task 16 against
  the vacancies. Aggregates only, no quotes or identities.
- Follow the dataviz skill's conventions for the charts; no paid calls.
- Done when: it works on the pool in the demo, with tests and screenshots.

### 18. [ ] Candidate material and skills

- "Your material": each file under "Your files" can be downloaded (a new API route
  that serves only that candidate's own uploads, checked against path traversal).
- The review's Skills tab lets the candidate add a skill there, with its level and
  why, besides the "Add skills" tab (which can go if the Skills tab covers it).
- Done when: both are tested (API, Vitest, and a Playwright step in John's demo).

### 19. [ ] Candidate profile dashboard

- An overview of the candidate's own profile: skills by area (through the taxonomy)
  with their own levels and how much of their material supports each, how their own
  levels compare with other candidates' own levels (aggregates over at least five
  candidates, otherwise not shown), and tips on what to develop, worked out without a
  model (for example the skills most asked for in rubrics that the candidate lacks,
  and the skills the taxonomy says follow from theirs).
- Decisions to check: estimates and claim support stay hidden, as decided on
  2026-11-26, so nothing here uses or hints at them; "how much material supports
  each" counts their own quotes, not a judgement of them. If a useful dashboard can't
  be made under that rule, block and ask.
- Done when: it works for John's demo, with tests that no assessment word or
  estimate reaches the page, and screenshots.

### 20. [ ] Candidate jobs and success rate

- The jobs a candidate connected to (task 14), each with how far they got (connected,
  revealed, asked to apply, applied) and their fit (task 15), and a success rate
  over all of them (revealed, and asked to apply, out of connected).
- For a job where they weren't revealed: skills that were common among the
  candidates who were revealed and that this candidate lacks or rated lower, from
  own levels only, shown only when at least five were revealed.
- Decisions to check: rubrics stay hidden, so tips never show weights, minimum levels
  or criteria, only skills; never anything about an identifiable other candidate.
- Done when: tested on the pool with demo reveals and requests, including the
  group-size rule.

## After the plan

Create `user/claude` from `dev` and continue there with improvements you're confident
about (tests, polish, documentation, small refactors), logging each in
`docs/progress.md`. When these changes are done feel free to continue developing any 
features you think make sense, keeping them to `user/claude` without merging to `dev`.
