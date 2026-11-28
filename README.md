# unapply

**Apply without applying.** Candidates upload material about themselves once. It is synthesised
into a structured, evidence-backed profile and exposed to employers over MCP. Companies post jobs
as usual, candidates opt in to the ones they want, an agent ranks the opted-in candidates against
the job's rubric, and the company pays to reveal the top *k*. Only then do they ask selected
candidates for real application material.

- **Candidates** are 1 of 20, not 1 of 200, and spend their effort on applications that count.
- **Companies** review a short, explained, anonymised shortlist instead of a pile of LLM-written
  cover letters.
- **Less slop:** LLMs do the matching, people do the writing that matters.

## Core concepts

| Concept | What it is |
| --- | --- |
| **Profile** | A typed record of a candidate: experiences, skills, preferences, dealbreakers. The candidate reviews and approves it. |
| **Evidence** | A snippet from a source (CV, LinkedIn export, GitHub, interview answer). Every claim and estimate points to evidence. |
| **Skill rating** | Each skill has a `self_level` (what the candidate says) and an `estimated_level` (what the evidence supports), plus a confidence. |
| **Claim support** | How well a candidate's self-reports are backed by evidence and agree across sources. Not a judgment of character. |
| **Rubric** | Hard filters, must-haves and nice-to-haves with weights, extracted from a job ad and edited by the recruiter. Hidden from candidates. |
| **Match** | Per-criterion scores with cited evidence, giving a rank within the job. |

## Design principles (EU AI Act / GDPR)

Ranking candidates for jobs is a **high-risk** use under the EU AI Act (Annex III), and profiles
are personal data under GDPR. These principles are product features, not afterthoughts:

1. **The assessment isn't shown to candidates, but it is theirs.** Estimated skill levels and
   claim support stay out of the candidate app, so candidates can't tune their profile to
   them. Candidates are told that their evidence is assessed, and the assessment is part of
   their data: it is provided on a data access request (GDPR art. 15). The job's rubric and
   weights are hidden as well.
2. **Every score is explainable** through cited evidence. "No evidence found" is a valid answer.
3. **A human decides.** The system produces a ranking; a recruiter reveals and contacts people.
4. **Consent is per job.** A candidate opts in to each job and controls which profile sections it can see.
5. **Anonymised until revealed.** This limits bias from names, photos and similar proxies.
6. **Everything is logged** (rubric version, model, scores) so rankings can be audited.

### Privacy notice

Until there is a proper privacy notice, this is it. Once an employer reveals a
candidate, the employer can ask an assistant (a language model, Claude) questions
about them. The assistant answers from that candidate's approved profile, roles and
evidence quotes only, and cites the quotes it rests on. These conversations aren't
saved, so they aren't part of what a candidate can export.

## Status

Early proof of concept. See [docs/poc-plan.md](docs/poc-plan.md).

See [CONTRIBUTING.md](CONTRIBUTING.md) for conventions and the Git workflow.

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Node.js](https://nodejs.org/) 26 or newer, for the frontend only
- VS Code (recommended). Accept the recommended extensions when prompted.

## Getting started

```bash
uv sync
uv run pytest
```

To call the Claude API, copy `.env.example` to `.env` and add your key. `.env` is
gitignored; variables already set in your environment take precedence over it.

**Paid API calls are off by default.** A command that would call Claude stops with a
message unless you add `--allow-api` to it (or set `UNAPPLY_ALLOW_API_CALLS=1`), and
the app has a toggle that starts off in every session. Tests always run with calls
off, except the opt-in live test. Every real call is logged with its estimated cost
in `data/api_calls.jsonl`. Use `--record` once and `--replay` after that to work
without calling the API.

## The frontend

The web app for candidates and employers lives in `frontend/` (Vite, React,
TypeScript, Tailwind CSS and shadcn/ui) and talks to the API (below). Run both:

```bash
uv run unapply api            # in one terminal
cd frontend
npm install                   # once
npm run dev                   # http://localhost:5173
```

- **Candidates:** upload and download material (drag and drop), review the draft
  profile (edit experience, rate skills with level chips and add missing ones with a
  level and where they were used, in the same Skills tab, set preferences, approve),
  answer a few questions, and see the profile as employers will. The assessment is
  never shown. Then the **job board**: browse and search the jobs (free text over
  title, company and ad; filters for location, work mode, seniority and their own
  fit band or the jobs whose requirements they don't meet, and under Advanced work
  permit, vacancies and the skills an ad names; every pill on a card adds its
  filter as a removable chip; newest or best fit first), read a
  listing in full (the ad and its vacancies, never the rubric), and **connect my
  profile** to a job with one click, from its card on the board or the listing. Connecting is the candidate's consent for that
  job, recorded with its time: only connected candidates are matched and ranked.
  It can be withdrawn, which takes the candidate out of the job's next ranking,
  until the employer reveals them. Each listing shows how many connected, were
  revealed, were asked to apply and applied. When an employer asks them to apply,
  the request shows on the board and the listing, and the candidate applies with a
  cover letter, files or both, or declines. Once an employer reveals them, the two
  can **message** each other on the listing: one thread per job, newest at the
  bottom, with unread counts on the board's cards (no email or push
  notifications). On their profile, candidates give the
  name and contact details an employer sees only once they reveal them. Their
  **dashboard** sums up their own profile: skills by area (the taxonomy's
  categories) with their own levels and how many quotes from their material
  mention each, how their own levels compare with other candidates' own levels
  (only over at least five of them), and skills to develop: those the jobs on the
  board ask for most that they don't list, and those that follow from theirs in the
  taxonomy. A second sheet lists the jobs they connected to, each with how far they
  got and their fit, and their success rate (revealed, and asked to apply, out of
  connected). A third compares them on each job with the others it revealed, asked
  to apply, or who applied, whatever their own stage, once a group has at least
  five others: a spider chart of their own levels against the group's median, the
  skills where they stand out (rated higher than most, or listed by few of them)
  and those where the group is ahead. Own levels only; never anything from the
  assessment or a rubric.
- **Employers:** paste a job ad and set its vacancies (shown on the job board),
  draft a rubric from it, and edit and approve the
  hard filters and weighted criteria. Any change makes a new version. Then the
  **shortlist**: match the candidates with either scorer and see them ranked and
  anonymised (an alias such as "Cobalt Otter" and an abstract, mirrored-pattern
  avatar, both from the profile id and the job's id together, unique within the job
  and different on every other job, so two employers can't link them; never a name
  or a photo), with a score per
  criterion, its reason and how many quotes support it, and the hard filter
  outcomes. A **spider chart** compares up to three candidates on the rubric's
  skills, with estimated levels, own levels or both, and a table of every value.
  **One button** on each card steps through **Reveal** (the candidate's name,
  contact details and the quotes behind each score; no payment is taken, a charge
  intent is recorded; limited to the job's reveal quota, 10), then **Request
  application**, then waits, then shows **Applied** with the application (letter
  and files to download) or **Declined**. A revealed candidate's card has
  **Messages**, a thread with them, and counts their unread messages, and **Ask**:
  questions in plain language, answered by a model from that candidate's own
  material only, with the quotes cited, and saying when the material doesn't answer
  (not saved; demo candidates have suggested questions that replay for free). Until a
  reveal, no quotes and no role
  summaries are shown. The job's counts sit above the list, beside its vacancies.
  The **overview** sums up the job's candidates in aggregate, never one of them:
  how many connected, were matched and meet every hard filter (and which filters
  fail most), histograms of the totals and of the own and estimated scores with
  their medians, the rubric's skills and other common skills among candidates,
  and how far candidates got against the vacancies.
- **Demos:** "Try the John Doe demo", "Try the Fjord Grocery demo" and "Try the
  shortlist demo" (Fjord Grocery with its rubric approved and the 12 synthetic
  candidates of `tests/fixtures/pool`) replay recorded answers, so they cost
  nothing. On the job board, "Add the demo jobs" posts eleven invented jobs
  (`tests/fixtures/jobs`, listed in `board.yaml`) with the pool connected to each. A real candidate or job needs paid model calls,
  which the frontend never asks for: they work only if the API runs with
  `UNAPPLY_ALLOW_API_CALLS=1`.

Requests to `/api` go to the API at `UNAPPLY_API_URL` (by default
`http://127.0.0.1:8000`). Checks, from `frontend/`:

| Command | What it does |
|---|---|
| `npm run lint` | Lint (oxlint) |
| `npm run build` | Type-check and build into `dist/` |
| `npm test` | Component tests (Vitest, Testing Library) |
| `npm run e2e` | The demos end to end in Chromium (Playwright). Starts the API and the dev server on ports 8766 and 5174 with an empty data folder in the temporary folder, stops them afterwards, and saves screenshots in `e2e/screenshots/`. Needs `npx playwright install chromium` once |

Screenshots of the demos are in [docs/screenshots/](docs/screenshots/).

## The Streamlit app (internal)

The Streamlit app is kept as the internal developer tool, with workspace folders
instead of the database:

```bash
uv run unapply app
```

Opens the app in your browser, with two sides switched in the sidebar:

- **Candidate:** upload material, review the extracted profile, answer follow-up
  questions and see the result. The assessment runs in the background and is never
  shown to candidates; **Developer view** adds an internal Assessment page.
- **Employer:** paste a job ad, extract a rubric (hard filters and weighted criteria,
  each quoting the ad), edit and approve it. Candidates never see rubrics.

Candidates are kept in `data/<name>/` and jobs in `data/jobs/<name>/`, each with a
copy after every step. Paid API calls stay off until you turn on the toggle in the
sidebar, and the **Demo** buttons (John Doe, Fjord Grocery) run everything for free
with recorded answers.

## The database

Candidates, jobs, rubric versions and matches can also be kept in a database, which
the API (below) works on. It is a SQLite file, `data/unapply.db`, unless
`UNAPPLY_DATABASE_URL` in `.env` points elsewhere; the same tables work on Postgres
(`uv sync --extra db` and a `postgresql+psycopg://` URL).

```bash
uv run unapply db init                                 # create or migrate the tables
uv run unapply db import data/me data/jobs/acme        # copy workspace folders in
```

`db init` also loads the skill taxonomy (below) into the database.

Importing a workspace brings its settings, history, current profile or job (every
rubric version in its history), and waiting interview questions. Uploaded material
stays in the folder. A rubric version that a match refers to can't be changed: edit
the rubric and it gets a new version.

## The API

`unapply api` serves the same steps over HTTP, on the database, for the frontend:

```bash
uv run unapply api            # http://127.0.0.1:8000, interactive docs at /docs
```

- **Candidates** (`/candidates`): create, upload material (PDF, Markdown, text,
  LaTeX, YAML, JSON or a zipped LinkedIn export; up to 20 MB a file), download
  their own uploads (`/candidates/<name>/material/<file>`, only files directly in
  that candidate's folder; any path in the name is refused, 404), extract a
  draft profile, read and save the review form, prepare and answer questions, and
  read the profile. Candidate routes never return the assessment.
- **Jobs** (`/jobs`): create with the ad, extract a rubric, read any version and
  save the recruiter's edit (any change raises the version).
- **Job board** (`/board`, `/board/<job>`, `/candidates/<name>/connections`):
  search the listings (jobs with an approved rubric) by words, location, work mode
  and seniority, by work permit (`work_permit=`, jobs asking for none or only for
  permits it covers, so `DK` covers `EU`), at least so many vacancies
  (`min_vacancies=`) and skills the ad names (`skill=`, repeatable, every one
  needed; through the taxonomy, so synonyms match, never a rubric criterion), and
  with `candidate=<name>` by their fit (`fit=strong|good|partial|low`,
  or `not_met` for jobs with a hard filter they miss) and best fit first
  (`sort=fit`, ties newest first), read one (the ad, vacancies, work permits and
  the skills the ad names, never the rubric), and connect an
  approved profile to a job (`PUT`), list the connections with how far each got
  and withdraw (`DELETE`, refused once the employer revealed the candidate). Each
  listing has its counts: connected, revealed, asked to apply, applied.
- **Fit** (`/candidates/<name>/fit`, `/candidates/<name>/fit/<job>`): how well the
  candidate fits each job on the board: a band ("Strong", "Good", "Partial" or "Low
  fit") from the baseline on their own levels only, the hard filters they don't meet
  as the ad names them ("Work permit: EU required"), and once connected their place
  in the job's latest ranking ("You're #4 of 37"). Never a score, criterion, weight
  or minimum level; free, and nothing is stored.
- **Matching** (`/jobs/<name>/match`, `/jobs/<name>/ranking`): match every
  candidate connected to a job, with an approved profile, against its approved
  rubric, with the baseline or the LLM scorer, and read the anonymised ranking
  (profile ids, never names). A candidate who withdrew isn't in the next ranking.
- **Shortlist** (`/jobs/<name>/shortlist`): the ranking with each candidate
  anonymised (an alias, their roles with names and contact details removed, their
  own and estimated levels in the rubric's skills, and the baseline's totals on own
  and on estimated levels only), how far each got, and the job's counts. Quotes and
  role summaries only once revealed, with the candidate's name and contact details.
  `/jobs/<name>/intents` lists the early reveal and application requests, which
  only recorded intent, as history.
- **Overview** (`/jobs/<name>/overview?scorer=`): the job's candidates in
  aggregate on the current rubric version, from stored matches: counts per hard
  filter, scores per tenth with medians, skill counts and the job's counts. No
  quote, name, alias or profile id; nothing is recorded and no model is called.
- **Dashboard** (`/candidates/<name>/dashboard`): the candidate's own profile in
  overview, from the profile without the assessment: skills by area with own levels
  and counts of quotes from documents and of their own statements; other
  candidates' own levels per skill (counts per level and the median), only where at
  least five rated it (the synthetic pool for a demo candidate, other real
  candidates with approved profiles otherwise); and tips naming skills only. No
  model is called.
- **Candidate's jobs** (`/candidates/<name>/jobs`): the jobs a candidate is
  connected to, newest first, each with its stage and fit, and the success rate.
  Each job has a comparison with every group of others on it (revealed, asked to
  apply, applied) that has at least five, whatever the candidate's own stage: the
  group's median own level in the skills it lists most (where at least five rated
  it) next to the candidate's, the skills they rated higher or that at most a fifth
  of the group list, and those at least half list that they lack or rated lower.
  Own levels only; no model is called and nothing is stored.
- **Hiring** (`/jobs/<name>/candidates/<profile id>/reveal`,
  `.../request-application`, `.../files/<id>`; `/candidates/<name>/applications/<job>`,
  `.../decline`, `/candidates/<name>/contact`): reveal a connected candidate (quota,
  charge intent, audit log entry), ask a revealed one to apply (refused before a
  reveal), apply with a letter and files (PDF, Word, Markdown, text; up to 5 of 10
  MB, kept in the database) or decline, download application files, and the
  candidate's contact details (from the CV for demo candidates).
- **Messages** (`/jobs/<name>/candidates/<profile id>/messages`,
  `/candidates/<name>/messages`, `/candidates/<name>/messages/<job>`, each thread
  with `.../read`): a thread per revealed candidate and job, oldest first. Before a
  reveal there is no thread: reading one gives 404 and writing one 409. Messages are
  up to 5,000 characters, and are marked read when the app shows them; the
  shortlist and the candidate's connections count those unread. A candidate's
  `GET /candidates/<name>/messages` lists every thread in full: their export.
- **Ask** (`/jobs/<name>/candidates/<profile id>/ask`): `POST` a question (and the
  conversation so far) about a revealed candidate; a model answers from their own
  material only, citing their quotes, checked to be theirs. One paid call per
  question, refused (403) unless allowed; refused (409) before a reveal. `GET` lists
  the free demo questions (pool candidates only; 404 before a reveal). Nothing is
  stored.
- **Demos** (`/demos/candidate`, `/demos/job`, `/demos/shortlist`, `/demos/board`):
  John Doe, Fjord Grocery, Fjord Grocery with the synthetic pool, and the eleven
  demo jobs on the board, which replay recorded answers for free. The pool's
  candidates are stored once, aren't listed under `/candidates`, and count as
  connected to every demo job. Only Fjord Grocery has the pool's recorded LLM
  scorer answers; the other board jobs are matched with the baseline (the LLM
  scorer is refused on them, 409).

**Paid model calls are refused** (403) unless the request adds `?allow_api=true` or
`UNAPPLY_ALLOW_API_CALLS=1` is set, just like `--allow-api`. `unapply api --internal`
adds `/internal/candidates/<name>/assessment` and `.../estimate`, for developers and
data access requests; never run a server candidates use with it. Uploaded material
goes in `data/uploads/<name>/`.

## The skill taxonomy

`config/skills.yaml` gives every skill one canonical name, with its synonyms
("radiation therapy planning" and "radiotherapy planning", "sklearn" and
"scikit-learn") and how it relates to others: **implies** ("dbt" implies "sql") and
**broader** ("lightgbm" is a kind of "gradient boosting"). Skill names are mapped to
their canonical name when a profile is extracted, when the candidate reviews it and
when a rubric is extracted or edited, so synonyms merge into one skill. Names it
doesn't know are kept as written, lowercased. Relations are for matching: evidence
for a specific skill also counts for the general one. To use another file, set
`UNAPPLY_SKILLS` to its path.

## Matching

`unapply match <job>` matches the candidates connected to a job and ranks them.
Only candidates who connected their approved profile to the job (on the job board,
or `unapply consent grant`) are matched, and only against an approved rubric;
matching locks that rubric version. Synthetic pool candidates count as connected to
every demo job.

```bash
uv run unapply match fjord-grocery-demo                    # the baseline: free
uv run unapply match fjord-grocery-demo --scorer llm --allow-api   # one paid call per candidate
```

1. **Hard filters**, in plain code: work mode, location (skipped when both sides
   accept remote work), work permit ("EU" and EU member states cover each other)
   and minimum years of work, from experience dates at month precision with
   overlapping roles counted once and education left out. A filter the profile
   says nothing about is "unknown" and doesn't exclude anyone. Candidates who fail
   one are still scored, so the employer sees how close they are, but rank after
   everyone who passes, whatever their score.
2. **Scores per criterion**, from 0 to 1, each with a reason and cited evidence:
   - `baseline` (default): no model. The candidate's level (the estimate and their
     own level, weighted by the estimate's confidence) against the criterion's
     minimum level, times a factor for how many document quotes back it. Evidence
     for a related skill counts through the taxonomy ("dbt" for "sql"), for less.
     Criteria that name no skill aren't scored. The shortlist also shows the
     baseline on the candidate's own levels only ("Own rating") and on the
     estimated levels only ("Estimated from evidence") beside the total, which
     still sets the rank.
   - `llm`: one model call per candidate, which sees the criteria and the
     anonymised profile (names, email addresses, phone numbers and links removed)
     but never the hard filters. Cited evidence must be the candidate's.
3. **Ranking** by `Match.total`, the weighted mean of the criterion scores.

4. **Audit log**: every match and every ranking is recorded in the append-only
   `audit_log` table, with the rubric version and a hash of it, the scorer and
   model, the scores, the hard filter outcomes, a hash of each profile scored (its
   version) and the time. A ranking entry keeps the rubric and every ranked match in
   full, so it can be ranked again from the log alone. Rankings read back through
   the API's `/ranking` route are recorded too. `unapply audit <job>` lists a job's
   rankings and checks that each one reproduces and agrees with its match entries.
   Each reveal is recorded too, with the profile revealed, a hash of it and where
   payment would have been taken.

`--replay` and `--record` take a folder with one `<candidate>.json` each, or a file
for one candidate. John Doe against Fjord Grocery: 0.81 with the baseline, 0.71 with
the LLM scorer's stand-in answer (not yet a real recording; see
[docs/to-record.md](docs/to-record.md)).

## Evaluation

`unapply evaluate` ranks a pool of synthetic candidates with each scorer and compares
the ranking with a reference ranking: the share of the reference's top k the ranking
also puts in its top k, and Kendall's tau-b over every pair (1 the same order, 0
unrelated, -1 reversed; shared ranks allowed). The default pool,
[`tests/fixtures/pool/`](tests/fixtures/pool/README.md), has 12 fictional candidates
for Fjord Grocery with an intended ranking, from a clear fit to unsuitable. It runs
offline on hand-written stand-in answers and stores nothing.

```bash
uv run unapply evaluate                            # both scorers, top-3 and top-5
uv run unapply evaluate --reference shortlist.yaml # a human shortlist instead
uv run unapply evaluate --reference anna.yaml --reference ben.yaml  # several people
```

With several references, each scorer is compared with each of them and with their
mean, and the command first prints how much the references agree with each other
(the mean over every pair): the ceiling from the key experiment, since a scorer that
agrees with each person about as much as they agree with each other does as well as
one of them. Each scorer still ranks the pool once.

`--job` compares a real job's ranking instead: the latest one in the audit log, as
its employer saw it (or one picked with `--ranking <id>`, as `unapply audit` lists
them). Each reference names candidates as they are in the database, and is needed,
since a job has no intended ranking. Nothing is scored again or stored, so no model
is called.

```bash
uv run unapply evaluate --job fjord --reference anna.yaml --reference ben.yaml
```

On the pool, the baseline gets top-3 overlap 1.00, top-5 0.80 and tau 0.82: it
trusts a candidate's own levels where the estimates are unsure, so the overclaimer
comes 4th instead of 8th. The LLM scorer's stand-ins agree with the intended ranking
(tau 0.98: the reference has the three who fail a hard filter share the last place,
while the ranking orders them by score), which only shows they are consistent until
they are recorded.

## The MCP server

A job's matching agent reads candidates over MCP, and only candidates who opted in
to that job, with an approved profile. A candidate's consent (`unapply.consent`, the
`consents` table) names the sections the job's agent may read: experiences (with the
headline), skills, evidence and preferences. Each is one tool; the others refuse.
Consent is read on every call, so withdrawing takes effect at once, and it stays
when the profile is extracted again.

```bash
uv run unapply consent grant john-doe acme                      # share everything
uv run unapply consent grant john-doe acme --sections skills evidence
uv run unapply consent list acme
uv run unapply consent withdraw john-doe acme
uv run unapply mcp acme                                         # serve over stdio
```

The tools, all read-only: `get_rubric`, `list_candidates` (profile id, alias such as
"Cobalt Otter", as on that job's shortlist, and what each shared), `get_experiences`, `get_skills` (own and
estimated levels with the estimate's confidence), `search_evidence(query)` (quotes
cited for the skill the query names, or one that counts towards it through the
taxonomy, first; then quotes with more of its words) and `get_preferences`. Texts go
through the same redaction as the shortlist, and no tool gives the candidate's name,
contact details, file names or claim support. An unknown id and a candidate who
didn't opt in get the same answer. The server's instructions to the agent are in
`src/unapply/mcp_server/instructions.md`.

## Common commands

| Command | What it does |
|---|---|
| `uv sync` | Create or update `.venv/` from `uv.lock` |
| `uv sync --all-extras` | Also install the optional extras (Postgres drivers) |
| `uv run pytest` | Run the tests |
| `uv run ruff check .` | Lint. Add `--fix` to fix what can be fixed automatically |
| `uv run ruff format .` | Format |
| `uv add <package>` | Add a runtime dependency. Use `uv add --dev <package>` for a local-only tool |
| `uv run unapply ingest data/me/ --github <user> --out data/me/profile.json` | Extract a draft profile (calls the Claude API; needs `ANTHROPIC_API_KEY` in `.env`) |
| `uv run unapply ingest ... --record answer.json` / `--replay answer.json` | Save the model's answer, or reuse a saved one without calling the API |
| `uv run unapply ingest data/me/ --exclude old_cv.pdf --exclude "drafts/*" ...` | Leave files out. In a folder, README files and JSON or YAML schemas are always left out (they describe the folder, not you); every skipped file is listed with the reason |
| `uv run unapply job extract ad.md --out data/jobs/acme.json` | Extract a rubric from a job ad (calls the Claude API: add `--allow-api`) |
| `uv run unapply job export data/jobs/acme.json --sheet data/jobs/acme.yaml` | Write a rubric sheet to edit and approve |
| `uv run unapply job apply data/jobs/acme.json data/jobs/acme.yaml --out data/jobs/acme.json` | Apply the edited rubric sheet |
| `uv run unapply api` | Start the HTTP API over the database (docs at http://127.0.0.1:8000/docs) |
| `uv run unapply db init` | Create the database's tables, or migrate them to the newest version, and load the skill taxonomy |
| `uv run unapply db import data/me data/jobs/acme` | Import candidate and job workspace folders into the database |
| `uv run unapply match acme` | Match the candidates connected to a job and rank them (`--scorer llm` calls the Claude API: add `--allow-api`) |
| `uv run unapply consent grant john-doe acme [--sections ...]` | Opt a candidate in to a job, choosing what its agent may read (`withdraw`, `list` too) |
| `uv run unapply mcp acme` | Serve a job's matching agent over MCP (stdio), scoped to the candidates who opted in |
| `uv run unapply audit acme` | List a job's rankings from the audit log and check that each reproduces |
| `uv run unapply ask astrid-holm production --replay tests/fixtures/pool/astrid-holm/ask_production.json` | Ask a demo question about a pool candidate, as an employer does after a reveal (`--allow-api --record FILE` records a real answer) |
| `uv run unapply evaluate` | Rank the synthetic pool with both scorers and compare with its intended ranking (`--reference FILE` for another; repeat it for several people and their agreement; `--job NAME` for a job's stored ranking) |
| `uv run unapply review export data/me/profile.json --sheet data/me/review.yaml` | Write a review sheet: set your levels, remove or add skills, approve |
| `uv run unapply review apply data/me/profile.json data/me/review.yaml --out data/me/profile.reviewed.json` | Apply the edited sheet |
| `uv run unapply estimate data/me/profile.reviewed.json --out data/me/profile.estimated.json` | Estimate skills without an estimate from their evidence, and check claim support (calls the Claude API; `--all` redoes every skill) |
| `uv run unapply interview export data/me/profile.estimated.json --sheet data/me/interview.yaml` | Write follow-up questions about skills the documents don't show enough of (Sonnet 5.5) |
| `uv run unapply interview apply data/me/profile.estimated.json data/me/interview.yaml --out data/me/profile.interviewed.json` | Add the answers as your own statements; then run `estimate` again |

## Layout

| Path | Contents |
|---|---|
| `src/unapply/` | The Python package |
| `src/unapply/schemas/` | Pydantic schemas: profiles, evidence, skills, jobs, rubrics, matches |
| `src/unapply/ingest/` | Loading material (PDF, text, LinkedIn export, GitHub) and extracting a profile |
| `src/unapply/llm.py` | The one place that calls a language model |
| `src/unapply/estimation/` | Skill estimation from evidence, and claim support |
| `src/unapply/interview/` | Follow-up questions (rules choose, a model words them) and the answer sheet |
| `src/unapply/app/` | The internal developer app (Streamlit): `candidate.py`, `employer.py`, shared helpers and the demos |
| `src/unapply/jobs/` | Job ads to rubrics, the recruiter's rubric sheet, the job board (listings, search, connecting), the candidate's fit, hiring (reveal, request, apply), messages after a reveal, the candidate's outcomes, and asking a model about a revealed candidate |
| `src/unapply/workspace.py` | A candidate's folder: material, current profile, history |
| `src/unapply/db/` | The database: SQLAlchemy tables, Alembic migrations, a repository that saves and loads the schemas, and the workspace import |
| `src/unapply/api/` | The HTTP API (FastAPI): candidate, job, matching, demo and internal routes |
| `src/unapply/matching/` | Matching: hard filters, the baseline and LLM scorers, anonymisation and ranking |
| `src/unapply/mcp_server/` | The MCP server for a job's matching agent: consent-scoped, anonymised reads, and its instructions |
| `src/unapply/consent.py` | A candidate's consent to one job: which profile sections its agent may read |
| `src/unapply/evaluation/` | Evaluation: top-k overlap, Kendall's tau, and the synthetic candidate pool |
| `src/unapply/taxonomy.py` | The skill taxonomy: canonical names, synonyms, implied and broader skills |
| `src/unapply/review.py` | The candidate's review sheet: levels, corrections, additions, approval |
| `frontend/` | The web app (React): `src/pages/` for the candidate and employer steps, `src/components/` for shared parts, `src/lib/` for the API client and types, `e2e/` for the Playwright tests |
| `config/` | Configuration, such as the skill taxonomy (`skills.yaml`) |
| `docs/` | Plans and design notes |
| `tests/` | Tests for the package |
| `tests/fixtures/` | Synthetic test data, including John Doe, a made-up candidate run end to end, and a pool of 12 candidates for evaluation (see their READMEs) |
| `data/` | Local uploads and real personal data, gitignored |
| `scratch/` | Personal exploration, gitignored |
| `pyproject.toml` | Python project, dependencies, and Ruff and pytest settings |
| `AGENTS.md` | Instructions for AI coding agents (`CLAUDE.md` points to it) |
