# John Doe: a synthetic test candidate

Everything here is invented: the person, the companies and the school. It exercises the
whole candidate flow end to end in `tests/test_end_to_end.py`.

| File | What it is |
|---|---|
| `material/cv.md` | John's CV: an ordinary data scientist in Copenhagen |
| `material/notes.md` | A few notes that are not on the CV, as free text |
| `extraction.json` | A recorded answer from Claude for `material/`, replayed by the offline test |
| `estimation.json` | A recorded estimate of his reviewed profile, replayed the same way |
| `review_edits.yaml` | What John changes in his review sheet, and the answer key that estimation must meet |
| `questions.json` | Recorded interview questions (written by Sonnet 5.5) |
| `interview_answers.yaml` | John's answers (detailed, vague, honest, skipped) and what re-estimation should conclude |
| `estimation_after_interview.json` | Recorded re-estimate of the four skills he answered about |

## Running it

Offline, replaying the recorded answer (the default, free):

```bash
uv run pytest tests/test_end_to_end.py
```

Against the real model (costs about $0.35; needs `ANTHROPIC_API_KEY` in `.env`):

```bash
UNAPPLY_LIVE=1 uv run pytest tests/test_end_to_end.py
```

By hand, as John would:

```bash
uv run unapply ingest tests/fixtures/john_doe/material --replay tests/fixtures/john_doe/extraction.json --out data/john_doe/profile.draft.json
uv run unapply review export data/john_doe/profile.draft.json --sheet data/john_doe/review.yaml
# edit data/john_doe/review.yaml
uv run unapply review apply data/john_doe/profile.draft.json data/john_doe/review.yaml --out data/john_doe/profile.reviewed.json
uv run unapply estimate data/john_doe/profile.reviewed.json --replay tests/fixtures/john_doe/estimation.json --out data/john_doe/profile.estimated.json
uv run unapply interview export data/john_doe/profile.estimated.json --sheet data/john_doe/interview.yaml --replay tests/fixtures/john_doe/questions.json
# answer data/john_doe/interview.yaml
uv run unapply interview apply data/john_doe/profile.estimated.json data/john_doe/interview.yaml --out data/john_doe/profile.interviewed.json
uv run unapply estimate data/john_doe/profile.interviewed.json --replay tests/fixtures/john_doe/estimation_after_interview.json --out data/john_doe/profile.reestimated.json
```

Drop `--replay ...` to call Claude instead; add `--record FILE` to save its answer. After
changing anything in `material/` or the extraction prompt, re-record `extraction.json`:

```bash
uv run unapply ingest tests/fixtures/john_doe/material --record tests/fixtures/john_doe/extraction.json --out data/john_doe/profile.draft.json
```
