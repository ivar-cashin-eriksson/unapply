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
- Known gaps: dates are year precision when the source gives only years; skill names
  need synonym matching ("radiotherapy planning" vs "radiation therapy planning").

### M2: Skill estimation and claim support
- Gap-filling interview, moved from M1: ask about skills whose evidence is weak
  ("What did you actually build with Kafka?"), and keep the answers as the
  candidate's own statements.
- For each skill, estimate `estimated_level` from evidence (projects, duration, depth of
  description, GitHub signals) with a `confidence`.
- Claim support = agreement between self-reported and estimated levels, weighted by confidence,
  plus consistency across sources (for example, dates matching between CV and LinkedIn).
- Visible to the candidate, with the reasons.

### M3: Job rubric
- Paste a job ad, have the LLM extract a `Rubric`, and let the recruiter edit it.

### M4: Matching over MCP
- Deterministic hard filters first (location, work permit, seniority band).
- Agent scoring over MCP tools scoped to what the candidate consented to: `get_experiences`,
  `get_skills`, `search_evidence(query)`, `get_preferences`.
- Output: per-criterion score with evidence ids, then an overall rank.

### M5: Recruiter view
- Anonymised ranked list with explanations.
- **Spider chart comparing selected candidates** on the rubric's skills, toggling between
  self-reported and estimated levels (and an overlay of both).
- "Reveal" button (no payment yet; logs intent) and "Request application" button.

### M6: Candidate view
- "You're #4 of 37 for this role." Profile, estimates and claim support with reasons.

## The key experiment (run alongside M1–M4)

- 30–50 real CVs (with consent) and 4–5 real job ads.
- 2–3 people who hire each shortlist the top 10 by hand for each job.
- Compare the system's ranking with theirs (top-k overlap, Kendall's tau), using agreement
  between the humans as the ceiling.

## Out of scope for the POC

Payments, a separate MCP server per person (one multi-tenant server with consent-scoped tools
instead), production auth, multi-company tenancy, and verification (references, certificates).

## Stack

Python 3.12, uv, Pydantic, FastAPI, Postgres + pgvector, the MCP Python SDK, the Claude API, and
Streamlit for the first UI.
