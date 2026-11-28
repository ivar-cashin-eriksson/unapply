# Product decisions

Decisions Ivar made that hold for every task. Each task's own "decisions to check"
are on its GitHub issue. Add a line here when a decision becomes a lasting rule.

- **Companies pay first.** Employers are the first paying side.
- **No paid calls by default.** Model calls are off unless explicitly allowed
  (`--allow-api`, the app's toggle); demos replay recordings.
- **The assessment is hidden from candidates** (2026-11-26). Skill estimates and claim
  support never appear in the candidate app, nor anything that hints at them.
  Candidates are told their evidence is assessed, and the assessment stays in what a
  candidate can export (a GDPR access request). Claim support is shown as counts, not
  one score, until Ivar decides how to combine findings.
- **Rubrics are hidden from candidates**, minimum levels included: candidates never
  see criteria, weights or minimum levels, and the job board has no filter by skill
  level (2026-11-27).
- **Anonymous until revealed.** Before a reveal, employers see no name, contact
  details, quotes or role summaries; connecting to a job is the candidate's consent to
  be ranked and revealed.
- **Asking about a revealed candidate (LLM)** (2026-11-27): the candidate app doesn't
  mention it; the privacy notice says revealed candidates' material is used for
  employers' conversations with an assistant. Conversations aren't saved and aren't
  part of a candidate's export.
- **Aliases are per job** (2026-11-27, task 21): a candidate's alias and avatar come
  from their profile id and the job's id together, so they differ on every job and
  two employers can't link them; within one job they're the same in every view.
