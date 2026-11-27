# Tidevand Software GmbH: a synthetic job ad

An invented company and ad for the demo job board, matched against the synthetic pool in
`tests/fixtures/pool`. Fully remote from Berlin: only Clara Jensen, who wants remote work, passes the work mode filter; Nadia Kowal scores best on skills but wants hybrid work.

| File | What it is |
|---|---|
| `ad.md` | The job ad |
| `extraction.json` | A **hand-written stand-in** for the rubric extraction, with quotes copied verbatim from the ad. Not a model answer |

Its vacancies and the other demo jobs are listed in `tests/fixtures/jobs/board.yaml`.

To record a real extraction (one paid call, about $0.03; only with permission):

```bash
uv run unapply job extract tests/fixtures/jobs/tidevand_software/ad.md --allow-api --record tests/fixtures/jobs/tidevand_software/extraction.json --out data/jobs/tidevand_software.json
```

Then run `uv run pytest tests/test_board.py` and adjust the expected results if the model
splits the ad differently.
