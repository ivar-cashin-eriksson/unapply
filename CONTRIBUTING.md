# Contributing to unapply

Conventions for working on this project. Setup is in the [README](README.md).

## Where code goes

- **All logic goes in the package**, `src/unapply/`, where it can be tested. Entry
  points (API routes, the MCP server, UI pages) stay thin: parse input, call the
  package, return the result.
- **Schemas go in `src/unapply/schemas/`.** They are the contract between ingestion,
  estimation, matching, the MCP server and the UI, so change them deliberately.
- **Database tables go in `src/unapply/db/models.py`**, and only
  `src/unapply/db/repository.py` turns rows into schemas and back. Every change to the
  tables comes with an Alembic migration in `src/unapply/db/migrations/versions/`:
  `uv run alembic revision --autogenerate --rev-id 0003 -m "Add the audit log"`,
  then read and fix what it wrote. Use only types that work on both SQLite and
  Postgres; `tests/test_db.py` checks the migrations match the models and render for
  Postgres.
- **Configuration goes in `config/`** as JSON, or YAML where people edit it by hand
  (the skill taxonomy, `config/skills.yaml`): thresholds, model names.
- **Exploration goes in `scratch/`**, which is gitignored. Move anything worth keeping
  into `src/`.

## Personal data

This project processes CVs and other personal data, and ranking job candidates is
high-risk under the EU AI Act. See the design principles in the README.

- **Never commit real personal data**, including your own CV. Real uploads go in `data/`,
  which is gitignored. `tests/` and `tests/fixtures/` contain only synthetic data.
- **The assessment (estimates, claim support) is never shown in the candidate app.**
  Use `forms.candidate_view()` for anything a candidate sees or downloads, and keep
  interview wording neutral. It is still the candidate's data: it must stay
  exportable for a data access request, and candidates are told it exists.
- **Every score and estimate cites evidence and records the model** that produced it
  (`evidence_ids`, `model`), so it can be explained and audited.
- **Never hardcode, print or log secrets** such as API keys. Read them from the
  environment (`.env` locally, which is gitignored).

## LLM calls

- Keep calls to the model behind one module, so models can be swapped and calls logged
  in one place.
- Validate model output against the Pydantic schemas. Don't pass raw model text on.
- Keep prompts in files next to the code that uses them, not inline in long strings.
- The model answers in its own schemas (such as `Extracted*` in `ingest/extract.py`),
  not the domain schemas: it can't invent ids, and its output is checked before it
  becomes domain data. Their `Field(description=...)` texts are sent to the model, so
  write them as instructions; a one-line class docstring is enough.
- Every quote the model cites must be found in its source text, or it is discarded.

## Naming

| Thing | Convention | Example |
|---|---|---|
| Python | `snake_case` modules and functions, `PascalCase` classes | `skill_estimation.py`, `estimate_skill()`, `SkillEstimate` |
| Skills | Canonical lowercase names | `python`, `kafka`, `machine_learning` |
| Enum values | Lowercase strings | `must_have`, `remote` |

## Dependencies

- **Runtime dependencies** go in `[project] dependencies` (`uv add <package>`), or in
  an optional extra under `[project.optional-dependencies]` if only one part needs them
  (`uv add --optional api fastapi`).
- **Development tools** go in the `dev` dependency group (`uv add --dev <package>`).
- Always commit `uv.lock` together with `pyproject.toml`.

## Code style

- Ruff formats and lints everything. VS Code formats on save. Before pushing:

  ```bash
  uv run ruff check --fix .
  uv run ruff format .
  ```

- Write docstrings and comments for a reader who doesn't know the domain: explain *why*,
  units, allowed values and anything surprising.

## Docstrings and comments

Docstrings follow the [NumPy style](https://numpydoc.readthedocs.io/en/latest/format.html).

- **Every public function, class and module in `src/unapply/` has a full docstring:**
  a one-line summary, then any of the `Parameters`, `Returns`, `Yields` and `Raises`
  sections that apply. Public means the name doesn't start with `_`.
- **Private helpers** (`_name`) need a docstring only when the name and signature don't
  say enough. One line is usually enough.
- **Type hints are required** on every argument and return value in the package. Write
  the types in the docstring too, and keep them in sync with the hints.
- **Describe meaning, not just type:** units, scales, allowed values, and what `None`
  means.
- **Classes**, including Pydantic models, document their constructor arguments (the
  model fields) in a `Parameters` section of the class docstring, not in `__init__`.

```python
def estimate_skill(skill: str, evidence: list[Evidence]) -> SkillEstimate:
    """Estimate a candidate's level in one skill from their evidence.

    Parameters
    ----------
    skill : str
        Canonical skill name, such as "python".
    evidence : list of Evidence
        Evidence from the candidate's profile that mentions the skill.

    Returns
    -------
    SkillEstimate
        The estimated level, with a confidence from 0 to 1 and the evidence used.

    Raises
    ------
    ValueError
        If `evidence` is empty.
    """
```

**Comments** (`#`) explain *why* the code does something, not *what* it does. Delete
commented-out code instead of committing it.

Ruff checks docstrings and type hints in the package (`D` and `ANN` rules): a missing
docstring, a malformed section, an undocumented parameter or a missing type hint fails
`ruff check`. It can't check that the docstring types match the hints or that the
descriptions are useful, so reviewers check those.

## Tests

- Tests live in `tests/` and run with `uv run pytest`.
- Tests must work offline. Fake the model in unit tests. Tests that call a real model
  are opt-in.
- Use only synthetic data.
- CI (`.github/workflows/ci.yml`) runs `ruff check`, `ruff format --check` and
  `pytest` on every push and pull request.

## Git workflow

### Branches

| Branch | Purpose | Merges into |
|---|---|---|
| `main` | The latest stable version | |
| `dev` | Integration branch for finished work | `main` |
| `feat/<description>` | New functionality | `dev` |
| `fix/<description>` | Bug fixes | `dev` |
| `chore/<description>` | Maintenance: dependencies, formatting, refactoring | `dev` |
| `experiment/<description>` | Investigations that may never be merged | `dev`, if at all |
| `hotfix/<description>` | Urgent fixes to `main`, branched from `main` | `main`, then also `dev` |

Only `dev` and `hotfix/*` branches are merged into `main`. Delete a branch, locally
and on GitHub, once it is merged:

```bash
git branch -d <branch>
git push origin --delete <branch>
```

### Commit messages

`<type>: <summary>`, with the summary in the imperative and starting with a capital letter:

```
feat: Add CV ingestion
fix: Handle CVs without dates
chore: Update pydantic
```

| Type | Use for |
|---|---|
| `feat` | New functionality |
| `fix` | Bug fixes |
| `chore` | Maintenance with no behaviour change |
| `docs` | Documentation only |
| `test` | Adding or fixing tests |
| `wip` | Work in progress on your own branch. Squash or reword before merging |

### Pull requests

Before opening a PR:

1. `uv run ruff check --fix .` and `uv run ruff format .` pass.
2. `uv run pytest` passes.
3. The description says what changed, how you tested it, and whether any schema changed.
