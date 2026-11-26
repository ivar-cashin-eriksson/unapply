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

## Status

Early proof of concept. See [docs/poc-plan.md](docs/poc-plan.md).

See [CONTRIBUTING.md](CONTRIBUTING.md) for conventions and the Git workflow.

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
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

## The candidate app

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
the API (coming next) works on. It is a SQLite file, `data/unapply.db`, unless
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

## Common commands

| Command | What it does |
|---|---|
| `uv sync` | Create or update `.venv/` from `uv.lock` |
| `uv sync --all-extras` | Also install the optional extras (API, MCP, Postgres drivers) |
| `uv run pytest` | Run the tests |
| `uv run ruff check .` | Lint. Add `--fix` to fix what can be fixed automatically |
| `uv run ruff format .` | Format |
| `uv add <package>` | Add a runtime dependency. Use `uv add --dev <package>` for a local-only tool |
| `uv run unapply ingest data/me/ --github <user> --out data/me/profile.json` | Extract a draft profile (calls the Claude API; needs `ANTHROPIC_API_KEY` in `.env`) |
| `uv run unapply ingest ... --record answer.json` / `--replay answer.json` | Save the model's answer, or reuse a saved one without calling the API |
| `uv run unapply job extract ad.md --out data/jobs/acme.json` | Extract a rubric from a job ad (calls the Claude API: add `--allow-api`) |
| `uv run unapply job export data/jobs/acme.json --sheet data/jobs/acme.yaml` | Write a rubric sheet to edit and approve |
| `uv run unapply job apply data/jobs/acme.json data/jobs/acme.yaml --out data/jobs/acme.json` | Apply the edited rubric sheet |
| `uv run unapply db init` | Create the database's tables, or migrate them to the newest version, and load the skill taxonomy |
| `uv run unapply db import data/me data/jobs/acme` | Import candidate and job workspace folders into the database |
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
| `src/unapply/app/` | The app (Streamlit): `candidate.py`, `employer.py`, shared helpers and the demos |
| `src/unapply/jobs/` | Job ads to rubrics, and the recruiter's rubric sheet |
| `src/unapply/workspace.py` | A candidate's folder: material, current profile, history |
| `src/unapply/db/` | The database: SQLAlchemy tables, Alembic migrations, a repository that saves and loads the schemas, and the workspace import |
| `src/unapply/taxonomy.py` | The skill taxonomy: canonical names, synonyms, implied and broader skills |
| `src/unapply/review.py` | The candidate's review sheet: levels, corrections, additions, approval |
| `config/` | Configuration, such as the skill taxonomy (`skills.yaml`) |
| `docs/` | Plans and design notes |
| `tests/` | Tests for the package |
| `tests/fixtures/` | Synthetic test data, including John Doe, a made-up candidate run end to end (see its README) |
| `data/` | Local uploads and real personal data, gitignored |
| `scratch/` | Personal exploration, gitignored |
| `pyproject.toml` | Python project, dependencies, and Ruff and pytest settings |
| `AGENTS.md` | Instructions for AI coding agents (`CLAUDE.md` points to it) |
