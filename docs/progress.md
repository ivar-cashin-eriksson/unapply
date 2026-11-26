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

## Questions for Ivar

None yet.
