"""The candidate side of the app: material, review, questions and profile.

The assessment of a candidate's skills (estimates and claim support) runs in the
background and is never shown in these steps; the developer view adds an internal
Assessment page with it.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from unapply.app import common, demo, forms
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
    LLMError,
)
from unapply.review import ReviewError, apply_review_sheet
from unapply.schemas import Profile, SkillCategory, SourceKind, WorkMode
from unapply.workspace import Workspace, data_dir

STEPS = ["Material", "Review", "Questions", "Profile"]
INTERNAL = "Assessment"
ICONS = {
    "Material": ":material/upload_file:",
    "Review": ":material/edit_note:",
    "Questions": ":material/forum:",
    "Profile": ":material/badge:",
    INTERNAL: ":material/lock:",
}
UPLOAD_TYPES = ["pdf", "md", "txt", "tex", "yaml", "yml", "json", "zip"]
TRANSPARENCY = (
    "Your evidence is assessed to match you with jobs. You can ask for that "
    "assessment at any time."
)


def welcome() -> None:
    """Explain the app before a candidate is chosen."""
    st.title("Apply without applying", anchor=False)
    st.markdown(
        "Upload your material once. We turn it into a profile you check and "
        "approve, ask a few questions where your documents say too little, and "
        "match you with jobs. You write application material only when an "
        "employer asks for it."
    )
    cols = st.columns(3)
    for col, (icon, title, text) in zip(
        cols,
        [
            (
                ":material/upload_file:",
                "1. Upload",
                "Your CV, other documents, a LinkedIn export and your GitHub.",
            ),
            (
                ":material/edit_note:",
                "2. Review",
                "Check what was extracted, rate your own skills and approve.",
            ),
            (
                ":material/forum:",
                "3. Answer",
                "A few questions about skills your documents don't show well.",
            ),
        ],
        strict=True,
    ):
        with col.container(border=True, height="stretch"):
            st.markdown(f"#### {icon} {title}")
            st.caption(text)
    st.caption(
        "Choose a candidate or create one in the sidebar, or try the John Doe demo, "
        "which costs nothing."
    )


def _interviewed(profile: Profile) -> bool:
    return any(
        s.kind == SourceKind.INTERVIEW and s.uri == "interview" for s in profile.sources
    )


def steps_done(ws: Workspace) -> set[str]:
    """List the candidate's finished steps, for the step selector."""
    profile = ws.profile()
    if profile is None:
        return set()
    done = {"Material"}
    if profile.approved_by_candidate_at:
        done |= {"Review", "Profile"}
    if _interviewed(profile):
        done.add("Questions")
    if profile.claim_support is not None and not skills_without_estimate(profile):
        done.add(INTERNAL)
    return done


def _need_profile(ws: Workspace) -> Profile | None:
    profile = ws.profile()
    if profile is None:
        st.info(
            "Extract a profile from your material first.",
            icon=":material/upload_file:",
        )
    return profile


def _estimate(ws: Workspace, profile: Profile, names: set[str] | None) -> Profile:
    """Estimate skills and recompute claim support; return the updated profile."""
    result = estimate_skills(profile, common.model(ws, "estimate", profile), names)
    return result.profile.model_copy(
        update={"claim_support": claim_support(result.profile)}
    )


def material_page(ws: Workspace) -> None:
    """Upload material and extract a draft profile."""
    st.header("Your material", anchor=False)
    st.caption(
        "Your CV and anything else about your work. From a LinkedIn data export (the "
        "zip) only profile sections are read, never messages or connections."
    )
    files = sorted(ws.material.iterdir()) if ws.material.exists() else []
    add, current = st.columns([3, 2], gap="large")
    with add:
        if common.is_demo(ws):
            st.info(
                "The demo's material is fixed, so the recorded answers fit it.",
                icon=":material/play_circle:",
            )
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
            settings = ws.settings()
            github = st.text_input(
                "GitHub username (optional)",
                value=settings.get("github") or "",
                placeholder="octocat",
            )
            if github.strip() != (settings.get("github") or ""):
                ws.save_settings({**settings, "github": github.strip() or None})
    with current, st.container(border=True):
        st.markdown("**Your files**")
        if not files:
            st.caption("No files yet.")
        for f in files:
            with st.container(horizontal=True, vertical_alignment="center"):
                st.markdown(f":material/description: {f.name}")
                st.caption(f"{f.stat().st_size / 1024:.0f} KB")
                if not common.is_demo(ws):
                    st.button(
                        "Remove",
                        key=f"remove_{f.name}",
                        icon=":material/delete:",
                        type="tertiary",
                        on_click=f.unlink,
                    )
        if github := ws.settings().get("github"):
            st.markdown(f":material/code: github.com/{github}")

    st.space("small")
    if ws.profile() is not None:
        st.warning(
            "Extracting again replaces your profile, including your review and "
            "answers. Earlier versions are kept in the history.",
            icon=":material/history:",
        )
    if common.model_button(
        ws, "Extract my profile", "extract", "extract", ":material/auto_awesome:"
    ):
        _extract(ws)


def _extract(ws: Workspace) -> None:
    documents = load_path(ws.material)
    if github := ws.settings().get("github"):
        fetch = cached_fetcher(data_dir() / ".cache" / "github")
        documents.append(fetch_github(github, fetch=fetch))
    if not documents:
        st.error("Add some material first.")
        return
    with st.spinner("Reading your material. This can take a few minutes."):
        try:
            result = extract_profile(documents, common.model(ws, "extract"))
        except LLMError as e:
            st.error(f"Extraction failed: {e}")
            return
    ws.save_profile(result.profile, "extracted")
    ws.save_pending_questions(None)
    p = result.profile
    st.session_state["flash"] = (
        f"Found {len(p.experiences)} experiences and {len(p.skills)} skills, each "
        "backed by a quote from your material. Check them in the Review step."
    )
    st.session_state["goto_step"] = "Review"
    st.rerun()


def review_page(ws: Workspace) -> None:
    """Check and correct the draft, rate your own skills and approve."""
    profile = _need_profile(ws)
    if profile is None:
        return
    st.header("Review your profile", anchor=False)
    st.caption(
        "Rate the skills you want employers to see, untick anything that's wrong, "
        "and add what's missing. Employers only see approved profiles."
    )
    if common.is_demo(ws) and st.button(
        "Fill in John's review", key="john_review", icon=":material/play_circle:"
    ):
        _save_review(ws, profile, demo.john_review_sheet(profile))

    # Keys change with every save, so the widgets show the saved profile.
    v = len(ws.history())
    headline = st.text_input("Headline", value=profile.headline, key=f"headline_{v}")
    skills_tab, experience_tab, add_tab, prefs_tab = st.tabs(
        [
            f":material/psychology: Skills ({len(profile.skills)})",
            f":material/work_history: Experience ({len(profile.experiences)})",
            ":material/add: Add skills",
            ":material/tune: Preferences",
        ]
    )
    with skills_tab:
        st.caption(
            "Your level: 1 aware, 2 basic, 3 working, 4 advanced, 5 expert. Leave it "
            "empty for skills you don't want to rate."
        )
        skills = st.data_editor(
            pd.DataFrame(forms.skill_rows(profile)),
            key=f"skills_{v}",
            hide_index=True,
            disabled=["name", "evidence"],
            column_order=["keep", "name", "level", "category", "evidence"],
            column_config={
                "keep": st.column_config.CheckboxColumn("Keep", width="small"),
                "name": st.column_config.TextColumn("Skill", width="medium"),
                "level": st.column_config.SelectboxColumn(
                    "Your level",
                    options=[forms.NO_LEVEL, *forms.LEVEL_LABELS],
                    width="small",
                ),
                "category": st.column_config.SelectboxColumn(
                    "Category", options=[c.value for c in SkillCategory], width="small"
                ),
                "evidence": st.column_config.TextColumn(
                    "Evidence from your material", width="large"
                ),
            },
        )
    with experience_tab:
        experiences = st.data_editor(
            pd.DataFrame(forms.experience_rows(profile)),
            key=f"experiences_{v}",
            hide_index=True,
            disabled=["id"],
            column_config={
                "id": None,
                "keep": st.column_config.CheckboxColumn("Keep", width="small"),
                "title": st.column_config.TextColumn("Title", width="medium"),
                "organisation": st.column_config.TextColumn("Organisation"),
                "start": st.column_config.TextColumn(
                    "Start", help="YYYY or YYYY-MM", width="small"
                ),
                "end": st.column_config.TextColumn(
                    "End", help="YYYY or YYYY-MM; empty means now", width="small"
                ),
                "summary": st.column_config.TextColumn("Summary", width="large"),
            },
        )
    with add_tab:
        st.caption(
            "Say where you used each one. Skills you add are kept as your own "
            "statements."
        )
        added = st.data_editor(
            pd.DataFrame(columns=["name", "category", "level", "note"]),
            key=f"added_{v}",
            num_rows="dynamic",
            hide_index=True,
            column_config={
                "name": st.column_config.TextColumn("Skill"),
                "category": st.column_config.SelectboxColumn(
                    "Category", options=[c.value for c in SkillCategory]
                ),
                "level": st.column_config.SelectboxColumn(
                    "Your level", options=forms.LEVEL_LABELS
                ),
                "note": st.column_config.TextColumn("Where you used it", width="large"),
            },
        )
    with prefs_tab:
        prefs = profile.preferences
        left, right = st.columns(2, gap="large")
        locations = left.text_input(
            "Locations",
            value=", ".join(prefs.locations),
            key=f"loc_{v}",
            help="Comma-separated, such as Copenhagen, Aarhus.",
        )
        modes = right.pills(
            "Work modes",
            [m.value for m in WorkMode],
            selection_mode="multi",
            default=[m.value for m in prefs.work_modes],
            key=f"modes_{v}",
        )
        permits = left.text_input(
            "Work permits",
            value=", ".join(prefs.work_permits),
            key=f"permits_{v}",
            help="Comma-separated country codes, or EU.",
        )
        salary_col, currency_col = right.columns([2, 1])
        salary = salary_col.number_input(
            "Minimum yearly salary",
            min_value=0,
            value=prefs.salary_min,
            step=10000,
            key=f"salary_{v}",
            placeholder="Not stated",
        )
        currency = currency_col.text_input(
            "Currency",
            value=prefs.salary_currency or "",
            key=f"currency_{v}",
            placeholder="DKK",
        )
        dealbreakers = st.text_area(
            "Dealbreakers",
            value="\n".join(prefs.dealbreakers),
            key=f"dealbreakers_{v}",
            help="One per line.",
        )

    with st.container(border=True, horizontal=True, vertical_alignment="center"):
        approve = st.toggle(
            "My profile is right; I approve it",
            value=profile.approved_by_candidate_at is not None,
            key=f"approve_{v}",
        )
        if st.button("Save", key="save_review", type="primary", icon=":material/save:"):
            sheet = forms.review_sheet(
                profile,
                headline=headline,
                preferences={
                    "locations": common.split(locations, ","),
                    "work_modes": list(modes or []),
                    "work_permits": common.split(permits, ","),
                    "salary_min": int(salary) if salary else None,
                    "salary_currency": currency.strip() or None,
                    "dealbreakers": common.split(dealbreakers, "\n"),
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
        st.error(f"Not saved: {e}", icon=":material/error:")
        return
    # Levels may have changed, so findings are recomputed (no model call).
    if any(s.estimate for s in reviewed.skills):
        reviewed = reviewed.model_copy(
            update={"claim_support": claim_support(reviewed)}
        )
    ws.save_profile(reviewed, "reviewed")
    rated = sum(s.self_level is not None for s in reviewed.skills)
    if reviewed.approved_by_candidate_at:
        st.session_state["flash"] = (
            f"Approved: {len(reviewed.skills)} skills, {rated} with your level. "
            "Next, a few questions."
        )
        st.session_state["goto_step"] = "Questions"
    else:
        st.session_state["flash"] = "Saved. Approve your profile when it's right."
    st.rerun()


def questions_page(ws: Workspace) -> None:
    """Answer questions about skills your documents don't show enough of."""
    profile = _need_profile(ws)
    if profile is None:
        return
    st.header("A few questions", anchor=False)
    if profile.approved_by_candidate_at is None:
        st.info(
            "Approve your profile first (step: Review).", icon=":material/edit_note:"
        )
        return
    questions = ws.pending_questions()
    if questions is not None:
        _answer_form(ws, profile, questions)
        return

    st.caption(
        "We ask about skills your documents say little about. Specific answers help "
        "most: what you did, at roughly what scale, in which role and when. Answers "
        "are kept as your own statements, next to the question."
    )
    st.caption(TRANSPARENCY)
    label = "Ask me more questions" if _interviewed(profile) else "Prepare my questions"
    if common.model_button(
        ws, label, "questions", "prepare_questions", ":material/forum:"
    ):
        _prepare_questions(ws, profile)
    _past_answers(profile)


def _prepare_questions(ws: Workspace, profile: Profile) -> None:
    with st.spinner("Preparing your questions."):
        try:
            missing = skills_without_estimate(profile)
            if missing or profile.claim_support is None:
                profile = _estimate(ws, profile, missing)
                ws.save_profile(profile, "assessed")
            topics = select_topics(profile, MAX_QUESTIONS)
            if not topics:
                st.session_state["flash"] = (
                    "No questions for now: your documents cover what you rated."
                )
                st.rerun()
            questions = write_questions(profile, topics, common.model(ws, "questions"))
        except LLMError as e:
            st.error(f"Couldn't prepare questions: {e}", icon=":material/error:")
            return
    ws.save_pending_questions(
        [
            {"skill": q.skill, "reason": q.reason.value, "text": q.text}
            for q in questions
        ]
    )
    st.rerun()


def _answer_form(ws: Workspace, profile: Profile, questions: list[dict]) -> None:
    st.caption(
        f"{len(questions)} questions. Answer the ones you can and leave the rest empty."
    )
    if common.is_demo(ws) and st.button(
        "Fill in John's answers", key="john_answers", icon=":material/play_circle:"
    ):
        answers = demo.john_answers()
        for i, q in enumerate(questions):
            st.session_state[f"answer_{i}"] = answers.get(q["skill"], "")
        st.rerun()
    with st.form("interview", border=False):
        for i, q in enumerate(questions):
            with st.container(border=True):
                st.markdown(f"**{q['skill']}**")
                st.caption(WHY[Reason(q["reason"])])
                st.markdown(q["text"])
                st.text_area(
                    f"Your answer about {q['skill']}",
                    key=f"answer_{i}",
                    label_visibility="collapsed",
                    placeholder="Your answer (leave empty to skip)",
                )
        submitted = st.form_submit_button(
            "Submit answers", type="primary", icon=":material/send:"
        )
    if not common.is_demo(ws) and not common.allowed(ws):
        st.caption(
            "Paid API calls are off: answers are saved, and the assessment is updated "
            "once calls are allowed."
        )
    if st.button("Discard these questions", key="discard_questions", type="tertiary"):
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
        st.error(f"Not saved: {e}", icon=":material/error:")
        return
    ws.save_pending_questions(None)
    for i in range(len(questions)):
        st.session_state.pop(f"answer_{i}", None)
    if not n:
        st.session_state["flash"] = "No answers given; nothing changed."
        st.rerun()
    ws.save_profile(updated, "interviewed")
    # Update the assessment of the answered skills, in the background.
    if common.allowed(ws):
        with st.spinner("Saving your answers."):
            try:
                assessed = _estimate(ws, updated, skills_without_estimate(updated))
                ws.save_profile(assessed, "assessed")
            except LLMError:
                pass  # Answers are saved; the assessment is updated next time.
    st.session_state["flash"] = f"Thank you. {n} answers saved to your profile."
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
    st.subheader("Your answers", anchor=False)
    by_evidence = {i: s.name for s in profile.skills for i in s.evidence_ids}
    for e in answers:
        with st.container(border=True):
            st.markdown(f"**{by_evidence.get(e.id, '?')}**")
            st.caption(e.locator)
            st.markdown(e.quote)


def profile_page(ws: Workspace) -> None:
    """Show the profile as the candidate sees it: no assessment."""
    full = _need_profile(ws)
    if full is None:
        return
    profile = forms.candidate_view(full)
    st.header(profile.headline or "Your profile", anchor=False)
    with st.container(horizontal=True):
        if profile.approved_by_candidate_at:
            st.badge(
                f"Approved {profile.approved_by_candidate_at:%d %b %Y}",
                icon=":material/verified:",
                color="green",
            )
        else:
            st.badge("Not approved yet", icon=":material/pending:", color="orange")
        st.badge(f"{len(profile.experiences)} experiences", color="gray")
        st.badge(f"{len(profile.skills)} skills", color="gray")

    p = profile.preferences
    looking = [
        ("Where", ", ".join(p.locations) or "anywhere"),
        ("How", ", ".join(m.value for m in p.work_modes) or "any work mode"),
        ("Work permits", ", ".join(p.work_permits) or "not stated"),
        (
            "Minimum salary",
            f"{p.salary_min:,} {p.salary_currency or ''}".strip()
            if p.salary_min
            else "not stated",
        ),
        ("Dealbreakers", "; ".join(p.dealbreakers) or "none"),
    ]
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader("Experience", anchor=False)
        for x in profile.experiences:
            when = forms.period(x.start, x.end)
            line = f"**{x.title}** · {x.organisation}"
            st.markdown(line + (f"  \n:gray[{when}]" if when else ""))
            if x.summary:
                st.caption(x.summary)
    with right:
        st.subheader("Looking for", anchor=False)
        with st.container(border=True):
            for label, value in looking:
                st.markdown(f":gray[{label}]  \n{value}")

    st.subheader("Skills", anchor=False)
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "skill": s.name,
                    "category": s.category.value if s.category else "",
                    "your level": forms.level_label(s.self_level),
                }
                for s in profile.skills
            ]
        ),
        hide_index=True,
        column_config={"your level": st.column_config.TextColumn("Your level")},
    )
    st.caption(TRANSPARENCY)
    with st.container(horizontal=True, vertical_alignment="center"):
        st.download_button(
            "Download my profile",
            profile.model_dump_json(indent=2),
            file_name=f"{ws.name}-profile.json",
            mime="application/json",
            icon=":material/download:",
        )
        with st.popover("History", icon=":material/history:"):
            for i, step in enumerate(ws.history(), start=1):
                st.write(f"{i}. {step}")


def assessment_page(ws: Workspace) -> None:
    """Show the internal assessment. Never part of the candidate's steps."""
    st.header("Assessment", anchor=False)
    st.warning(
        "Internal. Candidates don't see this page, the estimates or the findings.",
        icon=":material/lock:",
    )
    profile = _need_profile(ws)
    if profile is None:
        return
    missing = skills_without_estimate(profile)
    with st.container(horizontal=True, vertical_alignment="center"):
        redo = st.toggle("Re-estimate every skill", key="redo_all")
    count = len(profile.skills) if redo else len(missing)
    if count == 0:
        st.caption("Every skill has an estimate.")
    elif common.model_button(
        ws, f"Estimate {count} skills", "estimate", "estimate", ":material/calculate:"
    ):
        with st.spinner("Estimating."):
            try:
                estimated = _estimate(ws, profile, None if redo else missing)
            except LLMError as e:
                st.error(f"Estimation failed: {e}", icon=":material/error:")
                return
        ws.save_profile(estimated, "assessed")
        st.session_state["flash"] = f"Estimated. {summary(estimated.claim_support)}."
        st.rerun()

    support = profile.claim_support
    if support is None:
        return
    cols = st.columns(4)
    for col, (label, names, help_text) in zip(
        cols,
        [
            ("Overclaims", support.overclaims, "Rated clearly above a sure estimate"),
            ("Unverified", support.unverified, "Rated above; the evidence says little"),
            ("Underclaims", support.underclaims, "Rated clearly below a sure estimate"),
            ("Own statement only", support.unsupported_claims, "No document evidence"),
        ],
        strict=True,
    ):
        col.metric(label, len(names), help=help_text, border=True)
    st.caption(summary(support))
    rows = forms.finding_rows(profile)
    if st.toggle("Only skills with a finding", key="findings_only"):
        rows = [r for r in rows if r["finding"]]
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        column_config={
            "skill": st.column_config.TextColumn("Skill"),
            "category": st.column_config.TextColumn("Category"),
            "yours": st.column_config.NumberColumn("Theirs", width="small"),
            "estimate": st.column_config.NumberColumn("Estimate", width="small"),
            "confidence": st.column_config.ProgressColumn(
                "Confidence", min_value=0.0, max_value=1.0, format="%.2f"
            ),
            "finding": st.column_config.TextColumn("Finding", width="medium"),
            "reason": st.column_config.TextColumn("Reason", width="large"),
        },
    )


PAGES = {
    "Material": material_page,
    "Review": review_page,
    "Questions": questions_page,
    "Profile": profile_page,
    INTERNAL: assessment_page,
}
