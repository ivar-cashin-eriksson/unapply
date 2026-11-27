# Progress log

One line per finished or blocked task from `docs/autonomous-plan.md`: date, task,
branch, what was done, what was tested, anything to know.

## Log

- 2026-11-26 · Plan written (`docs/autonomous-plan.md`). Node.js v26.13.1 installed per
  user (portable, checksum-verified) because the admin install was cancelled.
- 2026-11-26 · Task 1, CI on GitHub · `chore/ci` · Added `.github/workflows/ci.yml`
  (push and pull request; checkout@v7, setup-uv@v7 with Python 3.12 and cache;
  `uv sync --locked --all-extras`, ruff check, ruff format --check, pytest). Checked
  the action tags exist, the YAML parses, `uv lock --check` and the sync dry-run are
  clean, and ruff and the 76 tests pass locally. Noted CI in CONTRIBUTING.md. First
  GitHub run happens on this push; not checked here (no `gh` CLI in this shell).
- 2026-11-26 · Task 2, Database · `feat/database` · Added `src/unapply/db/`:
  SQLAlchemy 2.0 tables (candidates with their current profile, sources, evidence,
  experiences, candidate skills with own level and estimate, claim support, interview
  questions and answers, candidate and job history, jobs, rubric versions, criteria,
  matches, criterion scores), an Alembic migration `0001`, a `Repository` that saves
  and loads `Profile`, `Job`, `Rubric` and `Match` by workspace-style names, and
  `unapply db init` / `unapply db import <workspace>...`. `UNAPPLY_DATABASE_URL`,
  default `sqlite:///data/unapply.db` (follows `UNAPPLY_DATA`; tests point it at a
  temporary file). Tested (20 new tests, 96 in all): John Doe's profile at every step
  (extracted to re-estimated) and Fjord Grocery's job at every rubric version load
  back equal; migrations build from empty, match the models (`compare_metadata`),
  downgrade and render for Postgres offline; a matched rubric version can't change;
  import of candidate and job workspaces, and a broken one imports nothing. To know:
  SQLAlchemy and Alembic are now core dependencies (the `db` extra only adds the
  Postgres drivers); the taxonomy and audit tables come with tasks 3 and 6 as their
  own migrations; lists of ids are JSON columns, not link tables; matches keep
  `job_id`/`profile_id` as plain ids so a replaced profile doesn't remove them. The
  Streamlit app still uses workspace folders. Not tested against a real Postgres.
- 2026-11-26 · Task 3, Skill taxonomy · `feat/skill-taxonomy` · Added
  `config/skills.yaml` (86 canonical skills with synonyms, `implies` and `broader`
  relations) and `src/unapply/taxonomy.py` (`Taxonomy`, `canonical_skill`,
  `implied`, `supporting`; checked on load for clashing names, unknown or
  non-canonical relation targets and cycles; `UNAPPLY_SKILLS` points to another
  file). `canonical_skill` moved there from `ingest/extract.py` and now maps synonyms
  at extraction, in the review sheet (rows still match by the name they were written
  with; skills that become one are merged, keeping all evidence and the higher own
  level, and lose their estimate so they are estimated again) and in rubric
  extraction and the rubric sheet. New tables `taxonomy_skills`, `skill_synonyms`,
  `skill_relations` (migration `0002`, a schema change to the database; the Pydantic
  schemas are unchanged), `Repository.save_taxonomy` / `taxonomy`, and
  `unapply db init` now loads the taxonomy. Tested (32 new tests, 128 in all):
  synonyms merge at extraction, review and rubric time, implied and supporting skills
  are found transitively, invalid taxonomies are refused, the taxonomy round-trips
  through the database, and no skill name in the John Doe or Fjord Grocery
  recordings is renamed, so their expected results hold. To know: YAML rather than
  JSON for this config because it is edited by hand (CONTRIBUTING updated); the
  relations aren't used by estimation yet, only offered for matching (task 5). Found
  but not fixed (outside this task): a profile with no experiences exports a review
  sheet with an empty `experiences:` that fails to apply ("Input should be a valid
  list").
- 2026-11-26 · Task 4, API · `feat/api` · Added `src/unapply/api/` (FastAPI over
  the database): candidates (create, settings, upload/list/remove material, extract,
  review form read and save, prepare/discard questions, answers, profile), jobs
  (create, ad, extract rubric, current and earlier rubric versions, edit and
  approve), demos (`/demos/candidate`, `/demos/job`, plus John's filled-in review and
  answers) and `/health`. `unapply api [--host] [--port] [--internal]` starts it with
  uvicorn; OpenAPI docs at `/docs`. Paid calls are refused with 403 unless
  `?allow_api=true` or the switch is on, checked before any work so a refused request
  changes nothing; demos replay recordings. Candidate routes return the profile
  without estimates or claim support, and questions only give their neutral reason;
  the assessment is only on `/internal/...`, added with `--internal`. Package errors
  map to status codes (404 unknown, 409 wrong step or locked rubric, 422 invalid
  review/rubric/answers, 502 model errors). Tested (25 new tests, 153 in all) with
  TestClient: every route, John Doe's demo journey end to end, refusal of paid calls
  (with a fake factory, and with the real one never creating a client), the switch,
  no assessment words in any candidate response, internal routes absent by default,
  upload checks (type, size, paths in names), a matched rubric not replaced, and the
  CLI command. To know: FastAPI, uvicorn and python-multipart are now core
  dependencies (the `api` extra is gone) and httpx a dev one; uploads go in
  `data/uploads/<name>/`; the Streamlit app still uses workspace folders; there is no
  auth (out of scope for the POC), so `--internal` must never face candidates.
  Matching routes come with task 5. Left running, not by Ivar: an `unapply api --port 8765`
  server from an earlier session of this task (started 19:16); stopping it was
  refused by the permission check, so it still holds `.venv/Scripts/unapply.exe` and
  makes `uv run` fail to reinstall the package (`uv run --no-sync` works). Please stop
  it. A headless Streamlit on port 8599 (since 16:14) was left alone too.
- 2026-11-26 · Task 5, Matching (M4) · `feat/matching` · Added
  `src/unapply/matching/`: hard filters in plain code (`filters.py`: work mode,
  location, work permit with "EU" and member states, minimum years from experience
  dates at month precision with overlapping roles counted once; pass, fail or
  "unknown" when the profile doesn't say, which doesn't exclude), a deterministic
  `BaselineScorer` (level blended from own and estimated by confidence, against
  `min_level` or WORKING, times an evidence factor; related skills through the
  taxonomy at 0.75), an `LLMScorer` with its prompt (one call per candidate on the
  anonymised profile; `anonymise.redact` removes emails, phone numbers, links,
  @handles and known names; source paths and hard filters are never sent; cited
  evidence ids checked to be the candidate's), `match_candidate`, `rank` (ties
  share a rank) and `latest`, and `run.match_job` over the database.
  `unapply match <job> [--scorer baseline|llm] [--candidates ...] [--today]` and
  the API's `POST /jobs/<name>/match` and `GET /jobs/<name>/ranking` (anonymised:
  profile ids, no names). Hand-written stand-in for the LLM scorer:
  `tests/fixtures/jobs/fjord_grocery/match_john_doe.json`, in `docs/to-record.md`.
  Tested (65 new tests, 218 in all): filters at their edges (47 vs 48 months,
  overlaps, education and personal projects skipped, current roles, remote, permit
  matrix, unknowns), the baseline on John against Fjord Grocery (total 0.81:
  Python, forecasting, A/B testing 1.0; SQL 0.46; Spark and deep learning 0.31) and
  on synonyms, related skills and statement-only evidence, the LLM scorer's stand-in
  (total 0.71) and its answer checks, that no name, email, phone or link reaches the
  model, ranking ties, the CLI (both scorers, refused paid calls saving nothing,
  unapproved rubrics and profiles) and the API (demos free with both scorers, a real
  candidate or a real job needs `allow_api`, ranking read back, rubric locked).
  Decisions to check (conservative, small): only approved profiles and approved
  rubrics are matched, since matching locks the rubric version; missing
  information is "unknown", not a failure; candidates failing a filter aren't
  scored (not even by the free baseline); criteria without a skill aren't scored by
  the baseline and `Match.total` averages over the rest; a member state's permit
  meets a job's "EU". To know: filter outcomes aren't stored with the match (no
  schema change; the API works them out again; task 6's audit log could keep
  them); education is recognised by title words, as `Experience` has no kind; the
  real candidate name isn't stored anywhere, so only contact patterns and the
  GitHub username are redacted. Scoring over MCP is left for task 11. The API
  server from task 4 still runs on port 8765, so this used `uv run --no-sync`.
- 2026-11-26 · Task 6, Ranking audit log · `feat/audit-log` · Added
  `src/unapply/matching/audit.py` (`AuditEntry`, `content_hash`, `match_entry`,
  `ranking_entry`, `reproduce_ranking`, `check_ranking`) and an append-only
  `audit_log` table (migration `0003`, a schema change to the database; the Pydantic
  schemas in `schemas/` are unchanged). A match entry keeps the rubric version and
  its hash, the profile id and a SHA-256 hash of the profile scored (its version),
  scorer ("baseline" or "llm") and model, the full `Match` with scores, the hard
  filter outcomes, the scorer's problems and the time; it is saved in the same
  transaction as the match (`Repository.save_match(match, audit=...)`). A ranking
  entry keeps the rubric and every ranked match in full with rank and total, so it
  reproduces from the log alone. `match_job` records both; the API's
  `GET /jobs/<name>/ranking` records the ranking it shows too. New
  `Repository.append_audit` / `audit_log`, and `unapply audit <job>` lists a job's
  rankings and checks each (exit 1 if one doesn't reproduce). Append-only: the ORM
  refuses updates and deletes of entries, and the repository has no method for
  them. Scorers gained a `name` attribute ("baseline"/"llm") in the `Scorer`
  protocol. Tested (9 new tests, 227 in all): hashes survive the database and see
  changes; matching logs every match (profile hash, rubric hash, scorer, model,
  scores, filter outcomes) and the ranking; a ranking is reproduced from the log
  after the profile is replaced, and re-scoring the logged profile version gives
  the logged scores; a swapped order, a changed score or a reweighted rubric is
  detected; ORM updates and deletes are refused; a mismatched entry saves nothing;
  a refused paid call logs nothing; the CLI command, including a log changed with
  raw SQL; the API records both its rankings. To know: raw SQL can still change the
  table (no database triggers, to stay portable), but `check_ranking` then reports
  it; profiles and rubrics are hashed as their JSON with sorted keys, so a schema
  change later changes the hashes of the same content; ranking entries repeat the
  matches, which is redundant but makes each entry self-contained; matches stored
  before this task have no match entry (nothing was lost, `check_ranking` skips
  them). The API server from task 4 still runs on port 8765 (`uv run --no-sync`).
- 2026-11-26 · Task 7, Synthetic candidate pool and evaluation · `feat/evaluation` ·
  Added `tests/fixtures/pool/`: 12 fictional candidates for Fjord Grocery, each with
  a short CV, a hand-written stand-in extraction (quotes verbatim from the CV), own
  levels in `review.yaml`, a stand-in estimation, and for the nine who pass the hard
  filters a stand-in LLM scorer answer; `pool.yaml` holds the intended ranking with a
  reason for each place (clear fit; a great fit in synonyms; strong forecaster
  outside retail; career changer; ML engineer weak on statistics; biostatistician;
  honest analyst; overclaimer; frontend developer; and, sharing the last place,
  strong but outside the EU, too junior (38 months), remote only). Added
  `src/unapply/evaluation/` (`top_k_overlap`, Kendall's tau-b with ties,
  `load_reference`, `load_pool`, `evaluate_pool`) and `unapply evaluate [pool]
  [--reference FILE] [--scorer ...] [--k ...] [-v] [--record --allow-api]`, which
  replays every candidate's journey in memory (extract, review and approve,
  estimate, match), stores nothing and runs offline. Results on the pool (k = 3, 5):
  baseline top-3 1.00, top-5 0.80, tau 0.84; LLM scorer stand-ins 1.00, 1.00, 1.00.
  Tested (30 new tests, 257 in all): the metrics on known cases, ties, partial
  references and bad input; the pool loads with no rejected quote, dropped item,
  unknown review edit or estimation problem, every quote is in its CV, every
  recording is marked as a stand-in, exactly the three intended candidates fail a
  filter, synonyms map to the rubric's skills, the overclaimer is flagged, no
  candidate's name reaches the LLM scorer's prompt; both scorers' rankings and
  metrics; a missing recording fails loudly; the CLI, including `--record` refused
  without `--allow-api` and leaving the pool unchanged. To know: the finding worth
  a look is that the baseline ranks the overclaimer 4th instead of 8th, because it
  blends own levels in by (1 - confidence) and his estimates are unsure; not
  changed here (it would change the baseline's documented behaviour and John's
  expected scores). The LLM scorer's perfect agreement only shows the stand-ins are
  consistent with the intended ranking, which I wrote too; record them
  (`docs/to-record.md`, about $1.50) for a real result. The evaluation doesn't read
  matches from the database yet; `--reference` takes a human shortlist as YAML.
  The pool imports `edit_review_sheet` from `unapply.app.demo` (no Streamlit
  needed). Nothing listens on ports 8765 or 8599 any more, so the servers left
  running by earlier sessions are gone; this session still used `uv run --no-sync`.
- 2026-11-27 · Task 8, New frontend (React) · `feat/frontend` · Finished what an
  earlier session left untracked in `frontend/` (Vite 8, React 19, TypeScript 7,
  Tailwind CSS 4, shadcn/ui, React Router; all pages were written, with no tests,
  CI or docs). Candidate steps: material (drag and drop, keyboard-operable, files
  checked before upload; GitHub), review (headline, skills with level chips, a
  filter and their quotes, experience, added skills, preferences, approval in a
  fixed bar), questions, and the profile as employers see it. Employer steps: job
  ad, and the rubric editor (hard filters, criteria with their quotes, lowest level,
  weight 1 to 5, kind, approval; each save a new version). Demo buttons for John Doe
  and Fjord Grocery; the frontend never sends `allow_api`, and a refused paid call
  says to try the demo. Added: Vitest with Testing Library (63 component tests:
  formats, file checks, the API client and its errors, level chips, the drop zone,
  start pages, every candidate and employer step, no assessment words on candidate
  pages), Playwright (4 end-to-end tests in Chromium: both demos all the way
  through, a real candidate refused a paid call, keyboard navigation), and a
  `frontend` CI job (lint, build, component tests, e2e, with the report and
  screenshots kept as an artifact). Playwright starts the API (port 8766) and the
  dev server (5174) itself, with an empty data folder at `%TEMP%/unapply-e2e`,
  emptied at the start of each run, and the database URL set explicitly, then stops
  both; checked that nothing still listens afterwards and that no call log was
  written. Screenshots of both demos are in `docs/screenshots/`. Small fixes from
  the screenshots: toasts moved to the top right (they covered the Save button in
  the fixed bar), the home page's card footers line up, and the rubric's empty
  skill field says "No skill" rather than a grey "python" that looked like a value.
  README (a frontend section; Streamlit is now "internal"), CONTRIBUTING, AGENTS and
  the POC plan updated. All checks pass: ruff, 257 pytest tests, oxlint, build,
  Vitest, Playwright. To know: the CI job uses Node 26 and actions/setup-node@v7
  and upload-artifact@v7 (tags checked to exist; its first GitHub run is on this
  push and wasn't checked here); `npm run e2e` needs `npx playwright install
  chromium` once; the build warns that the bundle is over 500 kB (not split yet);
  there is no matching or ranking page yet, which is task 9.
- 2026-11-27 · Task 9, Employer views (M5) · `feat/employer-views` · Added the
  Shortlist step to the frontend (`frontend/src/pages/employer/Shortlist.tsx`, step 3
  of a job, unlocked once the rubric is approved): candidates ranked and anonymised
  (an alias from the profile id, such as "Candidate 3F2A"), the total as a bar, failed
  and unknown hard filters, and behind "Why" each criterion's score, reason and cited
  quotes, the hard filter outcomes and the roles; a scorer switch (baseline or LLM),
  "Match candidates"/"Match again", and "Reveal" and "Request application", which
  only record the intent. A spider chart (`frontend/src/components/SpiderChart.tsx`,
  plain SVG, no chart library) compares up to three candidates on the rubric's skills:
  estimated levels solid, own levels dashed, or both; fixed colour slots from a
  palette checked for colour-blind readers, kept per candidate (and across scorers);
  a legend, a hover tooltip and a table of every value. Backend:
  `src/unapply/matching/shortlist.py` (the anonymised candidate: headline, roles and
  quotes through `anonymise.redact`, and own and estimated level per rubric skill,
  from a related skill through the taxonomy when the candidate lacks the skill
  itself; `Intent`), `GET /jobs/<name>/shortlist` (the ranking, recorded in the audit
  log like `/ranking`, plus the rubric version, skills, candidates, intents and
  reveal quota), `GET`/`POST /jobs/<name>/intents` (recorded once per job,
  candidate and kind; only candidates matched to the job; reveals limited to the
  job's `reveal_quota`, 10), and `POST /demos/shortlist`, which stores the synthetic
  pool (`evaluation.pool.store_pool`) with a Fjord Grocery job whose rubric is
  approved. New table `intents` (migration `0004`, a database schema change; the
  Pydantic schemas in `schemas/` are unchanged) and `Repository.record_intent`,
  `intents` and `candidate_of`. Tested: 16 new pytest tests (273 in all): the alias,
  rubric skills, levels direct and through a related skill, redaction of names,
  emails, phones, links and file names, intents stored once, storing the pool
  (twice, and a clashing name), the shortlist demo ranking exactly as `unapply
  evaluate` does with both scorers, no pool candidate's name anywhere in the
  shortlist, the audit entry, errors, refused model calls for pool candidates, the
  reveal quota, and years of experience counted to the pool's date; 13 new Vitest
  tests (76 in all) and a Playwright run of the shortlist demo (5 in all), with
  screenshots `11-shortlist` to `14-shortlist-llm` in `docs/screenshots/` (the others
  refreshed). All checks pass. Decisions to check (conservative, small): "Reveal"
  shows no identity, only records the intent and counts against the quota, since
  revealing needs payment and consent; the employer sees organisations and role
  summaries (as the LLM scorer does), with names and contacts removed; pool
  candidates are stored once as demo candidates named `pool-<name>`, are hidden from
  `GET /candidates` and refuse model calls (409), and are matched by every job, so a
  Fjord Grocery demo job ranks them too; a pool job stores its `today`
  (2026-11-26) so years of experience don't drift; a demo job with a pool candidate
  replays that candidate's recording with the LLM scorer. To know: no new stand-in
  recordings (the pool's are already in `docs/to-record.md`); the build still warns
  the bundle is over 500 kB.
- 2026-11-27 · Task 10, Smaller fixes · `feat/smaller-fixes` · **Dates:** a
  schema change: `Experience` has `start_precision` and `end_precision`
  (`DatePrecision`, "year" or "month", default "month"), with columns on
  `experiences` (migration `0005`; rows stored before get "month"). New
  `src/unapply/dates.py` (`parse_partial_date`, `format_partial_date`) used by
  extraction, the review sheet, the Streamlit tables and profile, the estimation and
  LLM scorer prompts, and the shortlist; the frontend's `month`/`period` take the
  precision. So "2017" stays "2017" and "2018-01" stays "2018-01" (before, every
  January was shown as a bare year, and John's "2018-01" came back from the review
  sheet as "2018"). An experience is in order when either date is known only to the
  year and the years are in order ("2019-08" to "2019" used to be refused). A month
  the model gives out of range keeps the year. **Ingestion:** in a folder,
  `load_path` skips files that describe the folder (`README`, `CHANGELOG`,
  `CONTRIBUTING`, `LICENSE`, any supported suffix) and JSON or YAML with a top-level
  `$schema`; a file given by name is still read. `load_path(..., exclude=[globs],
  skipped=[])` lets the candidate leave files or folders out and reports every
  skipped file with the reason; `unapply ingest --exclude PATTERN` (repeatable)
  prints them. The API now reads each upload on its own (an uploaded README is the
  candidate's choice, so it is read; they remove a file to leave it out); the
  Streamlit material list marks files the folder load won't read. **Streamlit
  review:** an "Evidence in full" view under the skills and experience tables shows
  each quote of a chosen item exactly as written, with source, file name and
  locator (`forms.evidence_details`). Tested: 29 new pytest tests (302 in all):
  parsing and formatting, John's extraction keeping both precisions, review sheet
  round trip and edits, a bad date refused, the year comparison, the prompts, the
  shortlist and the database keeping precision; folders skipping READMEs (also in
  subfolders), schemas and unsupported files with reasons, a README by name, YAML
  and JSON that aren't schemas, exclusions by name, folder and path, LinkedIn zips
  in a folder, the CLI's `--exclude` and report, the API reading an uploaded README
  and not a removed file; the detail view's helper and an AppTest clicking it for a
  skill and an experience. Frontend: 2 more Vitest tests (78), e2e unchanged (5).
  All checks pass. To know: profile hashes in the audit log change for the same
  content (new fields), as noted in task 6; the minimum-years filter still counts a
  year-only date as January (a year-only end undercounts by up to 11 months), not
  changed so the pool's filter edges and the evaluation stay as they were; the
  frontend's review form already took "YYYY" or "YYYY-MM" text, so it keeps the
  precision through the API with no change.
- 2026-11-27 · Task 11, MCP server · `feat/mcp-server` · Finished from an earlier
  session's uncommitted work (it had the code, no tests). **Consent:** a database
  schema change: new table `consents` (migration `0006`), keyed by the candidate's
  and the job's row ids so it outlives a new profile or rubric, with the shared
  sections and the time; the Pydantic schemas in `schemas/` are unchanged (the
  `Consent` model is in `src/unapply/consent.py`). `Repository.grant_consent`,
  `withdraw_consent`, `consent`, `consents`, and `unapply consent
  grant|withdraw|list`. **Server:** `src/unapply/mcp_server/` (`build_server(repo,
  job)`, `unapply mcp <job>` over stdio), on the MCP SDK 2.3 (`mcp` moved from an
  optional extra to a core dependency), with read-only tools `get_rubric`,
  `list_candidates`, `get_experiences`, `get_skills`, `search_evidence(query,
  limit)` and `get_preferences`; the logic is in `AgentTools`, testable without MCP.
  Only candidates who opted in with an approved profile exist for the job's agent;
  each tool needs its section shared; consent is read on every call; strangers,
  unknown or old profile ids and drafts all get the same refusal. Texts go through
  `anonymise.redact` (with the GitHub username, as the shortlist does); no name,
  contact, file name or claim support. Tested: 19 new pytest tests (321 in all),
  through the SDK's in-process `Client`: consent stored, changed, per job, kept over
  a new profile, withdrawn, and unknown names; the tools and their read-only
  annotations and instructions; the rubric; who is listed; the same refusal for
  every kind of stranger on every tool; each section on its own; withdrawal on the
  next call; redaction on a synthetic candidate with contact details; search
  ranking (dbt quotes first for "SQL" through the taxonomy, then by words found),
  limits and empty queries; no pool candidate named by any tool; the CLI. All
  checks pass; the frontend is unchanged. Decisions to check (conservative, small):
  sections are chosen per job and all are shared by default; the agent sees
  estimated levels and their confidence (as the employer's shortlist does) but not
  claim support; `get_rubric` and `list_candidates` were added so the agent knows
  the job and the ids. Task 14's "Connect my profile" will grant this consent. To
  know: no agent scores over the server yet (the LLM scorer still takes the profile
  in one call); `redact` removes known names in a bare domain such as
  "jane.example.com" but leaves the rest of the domain (pre-existing, not changed);
  `scripts/autorun.ps1`, `frontend/package-lock.json` (its name) and `TODO.md` had
  changes not made by this task, left uncommitted.
- 2026-11-27 · Task 12, Shortlist: own and estimated scores, and failed filters ·
  `feat/shortlist-scores` · **Failed filters are scored:** `match_candidate` now
  always calls the scorer, and `Match.total` no longer returns 0 when a hard filter
  failed: a change to `Match` in `src/unapply/schemas/job.py` (behaviour only, no
  new field, no database change). `rank` already put failed candidates after
  everyone who passes; now they are ordered by score among themselves. The audit
  log's match and ranking entries for them carry their scores. Hand-written
  stand-in LLM answers for the three pool candidates who fail a filter
  (`clara-jensen`, `emil-dahl`, `priya-raman`, quotes cited by id from their CVs),
  added to `docs/to-record.md` (now 36 calls, about $1.60). **Own and estimated
  scores:** `BaselineScorer(levels="blend"|"own"|"estimated")` and `level(skill,
  levels)`; a missing level counts as aware (1), as before when neither was there;
  `own_and_estimated(profile, rubric)` gives both totals. The ranking and shortlist
  routes return them as `own_total` and `estimated_total` on each `RankedCandidate`
  (None if the profile changed since the match), worked out at read time, free.
  **Frontend:** each shortlist card shows the scorer's total ("Baseline total" or
  "LLM total", which sets the rank), "Own rating" and "Estimated from evidence" as
  three rows of bars, with a key above the list; candidates who fail a filter come
  below a "Don't meet the requirements · N" divider, on a light red card with each
  failed filter named ("Doesn't meet work permit: ..."), and their reasons per
  criterion. **Evaluation:** the reference keeps the three sharing the last place;
  the ranking now orders them by score, so tau-b moves: baseline 0.84 to 0.82, LLM
  stand-ins 1.00 to 0.98 (sqrt(63/66): every pair the reference orders is in
  order, but it ties three the ranking doesn't); top-k unchanged (1.00/0.80 and
  1.00/1.00). Tested: pytest 324 (task 5's "isn't scored" test now checks a
  failed candidate gets the same scores as if they passed; rank ties among failed
  candidates; audit entries with scores; level modes and the two totals; the
  overclaimer's own rating 0.3+ above his estimate; the shortlist route on the
  pool with both scorers: both totals, nine then three, Priya above most who pass
  but 10th); Vitest 81 (three scores, the divider and its absence, the red card,
  reasons for a failed candidate); Playwright 5 (the shortlist demo checks the
  three scores, the divider, three failed cards with four failed filters), with
  screenshots refreshed and a new `15-shortlist-failed`. All checks pass. To know:
  Reveal and Request application stay enabled on failed cards (task 16 reworks
  those buttons); the own and estimated totals always use the baseline, also
  when the LLM scorer ranks.
- 2026-11-27 · Task 13, Anonymous candidate identities · `feat/anonymous-identities` ·
  **Aliases:** `src/unapply/matching/shortlist.py` replaces "Candidate 3F2A" with
  an adjective and an animal or object ("Cyan Heron", "Quartz Compass"): 48
  adjectives (colours, weather, textures, patterns) and 40 nouns, 1920 aliases.
  Left out on purpose: words that are person names (Amber, Robin, Jade, Crane...),
  that judge (Swift, Clever), or that hint at body, age, gender or skin colour
  (Tiny, Old, Ivory, Walrus). `identity(profile_id)` picks one from a SHA-256 of the
  profile id; `identities(ids)` makes them unique within a job (a clash goes to the
  lower profile id; the other takes the next free alias), independent of order.
  `AnonymousCandidate` gained `avatar` (the alias's number; not a schema in
  `schemas/`, no database change). The shortlist route and the MCP server's
  `list_candidates` and refusals use `identities` over the job's candidates.
  **Avatars:** drawn in the frontend (`frontend/src/lib/avatar.ts`,
  `components/CandidateAvatar.tsx`): a 5x5 mirrored grid in one of 8 cool,
  saturated colours (no skin, hair or pink/blue tones, each 4.5:1 on white) on a
  light tint; colour and pattern come from the alias number one to one, so two
  aliases never share an avatar; plain SVG, nothing fetched. Shown beside the alias
  on each shortlist card. Tested: pytest 329 (stable aliases, alias number and
  words agree, no alias word is a common first name or in a pool name, unique and
  order-independent on 400 ids, clash rule, too many candidates refused, the pool
  shortlist's 12 aliases and avatars unique and the same with both scorers, MCP
  aliases); Vitest 88 (every one of the 1920 avatars different, mirrored, never
  empty, contrast, no external reference, avatar on each card); Playwright 5 (the
  shortlist demo checks two-word aliases and avatars, none shared), screenshots
  refreshed. All checks pass. To know: uniqueness is over the candidates a view
  shows (the ranking for the shortlist, those who opted in for the MCP server), so
  if those sets differ and two candidates' aliases clash, one of them could be
  named differently in the two views; with 1920 aliases that is rare, and task
  14's "matching uses only connected candidates" makes the sets the same. A
  mirrored grid can now and then look a little like a figure; it carries no
  meaning. The Vitest fixtures keep their "Candidate A1A1" aliases (mock data).
- 2026-11-27 · Task 14, More demo jobs, vacancies and a job board · `feat/job-board` ·
  **Demo jobs:** ten invented jobs beside Fjord Grocery in `tests/fixtures/jobs/`
  (energy forecasting, junior analyst, senior ML engineer, data engineer in Aarhus
  with remote work, fully remote backend developer in Berlin, a category manager and
  a statistics lecturer outside tech, a senior forecaster in Bengaluru, an
  experimentation analyst, a junior data scientist), each with `ad.md`, a README and
  a **hand-written stand-in** `extraction.json` with quotes verbatim from the ad
  (listed in `docs/to-record.md`, about $0.30 to record). `board.yaml` lists the
  eleven with their vacancies (1 to 3). On the pool, the baseline ranks each job's
  intended fit first among those who pass (Sofie for energy, Freja for the analyst
  role, Nadia for ML engineering, Lars for the category manager, Ida for the
  lecturer, Mikkel for experimentation); only Clara (remote) passes the Aarhus and
  Berlin jobs; nobody passes Bengaluru, where Priya ranks first. **Vacancies (a
  schema change):** `Job.vacancies` (default 1, at least 1) in
  `src/unapply/schemas/job.py`, a `vacancies` column on `jobs` (migration `0007`,
  existing rows get 1). The employer sets it in the ad step (`JobAd.vacancies`;
  "Save vacancies" changes it at once, also on a demo whose ad is fixed). **Job
  board:** `src/unapply/jobs/board.py` (`Listing`, `listings`, `search`,
  `seniority` from the title, `connect`, `withdraw`, `connected`), routes `GET
  /board`, `GET /board/<job>`, `GET|PUT|DELETE /candidates/<name>/connections[/<job>]`
  and `POST /demos/board` (idempotent; jobs named `board-<folder>`). Listings are
  jobs with an approved rubric: ad, vacancies, place, work modes and seniority,
  never criteria, weights or levels. Frontend: a fifth candidate step, **Jobs**
  (`frontend/src/pages/candidate/Jobs.tsx`): search, filters (native selects),
  cards, a listing page with the ad rendered from Markdown as text (`AdText`), and
  Connect my profile / Withdraw. **Connecting** grants task 11's consent with its
  time; only approved profiles; refused withdrawal once revealed; withdrawing drops
  the candidate from the next ranking and shortlist (earlier audit entries stay).
  Tested: pytest 368 (39 new in `tests/test_board.py`: fixtures and quotes, the
  variety of jobs, each job's ranking of the pool in memory and through the API,
  vacancies round trip and the ad route, seniority, search and facets, only
  approved rubrics listed, the board demo stored once, no rubric word in any board
  response, connect/withdraw rules, matching only connected candidates, refusal
  after reveal, LLM scorer refused on jobs without recordings); Vitest 103 (15 new);
  Playwright 6 (new: John's demo approves, adds the demo jobs, searches, filters,
  reads a listing, connects, is ranked by the job, withdraws and drops out of the
  next ranking), screenshots `16` to `19` added and the rest refreshed. All checks
  pass. Decisions to check (as the plan says, plus small conservative ones):
  matching (API and `unapply match`, also with `--candidates`) now uses only
  connected candidates; pool candidates count as connected to every demo job without
  a consent row, so the MCP server still only lists those who opted in; place and
  work modes on a listing come from the approved rubric's hard filters (they are
  copied from the ad; task 15 names failed filters to candidates anyway), seniority
  from title words (junior/graduate/trainee, senior/sr, lead/head/principal; else
  mid); the LLM scorer is refused (409) on board jobs without the pool's recordings
  (all but Fjord Grocery); demo candidates see "Add the demo jobs" on the board. To
  know: tests that matched candidates without consent now connect them first; the
  shortlist demo ranks exactly the 12 of the pool, as John's demo isn't connected
  to it; `scripts/autorun.ps1`, `frontend/package-lock.json` and `TODO.md` still
  have changes not made by a task, left uncommitted.
- 2026-11-27 · Task 15, How well you fit, for candidates · `feat/fit-for-candidates` ·
  Added `src/unapply/jobs/fit.py` (`FitBand`, `band`, `filter_label`,
  `missed_filters`, `own_band`, `place`, `fit`, `fits`) and
  `matching.baseline.own_total`. The **band** is the baseline's total on own levels
  only, worked out on `candidate_view(profile)` (no estimates, no claim support, so
  nothing from the assessment can move it): strong from 0.8, good from 0.6, partial
  from 0.3, below that "Low fit". Only the band is returned, never the score. The
  **missed hard filters** are those that fail (unknown ones don't, as in matching),
  named from the job's hard filters, which are copied from the ad ("Location:
  Aarhus", "Work mode: remote", "Work permit: EU required", "Experience: at least 4
  years"). The **place** ("You're #3 of 13") comes from the job's latest ranking
  entry in the audit log, only while the candidate is connected; connected but not
  in that ranking says "Not ranked yet". Nothing is stored (no consent, no audit
  entry). Routes `GET /candidates/<name>/fit` (every listing) and `GET
  /candidates/<name>/fit/<job>`. Frontend: a band badge, a "You're #N of M" badge
  and red badges for missed requirements on each board card
  (`components/FitBadge.tsx`), and a "How well you fit" card on each listing that
  updates after connecting and withdrawing. Tested: pytest 397 (29 new in
  `tests/test_fit.py`: bands at every edge, twelve pool candidates across the jobs
  from strong to low, every pool band equals the own-only total's band, the
  overclaimer's band unchanged when his estimates are replaced, filter labels,
  Priya, Emil and Clara's failed filters on Fjord Grocery and none for a profile
  that leaves place and permit out, John's fits on all eleven jobs, nothing stored,
  place before ranking, after matching, from the newest ranking, gone after
  withdrawal, a failed pool candidate placed 10th of 12, unknown names, and no
  rubric or assessment word, nor "score" or "total", in any fit response); Vitest
  108 (5 new); Playwright 6 (John's board test checks bands, missed filters, "Not
  ranked yet" and his place after the job is matched, on the listing and the
  board), screenshot `20-job-listing-place` added and the rest refreshed. All
  checks pass. Decisions to check (small, conservative): **a fourth band, "Low
  fit"**, below 0.3, because calling a total of 0.00 "Partial fit" would mislead;
  the band and missed filters are shown after connecting too, beside the place;
  "of" counts everyone in the latest ranking, including those who fail a filter;
  the latest ranking is whichever scorer ranked last (the employer's view also
  records rankings); the place shows only after the employer has ranked since the
  candidate connected. To know: `playwright.config.ts` now starts Vite with
  `--bypass-lock`, because Vite 8 refuses a second dev server for the project and
  one (PID 30480, port 5173, not started by this session) was running; it was left
  alone. `scripts/autorun.ps1`, `frontend/package-lock.json` and `TODO.md` still
  have changes not made by a task, left uncommitted.

## Questions for Ivar

None yet.
