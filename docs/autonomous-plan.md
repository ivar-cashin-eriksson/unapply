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

### 1. [ ] CI on GitHub

- `.github/workflows/ci.yml`: on push and pull request, set up uv and Python 3.12, run
  `ruff check`, `ruff format --check` and `pytest`. Later tasks add the frontend checks.
- Done when: the workflow file is valid and every check it runs passes locally. (Its
  first run on GitHub happens on push; note in the log if it fails there.)

### 2. [ ] Database (SQLite now, Postgres later)

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

### 3. [ ] Skill taxonomy

- `config/skills.yaml`: canonical skills with synonyms ("radiation therapy planning"
  → "radiotherapy planning", "scikit learn" → "scikit-learn") and relations: implies
  ("dbt" → "sql", "pytorch" → "deep learning") and broader ("lightgbm" → "gradient
  boosting"). Loaded into the taxonomy tables.
- Canonicalise skill names at extraction, review and rubric time through it.
- Done when: tests show synonyms merge, implied skills are found, and existing
  fixtures still pass.

### 4. [ ] API (FastAPI)

- `src/unapply/api/`: endpoints over the database for candidates (create, upload
  material, extract, review, questions, answers, profile), jobs (create, ad, extract
  rubric, edit rubric) and, after task 5, matching. The candidate profile endpoints
  return `candidate_view` (no assessment); assessment endpoints are internal only.
- Paid model calls are refused unless the request is explicitly allowed, exactly like
  `--allow-api`; demo candidates and jobs replay recordings.
- `unapply api` starts it (uvicorn). OpenAPI docs at `/docs`.
- Done when: tests with FastAPI's TestClient cover each endpoint, including refusal of
  paid calls and the hidden assessment.

### 5. [ ] Matching (M4)

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

### 6. [ ] Ranking audit log

- Every match and ranking records rubric version, profile version (hash), scorer and
  model, scores and time, in an append-only audit table.
- Done when: a ranking can be reproduced from the log, and a test checks it.

### 7. [ ] Synthetic candidate pool and evaluation script

- 12 fictional candidates for Fjord Grocery, from a clear fit to unsuitable, each with
  a short CV, an approved profile (with hand-written stand-in extraction and
  estimation, evidence quoting the CV verbatim) and an **intended rank** with reasons.
  Vary the tricky cases: overclaimers, strong but outside the EU, too junior, a great
  fit using synonyms, a career changer.
- `unapply evaluate`: top-k overlap and Kendall's tau of a ranking against a reference
  ranking (intended now, human shortlists later), for both scorers.
- Done when: the evaluation runs offline on the pool and the results are in the log.

### 8. [ ] New frontend (React)

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

### 9. [ ] Employer views (M5)

- In the new frontend: an anonymised, ranked shortlist with per-criterion
  explanations and cited evidence; a spider chart comparing selected candidates on the
  rubric's skills, toggling own and estimated levels; "Reveal" and "Request
  application" buttons that record intent (no payment).
- Done when: the views work on the synthetic pool in the demo, with tests and
  screenshots.

### 10. [ ] Smaller fixes

- Dates: store whether a date is year or month precision, and show it that way.
- Ingestion: skip files that describe a schema rather than the candidate (such as a
  README in a profile folder), or let the candidate exclude files.
- Streamlit review table: show full evidence in a detail view.
- Done when: each is tested.

### 11. [ ] MCP server

- Consent-scoped tools over the database for a job's matching agent:
  `get_experiences`, `get_skills`, `search_evidence(query)`, `get_preferences`, only
  for candidates who opted in to that job, never their name or contact details.
- Done when: tested with the MCP SDK's in-process client.

## After the plan

Create `user/claude` from `dev` and continue there with improvements you're confident
about (tests, polish, documentation, small refactors), logging each in
`docs/progress.md`. When these changes are done feel free to continue developing any 
features you think make sense, keeping them to `user/claude` without merging to `dev`.
