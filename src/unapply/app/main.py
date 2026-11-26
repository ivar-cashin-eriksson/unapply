"""The unapply candidate app. Run with `unapply app`.

Every step a candidate takes, in order: material, review, estimate, interview and the
resulting profile. Paid API calls are off unless the sidebar toggle is turned on in
this session; demo workspaces replay recorded answers and never call the API.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from dotenv import find_dotenv, load_dotenv

from unapply.app import demo, forms
from unapply.estimation.claims import claim_support, summary
from unapply.estimation.skills import estimate_skills, skills_without_estimate
from unapply.ingest.documents import load_path
from unapply.ingest.extract import extract_profile
from unapply.ingest.github import cached_fetcher, fetch_github
from unapply.interview.questions import (
    MAX_QUESTIONS,
    WHY,
    Reason,
    select_topics,
    write_questions,
)
from unapply.interview.sheet import InterviewError, apply_interview_sheet
from unapply.llm import (
    DEFAULT_MODEL,
    QUESTION_MODEL,
    AnthropicLLM,
    LLMError,
    StructuredLLM,
    logged_spend,
)
from unapply.review import ReviewError, apply_review_sheet
from unapply.schemas import Profile, SkillCategory, SourceKind, WorkMode
from unapply.workspace import Workspace, data_dir

STEPS = ["Material", "Review", "Estimate", "Interview", "Profile"]
UPLOAD_TYPES = ["pdf", "md", "txt", "tex", "yaml", "yml", "json", "zip"]
COST = {
    "extract": "Claude Opus 5.5, roughly $0.10 to $1 depending on the material",
    "estimate": "Claude Opus 5.5, roughly $0.03 to $0.15",
    "questions": "Claude Sonnet 5.5, about $0.01",
}


def main() -> None:
    """Draw the app."""
    load_dotenv(find_dotenv(usecwd=True))
    st.set_page_config(page_title="unapply", layout="wide")
    ws = sidebar()
    if ws is None:
        st.title("unapply")
        st.write(
            "Upload your material once, check what was extracted, see how your own "
            "levels compare with what your evidence shows, and answer a few questions "
            "where it shows too little. Choose or create a candidate in the sidebar, "
            "or load the free John Doe demo."
        )
        return
    step = st.session_state.get("step", STEPS[0])
    if flash := st.session_state.pop("flash", None):
        st.success(flash)
    {
        "Material": material_page,
        "Review": review_page,
        "Estimate": estimate_page,
        "Interview": interview_page,
        "Profile": profile_page,
    }[step](ws)


# --- Sidebar and shared helpers -------------------------------------------------


def sidebar() -> Workspace | None:
    """Choose the workspace, the step and whether paid API calls are allowed."""
    with st.sidebar:
        st.title("unapply")
        names = Workspace.names()
        current = st.session_state.get("workspace")
        choice = st.selectbox(
            "Candidate",
            names,
            index=names.index(current) if current in names else None,
            placeholder="Choose a candidate",
            key="workspace_choice",
        )
        if choice and choice != current:
            st.session_state["workspace"] = choice
            st.session_state["step"] = STEPS[0]
            st.rerun()
        with st.expander("New candidate"):
            name = st.text_input(
                "Name", key="new_name", help="Lowercase, e.g. jane-doe"
            )
            if st.button("Create", key="create"):
                try:
                    _open(Workspace.create(name.strip()))
                except ValueError as e:
                    st.error(str(e))
            if demo.available() and st.button(
                "Load the John Doe demo (free)", key="demo"
            ):
                _open(demo.create_demo())

        if current not in names:
            return None
        ws = Workspace(data_dir() / current)
        st.divider()
        done = _steps_done(ws)
        st.radio(
            "Step",
            STEPS,
            key="step",
            format_func=lambda s: f"{'✓' if s in done else '○'} {s}",
        )
        st.divider()
        if _is_demo(ws):
            st.info("Demo: recorded answers are replayed. No API calls are made.")
        else:
            st.toggle(
                "Allow paid API calls",
                value=False,
                key="allow_api",
                help="Off in every new session. Buttons that call Claude say so.",
            )
            calls, cost = logged_spend()
            st.caption(f"Logged API calls: {calls}, about ${cost:.2f} in total.")
        return ws


def _open(ws: Workspace) -> None:
    st.session_state["workspace"] = ws.name
    st.session_state["step"] = STEPS[0]
    st.rerun()


def _is_demo(ws: Workspace) -> bool:
    return bool(ws.settings().get("demo"))


def _steps_done(ws: Workspace) -> set[str]:
    profile = ws.profile()
    if profile is None:
        return set()
    done = {"Material"}
    if profile.approved_by_candidate_at:
        done.add("Review")
    if profile.claim_support is not None and not skills_without_estimate(profile):
        done.add("Estimate")
    if any(
        s.kind == SourceKind.INTERVIEW and s.uri == "interview" for s in profile.sources
    ):
        done.add("Interview")
    if {"Review", "Estimate"} <= done:
        done.add("Profile")
    return done


def _model(
    ws: Workspace, purpose: str, profile: Profile | None = None
) -> StructuredLLM | None:
    """Pick the model for a step; None if paid calls aren't allowed now."""
    if _is_demo(ws):
        return demo.demo_llm(purpose, profile)
    if not st.session_state.get("allow_api"):
        return None
    if purpose == "questions":
        return AnthropicLLM(QUESTION_MODEL, "medium", allow=True)
    return AnthropicLLM(DEFAULT_MODEL, "high", allow=True)


def _model_button(ws: Workspace, label: str, purpose: str, key: str, **kwargs) -> bool:  # noqa: ANN003
    """Draw a button for a step that calls the model, disabled unless allowed."""
    allowed = _is_demo(ws) or st.session_state.get("allow_api", False)
    note = "replays a recorded answer" if _is_demo(ws) else f"calls {COST[purpose]}"
    clicked = st.button(
        label,
        key=key,
        type="primary",
        disabled=not allowed,
        help=None
        if allowed
        else "Turn on 'Allow paid API calls' in the sidebar first.",
        **kwargs,
    )
    st.caption(note if allowed else f"Paid API calls are off; this {note}.")
    return clicked


def _need_profile(ws: Workspace) -> Profile | None:
    profile = ws.profile()
    if profile is None:
        st.info("Extract a profile from your material first (step: Material).")
    return profile


# --- Steps ----------------------------------------------------------------------


def material_page(ws: Workspace) -> None:
    """Upload material and extract a draft profile."""
    st.header("1. Your material")
    st.write(
        "Add your CV and anything else about your work: other documents, notes, a "
        "LinkedIn data export (the zip) and your GitHub username. Only profile "
        "sections of a LinkedIn export are read, never messages or connections."
    )
    files = sorted(ws.material.iterdir()) if ws.material.exists() else []
    if _is_demo(ws):
        st.caption("Demo material is fixed, so the recorded answers fit it.")
    else:
        n = st.session_state.get("upload_round", 0)
        uploads = st.file_uploader(
            "Add files",
            type=UPLOAD_TYPES,
            accept_multiple_files=True,
            key=f"upload_{n}",
        )
        if uploads:
            for f in uploads:
                (ws.material / f.name).write_bytes(f.getvalue())
            st.session_state["upload_round"] = n + 1
            st.rerun()

    for f in files:
        left, right = st.columns([6, 1])
        left.write(f"📄 {f.name} ({f.stat().st_size / 1024:.0f} KB)")
        if not _is_demo(ws) and right.button("Remove", key=f"remove_{f.name}"):
            f.unlink()
            st.rerun()
    if not files:
        st.caption("No material yet.")

    settings = ws.settings()
    if not _is_demo(ws):
        github = st.text_input(
            "GitHub username (optional)", value=settings.get("github") or ""
        )
        if github.strip() != (settings.get("github") or ""):
            ws.save_settings({**settings, "github": github.strip() or None})

    st.divider()
    profile = ws.profile()
    if profile is not None:
        st.warning(
            "Extracting again replaces your current profile, including your review, "
            "estimates and answers. Earlier versions stay in the history."
        )
    if _model_button(ws, "Extract my profile", "extract", key="extract"):
        _extract(ws)


def _extract(ws: Workspace) -> None:
    llm = _model(ws, "extract")
    if llm is None:
        return
    documents = load_path(ws.material)
    if github := ws.settings().get("github"):
        documents.append(
            fetch_github(github, fetch=cached_fetcher(data_dir() / ".cache" / "github"))
        )
    if not documents:
        st.error("Add some material first.")
        return
    with st.spinner(
        "Reading your material and extracting a profile; this can take a few minutes."
    ):
        try:
            result = extract_profile(documents, llm)
        except LLMError as e:
            st.error(f"Extraction failed: {e}")
            return
    ws.save_profile(result.profile, "extracted")
    ws.save_pending_questions(None)
    p = result.profile
    st.session_state["flash"] = (
        f"Extracted {len(p.experiences)} experiences and {len(p.skills)} skills, backed "
        f"by {len(p.evidence)} quotes. {len(result.rejected_quotes)} quotes weren't found "
        f"in their source and were dropped. Check everything on the Review step."
    )
    st.rerun()


def review_page(ws: Workspace) -> None:
    """Check and correct the draft, rate your own skills and approve."""
    st.header("2. Review your profile")
    profile = _need_profile(ws)
    if profile is None:
        return
    st.write(
        "Set your own level on the skills you want employers to see (1 aware, 2 basic, "
        "3 working, 4 advanced, 5 expert), untick anything that's wrong, correct your "
        "experiences and add skills that are missing. Employers only see approved "
        "profiles."
    )
    if _is_demo(ws) and st.button("Fill in John's review (demo)", key="john_review"):
        _save_review(ws, profile, demo.john_review_sheet(profile))

    # Keys change with every save, so the tables show the saved profile.
    version = len(ws.history())
    headline = st.text_input(
        "Headline", value=profile.headline, key=f"headline_{version}"
    )
    prefs = profile.preferences
    with st.expander("Preferences", expanded=False):
        locations = st.text_input(
            "Locations (comma-separated)",
            value=", ".join(prefs.locations),
            key=f"loc_{version}",
        )
        modes = st.multiselect(
            "Work modes",
            [m.value for m in WorkMode],
            default=[m.value for m in prefs.work_modes],
            key=f"modes_{version}",
        )
        permits = st.text_input(
            "Work permits (comma-separated, e.g. DK, EU)",
            value=", ".join(prefs.work_permits),
            key=f"permits_{version}",
        )
        left, right = st.columns(2)
        salary = left.number_input(
            "Minimum yearly salary",
            min_value=0,
            value=prefs.salary_min or 0,
            step=10000,
            key=f"salary_{version}",
        )
        currency = right.text_input(
            "Currency", value=prefs.salary_currency or "", key=f"currency_{version}"
        )
        dealbreakers = st.text_area(
            "Dealbreakers (one per line)",
            value="\n".join(prefs.dealbreakers),
            key=f"dealbreakers_{version}",
        )

    st.subheader("Experiences")
    experiences = st.data_editor(
        pd.DataFrame(forms.experience_rows(profile)),
        key=f"experiences_{version}",
        hide_index=True,
        width="stretch",
        disabled=["id"],
        column_config={
            "id": None,
            "keep": st.column_config.CheckboxColumn("Keep", width="small"),
            "start": st.column_config.TextColumn("Start", help="YYYY or YYYY-MM"),
            "end": st.column_config.TextColumn(
                "End", help="YYYY or YYYY-MM; empty means now"
            ),
        },
    )

    st.subheader("Skills")
    skills = st.data_editor(
        pd.DataFrame(forms.skill_rows(profile)),
        key=f"skills_{version}",
        hide_index=True,
        width="stretch",
        disabled=["name", "evidence"],
        column_config={
            "keep": st.column_config.CheckboxColumn("Keep", width="small"),
            "name": st.column_config.TextColumn("Skill"),
            "category": st.column_config.SelectboxColumn(
                "Category", options=[c.value for c in SkillCategory]
            ),
            "level": st.column_config.NumberColumn(
                "Your level",
                min_value=1,
                max_value=5,
                step=1,
                help="1 aware ... 5 expert",
            ),
            "evidence": st.column_config.TextColumn("Evidence", width="large"),
        },
    )

    st.subheader("Add missing skills")
    st.caption(
        "Say where you used each one. Added skills are kept as your own statements."
    )
    added = st.data_editor(
        pd.DataFrame(columns=["name", "category", "level", "note"]),
        key=f"added_{version}",
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            "category": st.column_config.SelectboxColumn(
                "category", options=[c.value for c in SkillCategory]
            ),
            "level": st.column_config.NumberColumn(
                "level", min_value=1, max_value=5, step=1
            ),
            "note": st.column_config.TextColumn("note", width="large"),
        },
    )

    approve = st.checkbox(
        "This profile is right; I approve it",
        value=profile.approved_by_candidate_at is not None,
        key=f"approve_{version}",
    )
    if st.button("Save review", key="save_review", type="primary"):
        sheet = forms.review_sheet(
            profile,
            headline=headline,
            preferences={
                "locations": _split(locations, ","),
                "work_modes": modes,
                "work_permits": _split(permits, ","),
                "salary_min": int(salary) or None,
                "salary_currency": currency.strip() or None,
                "dealbreakers": _split(dealbreakers, "\n"),
            },
            experiences=experiences.to_dict("records"),
            skills=skills.to_dict("records"),
            added=added.to_dict("records"),
            approve=approve,
        )
        _save_review(ws, profile, sheet)


def _save_review(ws: Workspace, profile: Profile, sheet: str) -> None:
    try:
        reviewed = apply_review_sheet(profile, sheet)
    except ReviewError as e:
        st.error(f"Not saved: {e}")
        return
    # Levels may have changed, so findings are recomputed (no model call).
    if any(s.estimate for s in reviewed.skills):
        reviewed = reviewed.model_copy(
            update={"claim_support": claim_support(reviewed)}
        )
    ws.save_profile(reviewed, "reviewed")
    rated = sum(s.self_level is not None for s in reviewed.skills)
    approved = "Approved." if reviewed.approved_by_candidate_at else "Not approved yet."
    st.session_state["flash"] = (
        f"Saved: {len(reviewed.experiences)} experiences, {len(reviewed.skills)} "
        f"skills, {rated} with your level. {approved}"
    )
    st.rerun()


def estimate_page(ws: Workspace) -> None:
    """Estimate levels from evidence and compare them with your own."""
    st.header("3. Your levels and the evidence")
    profile = _need_profile(ws)
    if profile is None:
        return
    st.write(
        "Each skill's level is estimated from its evidence alone, without seeing your "
        "own level, then compared with yours. You can see every estimate and why."
    )
    if profile.approved_by_candidate_at is None:
        st.caption("Your profile isn't approved yet; you can still estimate.")
    missing = skills_without_estimate(profile)
    redo = st.checkbox("Re-estimate every skill", key="redo_all", value=False)
    names = None if redo else missing
    count = len(profile.skills) if redo else len(missing)
    if count == 0:
        st.caption("Every skill has an estimate.")
    elif _model_button(ws, f"Estimate {count} skills", "estimate", key="estimate"):
        _estimate(ws, profile, names)

    if profile.claim_support is None:
        return
    support = profile.claim_support
    st.subheader("Findings")
    st.write(summary(support))
    cols = st.columns(4)
    cols[0].metric(
        "Overclaims",
        len(support.overclaims),
        help="Rated clearly above what the evidence shows",
    )
    cols[1].metric(
        "Unverified",
        len(support.unverified),
        help="Rated above the evidence, which says little either way",
    )
    cols[2].metric(
        "Underclaims", len(support.underclaims), help="Rated clearly below the evidence"
    )
    cols[3].metric("Only your statement", len(support.unsupported_claims))
    rows = forms.finding_rows(profile)
    if st.toggle("Only skills with a finding", key="findings_only"):
        rows = [r for r in rows if r["finding"]]
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
        column_config={
            "confidence": st.column_config.ProgressColumn(
                "Confidence", min_value=0.0, max_value=1.0, format="%.2f"
            ),
            "reason": st.column_config.TextColumn("Reason", width="large"),
        },
    )
    if support.unverified or support.unsupported_claims:
        st.info(
            "The Interview step asks about unverified skills and your own statements."
        )


def _estimate(ws: Workspace, profile: Profile, names: set[str] | None) -> None:
    llm = _model(ws, "estimate", profile)
    if llm is None:
        return
    with st.spinner("Estimating levels from your evidence."):
        try:
            result = estimate_skills(profile, llm, names)
        except LLMError as e:
            st.error(f"Estimation failed: {e}")
            return
    estimated = result.profile.model_copy(
        update={"claim_support": claim_support(result.profile)}
    )
    ws.save_profile(estimated, "estimated")
    flash = f"Estimated. {summary(estimated.claim_support)}."
    if result.problems:
        flash += f" Problems with the model's answer: {'; '.join(result.problems)}"
    st.session_state["flash"] = flash
    st.rerun()


def interview_page(ws: Workspace) -> None:
    """Answer questions about skills your documents don't show enough of."""
    st.header("4. A few questions")
    profile = _need_profile(ws)
    if profile is None:
        return
    if profile.claim_support is None:
        st.info(
            "Estimate your levels first (step: Estimate); the questions build on it."
        )
        return
    questions = ws.pending_questions()
    if questions is None:
        st.write(
            "Questions are chosen for skills you rate higher than your documents "
            "show, and for skills only your own statement backs. Specific answers "
            "(what you did, at what scale, in which role, when) help most. They are "
            "kept as your own statements."
        )
        limit = st.number_input("At most", 1, 15, MAX_QUESTIONS, key="max_questions")
        topics = select_topics(profile, int(limit))
        if not topics:
            st.success(
                "Nothing to ask: your rated skills are supported or already asked about."
            )
        elif _model_button(
            ws, f"Write {len(topics)} questions", "questions", key="write_questions"
        ):
            _write_questions(ws, profile, topics)
        _past_answers(profile)
        return

    if _is_demo(ws) and st.button("Fill in John's answers (demo)", key="john_answers"):
        answers = demo.john_answers()
        for i, q in enumerate(questions):
            st.session_state[f"answer_{i}"] = answers.get(q["skill"], "")
        st.rerun()
    with st.form("interview"):
        for i, q in enumerate(questions):
            st.markdown(f"**{q['skill']}**")
            st.caption(WHY[Reason(q["reason"])])
            st.write(q["text"])
            st.text_area("Your answer (leave empty to skip)", key=f"answer_{i}")
        submitted = st.form_submit_button("Submit answers", type="primary")
    if st.button("Discard these questions", key="discard_questions"):
        ws.save_pending_questions(None)
        st.rerun()
    if submitted:
        _submit_answers(ws, profile, questions)


def _submit_answers(ws: Workspace, profile: Profile, questions: list[dict]) -> None:
    answers = {
        q["skill"]: st.session_state.get(f"answer_{i}", "")
        for i, q in enumerate(questions)
    }
    try:
        updated, n = apply_interview_sheet(
            profile, forms.interview_sheet(profile, questions, answers)
        )
    except InterviewError as e:
        st.error(f"Not saved: {e}")
        return
    ws.save_pending_questions(None)
    for i in range(len(questions)):
        st.session_state.pop(f"answer_{i}", None)
    if n:
        ws.save_profile(updated, "interviewed")
        st.session_state["flash"] = (
            f"{n} answers added. Re-estimate the answered skills on the Estimate step."
        )
    else:
        st.session_state["flash"] = "No answers given; nothing changed."
    st.rerun()


def _write_questions(ws: Workspace, profile: Profile, topics: list) -> None:
    llm = _model(ws, "questions", profile)
    if llm is None:
        return
    with st.spinner("Writing questions."):
        try:
            questions = write_questions(profile, topics, llm)
        except LLMError as e:
            st.error(f"Couldn't write questions: {e}")
            return
    ws.save_pending_questions(
        [
            {"skill": q.skill, "reason": q.reason.value, "text": q.text}
            for q in questions
        ]
    )
    st.rerun()


def _past_answers(profile: Profile) -> None:
    interviews = {
        s.id
        for s in profile.sources
        if s.kind == SourceKind.INTERVIEW and s.uri == "interview"
    }
    answers = [e for e in profile.evidence if e.source_id in interviews]
    if not answers:
        return
    st.subheader("Your earlier answers")
    by_evidence = {i: s.name for s in profile.skills for i in s.evidence_ids}
    for e in answers:
        st.markdown(f"**{by_evidence.get(e.id, '?')}**: {e.locator}")
        st.write(f"> {e.quote}")


def profile_page(ws: Workspace) -> None:
    """Show the resulting profile, as employers would see it once revealed."""
    st.header("5. Your profile")
    profile = _need_profile(ws)
    if profile is None:
        return
    st.subheader(profile.headline or "(no headline)")
    status = (
        f"Approved {profile.approved_by_candidate_at:%Y-%m-%d %H:%M}"
        if profile.approved_by_candidate_at
        else "Not approved yet"
    )
    st.caption(
        f"{status} · {len(profile.experiences)} experiences · "
        f"{len(profile.skills)} skills"
    )
    if profile.claim_support is not None:
        st.write(f"**Claim support:** {summary(profile.claim_support)}")
    p = profile.preferences
    wanted = (
        f"**Looking for:** {', '.join(m.value for m in p.work_modes) or 'any work mode'}"
        f" in {', '.join(p.locations) or 'any location'}"
    )
    if p.salary_min:
        wanted += f", from {p.salary_min:,} {p.salary_currency or ''}".rstrip()
    if p.dealbreakers:
        wanted += f". Dealbreakers: {'; '.join(p.dealbreakers)}"
    st.write(wanted)
    st.subheader("Experience")
    for x in profile.experiences:
        start = forms.month(x.start) or "?"
        end = forms.month(x.end) or "now"
        st.markdown(f"**{x.title}**, {x.organisation} ({start} to {end})")
        if x.summary:
            st.caption(x.summary)
    st.subheader("Skills")
    st.dataframe(
        pd.DataFrame(forms.finding_rows(profile)).drop(columns=["reason"]),
        hide_index=True,
        width="stretch",
    )
    st.download_button(
        "Download profile (JSON)",
        profile.model_dump_json(indent=2),
        file_name=f"{ws.name}-profile.json",
        mime="application/json",
    )
    with st.expander("History"):
        for i, step in enumerate(ws.history(), start=1):
            st.write(f"{i}. {step}")


def _split(text: str, sep: str) -> list[str]:
    return [part.strip() for part in text.split(sep) if part.strip()]


main()
