# Autonomous runs

Tasks live in the GitHub issues of `ivar-cashin-eriksson/unapply`, not in this repo.
Work through the open issues labelled `autonomous` while Ivar is away, until the usage
limit is reached. Run it with `pwsh scripts/autorun.ps1`: one fresh Claude Code
session per task, so no context carries over. Each session reads this file, finishes
an unfinished task or takes the next one, logs it on the issue, and exits.

Product decisions that hold for every task are in [decisions.md](decisions.md).

## Finding the task

- Use the `gh` CLI. Read only what you need: the list, then the one issue you take.
- An unfinished task first: an open `autonomous` issue labelled `in-progress`, or an
  unmerged task branch. Read its comments (`gh issue view <n> --comments`) to see
  where the last session stopped.
- Otherwise the next open `autonomous` issue that isn't labelled `blocked`, by
  priority: `priority: high` first, then issues with no priority label, then
  `priority: low`; within a priority, the lowest number:
  `gh issue list --label autonomous --state open --json number,title,labels --limit 100`.
- When you start, add the `in-progress` label and comment the branch name.

## Labels

- `autonomous`: a task for these runs. `in-progress`: a session has started it.
- `blocked`: can't go on without Ivar; `question`: it asks Ivar something.
- `priority: high`, `priority: low`: the order Ivar wants; no label is normal.
- `idea`: Ivar's ideas for later, not for these runs. Never take an `idea` issue.
- Ivar decides what becomes a task and its priority; don't add `autonomous` or a
  priority label to an issue yourself.

## Ground rules

These apply to every task. If a rule and an issue disagree, the rule wins.

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

- One `feat/<task>` (or `fix/`, `chore/`, `docs/`, `test/`) branch per issue,
  **from `dev`**. Merge it into `dev` with `--no-ff` when the task is done and every
  check passes (below), push `dev`, then delete the branch locally and on GitHub.
- Once no open `autonomous` issue is left that isn't blocked: create `user/claude`
  from `dev` (if it doesn't exist). Any further work goes on branches from
  `user/claude` and is merged into `user/claude`, never into `dev`.
- Never commit to, merge into or push `main`. Never force-push. Never rewrite history.
- Commit messages: `<type>: <Summary>`, mentioning the issue (`(#17)`), ending with
  the co-author line. Commits use the repo's local git email (the GitHub noreply
  address); don't change git config.

### Checks before every merge

1. `uv run ruff check .` and `uv run ruff format --check .`
2. `uv run pytest -q -p no:logging`
3. In `frontend/`: `npm run lint`, `npm run build`, `npm test` and `npm run e2e`.

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

### Logging on the issue

- Issues are public: never put secrets, personal data or anything from `data/` in
  them.
- Write comment bodies to a file and pass `--body-file`, so quoting can't break them.
- When the task is merged, comment on its issue: date, branch, what was done, what
  was tested, decisions to check that you took, and anything Ivar should know. Then
  remove `in-progress` and close it: `gh issue close <n> --reason completed`.
- If you stop before it is done (usage limit, a failing check you couldn't fix),
  comment what is done and what is left, so the next session can go on.
- If a task needs a decision only Ivar can make, or can't be done without breaking a
  rule: comment the question, add `blocked` and `question`, remove `in-progress`, and
  go on with the next issue. Don't guess at product decisions; take the conservative
  option and note it if a choice is small.
- Found something outside the task worth doing (a bug, a gap)? Open an issue for it
  without the `autonomous` label, and say so in your comment.
- Keep the code standards in `CONTRIBUTING.md` (NumPy docstrings, type hints, tests),
  and update README, `docs/poc-plan.md`, `docs/decisions.md` and `AGENTS.md` as
  things change.

## After the issues

Once no open `autonomous` issue is left that isn't blocked, continue on `user/claude`
with improvements you're confident about (tests, polish, documentation, small
refactors). When those are done, feel free to develop any features you think make
sense, kept to `user/claude` without merging to `dev`. Log each piece of work as its
own issue, labelled `claude`: open it before you start, comment as above, close it
when merged into `user/claude`.
