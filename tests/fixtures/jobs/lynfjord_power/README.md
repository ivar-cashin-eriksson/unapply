# Lynfjord Power A/S: a synthetic job ad

An invented company and ad for the demo job board, matched against the synthetic pool in
`tests/fixtures/pool`. Sofie Krag (energy forecasting, Bayesian statistics) fits best, then the other forecasters.

| File | What it is |
|---|---|
| `ad.md` | The job ad |
| `extraction.json` | A **hand-written stand-in** for the rubric extraction, with quotes copied verbatim from the ad. Not a model answer |

Its vacancies and the other demo jobs are listed in `tests/fixtures/jobs/board.yaml`.

To record a real extraction (one paid call, about $0.03; only with permission):

```bash
uv run unapply job extract tests/fixtures/jobs/lynfjord_power/ad.md --allow-api --record tests/fixtures/jobs/lynfjord_power/extraction.json --out data/jobs/lynfjord_power.json
```

Then run `uv run pytest tests/test_board.py` and adjust the expected results if the model
splits the ad differently.
