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

1. **Candidates can see everything inferred about them**, including estimated skill levels and
   claim support. What stays hidden is the job's rubric and weights, not the candidate's data.
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

## Common commands

| Command | What it does |
|---|---|
| `uv sync` | Create or update `.venv/` from `uv.lock` |
| `uv sync --all-extras` | Also install the optional extras (API, LLM, MCP, database, ingestion) |
| `uv run pytest` | Run the tests |
| `uv run ruff check .` | Lint. Add `--fix` to fix what can be fixed automatically |
| `uv run ruff format .` | Format |
| `uv add <package>` | Add a runtime dependency. Use `uv add --dev <package>` for a local-only tool |

## Layout

| Path | Contents |
|---|---|
| `src/unapply/` | The Python package |
| `src/unapply/schemas/` | Pydantic schemas: profiles, evidence, skills, jobs, rubrics, matches |
| `config/` | JSON configuration, such as skill taxonomies and thresholds |
| `docs/` | Plans and design notes |
| `tests/` | Tests for the package |
| `tests/fixtures/` | Synthetic test data |
| `data/` | Local uploads and real personal data, gitignored |
| `scratch/` | Personal exploration, gitignored |
| `pyproject.toml` | Python project, dependencies, and Ruff and pytest settings |
| `AGENTS.md` | Instructions for AI coding agents (`CLAUDE.md` points to it) |
