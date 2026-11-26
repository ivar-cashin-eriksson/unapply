# Recordings to make

Hand-written stand-ins for model answers, written while paid API calls were off. Each
should be replaced by a real recording (with Ivar's permission), then its tests
re-run and adjusted if the model answers differently.

| Stand-in file | Record with | Notes |
|---|---|---|
| `tests/fixtures/jobs/fjord_grocery/match_john_doe.json` | `uv run unapply match fjord-grocery-demo --candidates john-doe-demo --scorer llm --allow-api --record tests/fixtures/jobs/fjord_grocery/match_john_doe.json` | The LLM scorer's answer for John Doe's re-estimated profile against the approved Fjord Grocery rubric (one Opus 5.5 call, about $0.05). First put both in the database: finish John's demo journey and approve the Fjord Grocery demo rubric in the app, then `uv run unapply db import data/john-doe-demo data/jobs/fjord-grocery-demo`. Then run `uv run pytest tests/test_matching.py tests/test_api.py` and adjust the expected LLM scores and total (0.71) to the model's. Evidence ids (E1 to E32) follow the order of John's evidence, so they stay valid while his recordings don't change. |
