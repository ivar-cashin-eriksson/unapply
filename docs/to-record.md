# Recordings to make

Hand-written stand-ins for model answers, written while paid API calls were off. Each
should be replaced by a real recording (with Ivar's permission), then its tests
re-run and adjusted if the model answers differently.

| Stand-in file | Record with | Notes |
|---|---|---|
| `tests/fixtures/jobs/fjord_grocery/match_john_doe.json` | `uv run unapply match fjord-grocery-demo --candidates john-doe-demo --scorer llm --allow-api --record tests/fixtures/jobs/fjord_grocery/match_john_doe.json` | The LLM scorer's answer for John Doe's re-estimated profile against the approved Fjord Grocery rubric (one Opus 5.5 call, about $0.05). First put both in the database: finish John's demo journey and approve the Fjord Grocery demo rubric in the app, then `uv run unapply db import data/john-doe-demo data/jobs/fjord-grocery-demo`. Then run `uv run pytest tests/test_matching.py tests/test_api.py` and adjust the expected LLM scores and total (0.71) to the model's. Evidence ids (E1 to E32) follow the order of John's evidence, so they stay valid while his recordings don't change. |
| `tests/fixtures/pool/*/extraction.json`, `estimation.json` and `match_fjord_grocery.json` (12 + 12 + 9 files) | `uv run unapply evaluate --record --allow-api` | The synthetic pool for Fjord Grocery (task 7): each candidate's extraction of `material/cv.md`, the estimate of their reviewed profile (own levels from `review.yaml`) and, for the nine who pass the hard filters, the LLM scorer's answer. One command records all three steps in order, overwriting the stand-ins (33 Opus 5.5 calls, about $1.50). Then check the problems it prints (a real extraction may name skills differently from `review.yaml`), and run `uv run pytest tests/test_evaluation.py`: adjust the expected rankings, overlaps and taus to the model's, keeping the intended ranking in `pool.yaml` as it is. |
