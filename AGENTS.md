# unapply: instructions for AI agents

## Project instructions

Read these before changing anything, and follow them:

- [README.md](README.md): what the project is, its design principles, and setup.
- [CONTRIBUTING.md](CONTRIBUTING.md): where code goes, personal data, LLM calls,
  naming, dependencies, code style, tests and the Git workflow.
- [docs/poc-plan.md](docs/poc-plan.md): the current plan and milestones.

This file only adds what applies to agents.

## Working on a change

- Make the smallest change that solves the task. Don't refactor, rename or reformat
  unrelated code.
- Don't change the schemas in `src/unapply/schemas/` without saying so. Everything
  else depends on them.
- Never read, copy or commit real personal data from `data/`. Use only synthetic data
  in `tests/`.
- Never hardcode, print or log secrets.

## Verifying a change

Before you say a change is done, run checks 1 and 2 of the pull request checklist in
CONTRIBUTING.md and make sure they pass.

## Autonomous runs

When working through `docs/autonomous-plan.md`, the user has given permission to
commit, push, change branches and merge into `dev` (or `user/claude`), exactly as its
ground rules describe. That permission covers nothing else: never `main`, never
force-push, and still no paid API calls.

## Never, without explicit permission from the user

- Commit, push, or change branches.
- Merge into `dev` or `main`.
- Call paid APIs (LLM calls included) outside tests that fake them. Concretely: never
  pass `--allow-api`, set `UNAPPLY_ALLOW_API_CALLS=1`, turn on the app's API toggle,
  or run tests with `UNAPPLY_LIVE=1`. Use `--replay` with recorded answers instead.
