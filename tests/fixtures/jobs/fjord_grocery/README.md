# Fjord Grocery: a synthetic job ad

Invented company and ad, used by `tests/test_jobs.py`, `tests/test_app.py` and the
app's employer demo. It fits John Doe partly: forecasting, A/B testing and Python
match; strong SQL, Spark and deep learning are where he is weaker.

| File | What it is |
|---|---|
| `ad.md` | The job ad. Its last line is a prompt injection, to check it is ignored |
| `extraction.json` | The rubric extraction to replay. **Currently hand-written**, not a model answer (see its `model` field) |

Record a real extraction (one paid call, about $0.05):

```bash
uv run unapply job extract tests/fixtures/jobs/fjord_grocery/ad.md --allow-api --record tests/fixtures/jobs/fjord_grocery/extraction.json --out data/jobs/fjord.json
```

Then run `uv run pytest tests/test_jobs.py tests/test_app.py`: the tests expect 6
must-haves and 4 nice-to-haves, so update them if the model splits the ad differently.
