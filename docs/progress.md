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

## Questions for Ivar

None yet.
