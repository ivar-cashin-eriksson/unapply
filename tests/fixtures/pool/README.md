# A synthetic candidate pool for Fjord Grocery

Twelve invented candidates for the Fjord Grocery job ad (`../jobs/fjord_grocery/`),
written from a clear fit to unsuitable, with an **intended ranking** and the reason
for each place in `pool.yaml`. `unapply evaluate` ranks them with each scorer and
compares the ranking with the intended one (top-k overlap and Kendall's tau);
`tests/test_evaluation.py` checks it. Everything here is invented: people,
companies, schools, email addresses and phone numbers.

The same twelve are matched against the ten other demo jobs on the job board
(`../jobs/board.yaml`) with the baseline scorer; `tests/test_board.py` checks each
job's best fit. There are no recorded LLM scorer answers for those jobs.

| Intended | Candidate | Why there |
|---|---|---|
| 1 | `astrid-holm` | The clearest fit: production demand forecasting at an online grocer, price experiments, strong Python and SQL, PySpark, deep learning, statistics MSc, Danish |
| 2 | `mikkel-lund` | A great fit in other words: "time series prediction", "split testing", "Apache Spark", "deep neural networks", "applied statistics" (synonyms the taxonomy maps) |
| 3 | `sofie-krag` | Strong forecaster and statistician, but energy rather than retail, and no Spark or deep learning |
| 4 | `lars-winther` | Career changer: buyer and category analyst at a supermarket chain, now a data scientist with a forecast in 60 stores; working Python, basic statistics and A/B testing |
| 5 | `nadia-kowal` | Strong ML engineer (deep learning forecasting, PySpark on 4 TB), but almost no statistics, experiments or stakeholder work, and no Danish |
| 6 | `ida-thorsen` | Expert biostatistician who communicates well, but basic Python and SQL and no forecasting |
| 7 | `freja-nygaard` | Honest data analyst: real A/B test analysis, e-commerce, working SQL, basic Python |
| 8 | `jonas-friis` | The overclaimer: "expert" in seven skills, with BI dashboards, SQL views, a Kaggle notebook and an online course as evidence |
| 9 | `henrik-mose` | Unsuitable: a frontend developer who passes the hard filters |
| 10 | `priya-raman` | Strong, but outside the EU and needs a work permit: fails a hard filter |
| 10 | `emil-dahl` | Too junior: about three years of work, the job asks for four |
| 10 | `clara-jensen` | Remote only, from Odense: fails the work mode and location filters |

Candidates who fail a hard filter share the last place in the intended ranking. They
are scored too, and a ranking orders them by score after everyone who passes.

## Files

`pool.yaml` names the job, the date roles are counted to (2026-11-26, so years of
experience don't change), the name of the LLM scorer answers and the intended
ranking. Each candidate's folder has:

| File | What it is |
|---|---|
| `material/cv.md` | The CV. Only `material/` is ingested |
| `extraction.json` | The profile extraction of the CV |
| `review.yaml` | The candidate's own levels, set in the review sheet; the profile is then approved |
| `estimation.json` | The estimate of every skill of the reviewed profile |
| `match_fjord_grocery.json` | The LLM scorer's answer for the job, for every candidate, those who fail a hard filter too |

Every `.json` file is a **hand-written stand-in**, not a model answer (its `model` says
so): the quotes are copied verbatim from the CV, the levels and scores follow the
intended ranking. So the LLM scorer's agreement with the intended ranking only shows
that the stand-ins are consistent; a real recording will show what the model does.
They are listed in [docs/to-record.md](../../../docs/to-record.md).

## Running it

Offline, replaying the stand-ins (free):

```bash
uv run unapply evaluate                       # both scorers, top-3 and top-5
uv run unapply evaluate --scorer baseline --k 3 5 9 -v
uv run unapply evaluate --reference shortlist.yaml   # a human shortlist instead
```

A reference file lists `candidate` and `rank` (and an optional `reason`) under
`ranking`; it may cover only some candidates.

To record real answers instead (paid, about $1.60: 24 Opus calls for extraction and
estimation, 12 for scoring), which overwrites the stand-ins:

```bash
uv run unapply evaluate --record --allow-api
```

A real extraction may name skills differently from `review.yaml`; those are listed
as problems, so check them, adjust `review.yaml` and the expected results in
`tests/test_evaluation.py`, and record again if needed.
