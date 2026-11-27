# Havnelys Logistics ApS: a synthetic job ad

An invented company and ad for the demo job board, matched against the synthetic pool in
`tests/fixtures/pool`. Analysts fit best: Freja Nygaard, Jonas Friis (on his own levels) and Lars Winther; no minimum years, so Emil Dahl passes too.

| File | What it is |
|---|---|
| `ad.md` | The job ad |
| `extraction.json` | A **hand-written stand-in** for the rubric extraction, with quotes copied verbatim from the ad. Not a model answer |

Its vacancies and the other demo jobs are listed in `tests/fixtures/jobs/board.yaml`.

To record a real extraction (one paid call, about $0.03; only with permission):

```bash
uv run unapply job extract tests/fixtures/jobs/havnelys_logistics/ad.md --allow-api --record tests/fixtures/jobs/havnelys_logistics/extraction.json --out data/jobs/havnelys_logistics.json
```

Then run `uv run pytest tests/test_board.py` and adjust the expected results if the model
splits the ad differently.
