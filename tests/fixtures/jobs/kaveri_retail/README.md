# Kaveri Retail Pvt Ltd: a synthetic job ad

An invented company and ad for the demo job board, matched against the synthetic pool in
`tests/fixtures/pool`. Outside the EU, in Bengaluru: every pool candidate fails a hard filter. Priya Raman (permit for India) fails only the location, as she wants Copenhagen, and scores best.

| File | What it is |
|---|---|
| `ad.md` | The job ad |
| `extraction.json` | A **hand-written stand-in** for the rubric extraction, with quotes copied verbatim from the ad. Not a model answer |

Its vacancies and the other demo jobs are listed in `tests/fixtures/jobs/board.yaml`.

To record a real extraction (one paid call, about $0.03; only with permission):

```bash
uv run unapply job extract tests/fixtures/jobs/kaveri_retail/ad.md --allow-api --record tests/fixtures/jobs/kaveri_retail/extraction.json --out data/jobs/kaveri_retail.json
```

Then run `uv run pytest tests/test_board.py` and adjust the expected results if the model
splits the ad differently.
