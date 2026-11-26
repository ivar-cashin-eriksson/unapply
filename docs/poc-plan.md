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

### M2a: Skill estimation and claim support (done)
- `unapply estimate`: one model call estimates every skill's level, confidence and a
  reason from its evidence and the candidate's roles. The model never sees the
  candidate's own levels. Estimates resting only on the candidate's statements are
  capped at confidence 0.3.
- Confidence means how sure the estimate is close to the real level: "familiar with"
  or a course is evidence of a low level, a bare skills-list entry is no information.
- Claim support (deterministic): overclaims (own level 2+ above a sure estimate) lower
  the score; unverified gaps (2+ above, evidence says little), underclaims and
  low-rated own statements don't. Visible to the candidate with the reasons.
- John Doe's answer key is met: all three overclaims, four unverified skills and both
  self-stated skills flagged, consistent skills left alone.
- Known limits: evidence for one skill that implies another (dbt implies SQL) isn't
  shared; cross-source consistency (dates in CV vs LinkedIn) isn't checked yet.
- Open question: the score is a mean over all rated skills, so a few large
  overclaims among many honest ratings still score high (John: 0.93).

### M2b: Gap-filling interview
- Ask about unverified and unsupported skills ("What did you actually build with
  Kafka?"), keep the answers as the candidate's own statements, and re-estimate.

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
