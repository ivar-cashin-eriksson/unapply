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

## Questions for Ivar

None yet.
