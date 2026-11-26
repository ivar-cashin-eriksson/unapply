# POC plan

## What the POC must prove

1. **Ranking quality (primary).** LLM ranking over structured profiles produces shortlists that
   people who hire agree with about as much as they agree with each other.
2. **Candidate willingness.** People will upload a rich profile once instead of writing applications.
3. **Employer willingness to pay.** Companies pay to reveal a ranked, anonymised shortlist.
   Companies are the first paying side.

## Milestones

### M0: Schemas (done)
Pydantic models for Profile, Evidence, SkillRating, Rubric and Match (`src/unapply/schemas/`).

### M1: Candidate ingestion (done)
- Inputs: CV PDF, LinkedIn data export, GitHub URL, free text.
- LLM extraction into `Profile`; every claim gets `Evidence`, and quotes not found
  verbatim in their source are discarded.
- The candidate reviews and approves the profile through a YAML review sheet
  (`unapply review export` / `apply`): own levels, removals, corrections, added skills.
- Result on the author's own material (CV, resume-builder profile, LinkedIn, GitHub):
  48 of the 50 skills in their hand-written list extracted, no invented quotes.
- Known gaps: dates are year precision when the source gives only years. Synonyms
  ("radiotherapy planning" vs "radiation therapy planning") are now merged through
  the skill taxonomy (below).

### M2a: Skill estimation and claim support (done)
- `unapply estimate`: one model call estimates every skill's level, confidence and a
  reason from its evidence and the candidate's roles. The model never sees the
  candidate's own levels. Estimates resting only on the candidate's statements are
  capped at confidence 0.3.
- Confidence means how sure the estimate is close to the real level: "familiar with"
  or a course is evidence of a low level, a bare skills-list entry is no information.
- Claim support (deterministic) sorts rated skills into findings: overclaims (own
  level 2+ above a sure estimate), unverified (2+ above, evidence says little),
  underclaims, and skills backed only by the candidate's statement. Shown as counts,
  such as "3 overclaims, 4 unverified, 0 underclaims, 2 only your own statement, of
  26 rated skills". Not shown to the candidate (see the candidate app below).
- John Doe's answer key is met: all three overclaims, four unverified skills and both
  self-stated skills flagged, consistent skills left alone.
- Known limits: evidence for one skill that implies another (dbt implies SQL) isn't
  shared in estimation (the skill taxonomy records the relation, for matching); cross-source consistency (dates in CV vs LinkedIn) isn't checked yet.
- Open question: whether and how findings combine into one score. A mean penalty
  over rated skills (`penalty_score`, kept but not used) lets a few large overclaims
  among many honest ratings still score high (John: 0.93). Counts for now.

### M2b: Gap-filling interview (done)
- Rules choose up to 8 skills: unverified first, then those backed only by the
  candidate's statement, then overclaims (as a chance to show more), highest
  self-rated first, never the same skill twice.
- Sonnet 5.5 words each question from the skill's evidence and the roles, asking for
  one concrete example; a template stands in for any it skips.
- `unapply interview export` / `apply`: answers become the candidate's statements,
  with their question, and clear the answered skills' estimates; `unapply estimate`
  then re-estimates only those, so other estimates don't drift between runs.
- John Doe: a detailed pandas answer raised it from 1 to 4 (confidence 0.55); a vague
  Git answer changed nothing; an honest "only the course" made the deep learning
  estimate surer; a concrete Kubernetes statement stayed capped at confidence 0.3.

### Candidate app (done)
- `unapply app`: a Streamlit app for every candidate step (material, review,
  estimate, interview, profile), on top of the same functions as the CLI. Edits
  become review and interview sheets, so validation is shared.
- Paid API calls are off unless the sidebar toggle is on in that session (and the
  `UNAPPLY_ALLOW_API_CALLS` switch or `--allow-api` for the CLI); every real call is
  logged with an estimated cost. A John Doe demo replays recorded answers for free.
- Tested headlessly with Streamlit's AppTest, clicking through John's whole journey.
- The assessment is hidden from candidates: steps are Material, Review, Questions and
  Profile; estimation runs in the background when questions are prepared and answers
  submitted; interview wording is neutral; the profile and its download leave
  estimates out. Candidates are told their evidence is assessed and can ask for the
  assessment. A developer view adds an internal Assessment page. A test checks that
  no assessment wording appears on any candidate page.

### M3: Job rubric (done)
- `unapply job extract`: a job ad becomes a draft rubric: hard filters (locations,
  work modes, work permits, minimum years) and must-have / nice-to-have criteria with
  skill, minimum level and weight 1 to 5. Every criterion quotes the ad; criteria
  whose quote isn't in it, or that repeat another, are dropped. Instructions in the
  ad are ignored (the fixture ad contains one).
- `unapply job export` / `apply`, and the app's Employer side: the recruiter edits
  filters and criteria and approves; any change raises the rubric's version.
- Demo: the fictional Fjord Grocery ad, which fits John Doe partly, with a recorded
  extraction: Claude found the filters (Copenhagen, hybrid, EU, 4+ years), 6
  must-haves and 4 nice-to-haves, dropped nothing and ignored the injected line.

### M4: Matching (done, except over MCP)
- `src/unapply/matching/`, `unapply match <job> [--scorer baseline|llm]` and the API's
  `/jobs/<name>/match` and `/ranking`. Only approved profiles, only approved rubrics,
  and matching locks the rubric version.
- Deterministic hard filters first: work mode, location, work permit (EU and member
  states) and minimum years of work (month precision, overlapping roles counted
  once, education left out by a title heuristic). Missing information is "unknown",
  not a failure. Candidates who fail a filter aren't scored.
- Two scorers, each giving a score from 0 to 1 per criterion with a reason and
  evidence ids: a **baseline** in plain code (level against `min_level`, blending
  own and estimated levels by confidence, times an evidence factor; related skills
  through the taxonomy, discounted) and an **LLM scorer** (one call per candidate,
  on the anonymised profile; cited ids checked to be the candidate's).
- Then `Match.total` and a ranking (equal totals share a rank).
- An append-only audit log (`audit_log`, `unapply.matching.audit`): every match
  (rubric version and hash, profile hash, scorer, model, scores, hard filter
  outcomes, time) and every ranking (the rubric and the ranked matches in full), so
  a ranking can be reproduced from the log alone. `unapply audit <job>` checks it.
- John Doe against Fjord Grocery: 0.81 (baseline) and 0.71 (LLM, from a hand-written
  stand-in answer until it is recorded). Both put forecasting, Python and A/B
  testing high and SQL, Spark and deep learning low.
- Known limits: the baseline can't score criteria without a skill (Fjord's "retail or
  e-commerce"); places are matched by name, without geography ("Denmark" doesn't
  match "Copenhagen"); hard filter outcomes are kept in the audit log, not with the
  match.
- Still to do: agent scoring over MCP tools scoped to what the candidate consented
  to (`get_experiences`, `get_skills`, `search_evidence(query)`, `get_preferences`),
  with the MCP server.

### M5: Recruiter view
- Anonymised ranked list with explanations.
- **Spider chart comparing selected candidates** on the rubric's skills, toggling between
  self-reported and estimated levels (and an overlay of both).
- "Reveal" button (no payment yet; logs intent) and "Request application" button.

### M6: Candidate view
- "You're #4 of 37 for this role." The profile, without the assessment.

## The key experiment (run alongside M1–M4)

- 30–50 real CVs (with consent) and 4–5 real job ads.
- 2–3 people who hire each shortlist the top 10 by hand for each job.
- Compare the system's ranking with theirs (top-k overlap, Kendall's tau), using agreement
  between the humans as the ceiling.
- Done so far: `unapply evaluate` (`src/unapply/evaluation/`) computes both metrics
  for each scorer against a reference ranking, a YAML file of candidates and ranks
  (`--reference`), and runs on a synthetic pool of 12 candidates for Fjord Grocery
  with an intended ranking (`tests/fixtures/pool/`). On it the baseline scores
  top-3 1.00, top-5 0.80, tau 0.84; it ranks an overclaimer 4th instead of 8th,
  because unsure estimates leave room for the candidate's own levels. The LLM
  scorer's answers are hand-written stand-ins until recorded. Still to do: rankings
  from the database (real matches) and agreement between human rankers.

## Out of scope for the POC

Payments, a separate MCP server per person (one multi-tenant server with consent-scoped tools
instead), production auth, multi-company tenancy, and verification (references, certificates).

## Stack

Python 3.12, uv, Pydantic, SQLAlchemy 2.0 and Alembic (SQLite now, Postgres + pgvector later:
a URL change), FastAPI, the MCP Python SDK, the Claude API, and Streamlit for the first UI.

### Database (done)
- `src/unapply/db/`: tables for candidates and their profiles (sources, evidence,
  experiences, skills with own level and estimate, claim support), interview questions
  and answers, jobs, rubric versions and criteria, matches and criterion scores, and
  the history of every step. Migrations build them from empty on SQLite and render for
  Postgres.
- A repository saves and loads the existing schemas (John Doe's profile at every step
  and Fjord Grocery's job load back equal). Rubric versions that a match refers to
  can't change. `unapply db init` and `unapply db import <workspace>`.
- The app still works on workspace folders; the API will use the database.

### Skill taxonomy (done)
- `config/skills.yaml`: 86 canonical skills (data science, data engineering, a few
  domains and spoken languages) with synonyms, and two relations: implies ("dbt" →
  "sql", "pytorch" → "deep learning") and broader ("lightgbm" → "gradient boosting").
  Checked on load: a name belongs to one skill, relations name canonical skills, no
  cycles.
- Names are canonicalised at extraction, review and rubric time, so synonyms merge;
  a review merges skills that an older profile kept apart and estimates them again.
- `Taxonomy.implied` and `Taxonomy.supporting` follow the relations, for matching.
  `unapply db init` copies the taxonomy into its tables.

### API (done)
- `src/unapply/api/`: FastAPI routes over the database for candidates (create,
  upload material, extract, review, questions, answers, profile), jobs (create, ad,
  extract rubric, read versions, edit and approve the rubric) and the two demos.
  `unapply api` starts it; OpenAPI docs at `/docs`.
- Candidate routes return the profile without the assessment; the assessment is only
  on `/internal/...` routes, added with `unapply api --internal`.
- Paid model calls are refused (403) unless the request adds `?allow_api=true` or the
  switch is on; a refused request changes nothing. Demos replay recordings.
- Matching routes (M4): `POST /jobs/<name>/match`, `GET /jobs/<name>/ranking`.
