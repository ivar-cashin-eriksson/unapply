"""The employer side of the app: a job ad and its rubric.

The rubric is what candidates are scored against. Candidates never see it.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from unapply.app import common, forms
from unapply.jobs.extract import MAX_WEIGHT, MIN_WEIGHT, extract_job
from unapply.jobs.sheet import RubricError, apply_rubric_sheet
from unapply.llm import LLMError
from unapply.schemas import CriterionKind, Job, WorkMode
from unapply.workspace import Workspace

STEPS = ["Job ad", "Rubric"]
ICONS = {"Job ad": ":material/description:", "Rubric": ":material/checklist:"}


def welcome() -> None:
    """Explain the employer side before a job is chosen."""
    st.title("Hire from a shortlist", anchor=False)
    st.markdown(
        "Paste a job ad. We turn it into a rubric of hard filters and weighted "
        "criteria that you check and approve. Candidates who opt in are scored "
        "against it, and you see an explained, anonymised shortlist."
    )
    st.caption(
        "Choose a job or create one in the sidebar, or try the Fjord Grocery demo, "
        "which costs nothing."
    )


def steps_done(ws: Workspace) -> set[str]:
    """List the job's finished steps, for the step selector.

    Parameters
    ----------
    ws : Workspace
        The job workspace.

    Returns
    -------
    set of str
        Finished steps.
    """
    job = ws.job()
    if job is None:
        return set()
    return {"Job ad", "Rubric"} if job.rubric.approved_at else {"Job ad"}


def job_ad_page(ws: Workspace) -> None:
    """Paste or view the job ad and extract a rubric from it."""
    st.header("Job ad", anchor=False)
    st.caption(
        "Paste the ad as you would post it. The rubric is extracted from it, and every "
        "criterion quotes the ad."
    )
    job = ws.job()
    draft = ws.root / "ad.md"
    saved = (
        job.ad_text
        if job
        else (draft.read_text(encoding="utf-8") if draft.exists() else "")
    )
    left, right = st.columns(2, gap="large")
    company = left.text_input(
        "Company (optional)",
        value=job.company if job else "",
        key="job_company",
        help="Read from the ad if empty.",
    )
    title = right.text_input(
        "Job title (optional)",
        value=job.title if job else "",
        key="job_title",
        help="Read from the ad if empty.",
    )
    if common.is_demo(ws):
        st.info(
            "The demo's ad is fixed, so the recorded answer fits it.",
            icon=":material/play_circle:",
        )
    ad = st.text_area(
        "Job ad",
        value=saved,
        height=360,
        key="job_ad",
        disabled=common.is_demo(ws),
        placeholder="Paste the job ad here.",
    )
    if not common.is_demo(ws) and ad != saved:
        draft.write_text(ad, encoding="utf-8")
    if job is not None:
        st.warning(
            "Extracting again replaces the rubric, including your edits. Earlier "
            "versions are kept in the history.",
            icon=":material/history:",
        )
    if common.model_button(
        ws, "Extract the rubric", "rubric", "extract_rubric", ":material/auto_awesome:"
    ):
        _extract(ws, ad, company, title)


def _extract(ws: Workspace, ad: str, company: str, title: str) -> None:
    if not ad.strip():
        st.error("Paste the job ad first.")
        return
    with st.spinner("Reading the ad."):
        try:
            result = extract_job(
                ad,
                common.model(ws, "rubric"),
                company=company.strip() or None,
                title=title.strip() or None,
            )
        except LLMError as e:
            st.error(f"Extraction failed: {e}", icon=":material/error:")
            return
    ws.save_job(result.job, "extracted")
    musts = sum(c.kind == CriterionKind.MUST_HAVE for c in result.job.rubric.criteria)
    flash = (
        f"Found {musts} must-haves and {len(result.job.rubric.criteria) - musts} "
        "nice-to-haves, each quoting the ad. Check them in the Rubric step."
    )
    if result.dropped:
        flash += f" Dropped {len(result.dropped)}: {'; '.join(result.dropped)}."
    st.session_state["flash"] = flash
    st.session_state["goto_job_step"] = "Rubric"
    st.rerun()


def rubric_page(ws: Workspace) -> None:
    """Edit the hard filters and criteria, and approve the rubric."""
    job = ws.job()
    if job is None:
        st.info(
            "Extract a rubric from the job ad first.", icon=":material/description:"
        )
        return
    rubric = job.rubric
    st.header(f"{job.title}", anchor=False)
    with st.container(horizontal=True):
        st.badge(
            job.company or "Company not set", icon=":material/apartment:", color="gray"
        )
        st.badge(f"Version {rubric.version}", color="gray")
        if rubric.approved_at:
            st.badge(
                f"Approved {rubric.approved_at:%d %b %Y}",
                icon=":material/verified:",
                color="green",
            )
        else:
            st.badge("Draft", icon=":material/pending:", color="orange")
    st.caption(
        "Candidates are scored against this rubric. They never see it. Hard filters "
        "are pass/fail; criteria are weighted from 1 (minor) to 5 (essential)."
    )

    # Keys change with every save, so the widgets show the saved rubric.
    v = len(ws.history())
    f = rubric.hard_filters
    with st.container(border=True):
        st.markdown("**Hard filters**")
        left, right = st.columns(2, gap="large")
        locations = left.text_input(
            "Locations",
            value=", ".join(f.locations),
            key=f"rubric_locations_{v}",
            help="Comma-separated. Empty means anywhere.",
        )
        modes = right.pills(
            "Work modes",
            [m.value for m in WorkMode],
            selection_mode="multi",
            default=[m.value for m in f.work_modes],
            key=f"rubric_modes_{v}",
        )
        permits = left.text_input(
            "Required work permits",
            value=", ".join(f.required_work_permits),
            key=f"rubric_permits_{v}",
            help="Comma-separated country codes, or EU.",
        )
        years = right.number_input(
            "Minimum years of experience",
            min_value=0,
            max_value=50,
            value=f.min_years_experience,
            key=f"rubric_years_{v}",
            placeholder="No minimum",
        )

    st.markdown("**Criteria**")
    st.caption(
        "Add rows for criteria the ad doesn't state; delete rows to remove them."
    )
    rows = st.data_editor(
        pd.DataFrame(
            forms.criterion_rows(job),
            columns=["id", "kind", "description", "skill", "level", "weight", "quote"],
        ),
        key=f"criteria_{v}",
        num_rows="dynamic",
        hide_index=True,
        disabled=["id", "quote"],
        column_config={
            "id": None,
            "kind": st.column_config.SelectboxColumn(
                "Kind",
                options=list(forms.KIND_LABELS.values()),
                width="small",
                required=True,
                default=forms.KIND_LABELS["must_have"],
            ),
            "description": st.column_config.TextColumn("Criterion", width="medium"),
            "skill": st.column_config.TextColumn("Skill", width="small"),
            "level": st.column_config.SelectboxColumn(
                "Min. level",
                options=[forms.NO_LEVEL, *forms.LEVEL_LABELS],
                width="small",
                default=forms.NO_LEVEL,
            ),
            "weight": st.column_config.NumberColumn(
                "Weight",
                min_value=MIN_WEIGHT,
                max_value=MAX_WEIGHT,
                step=1,
                width="small",
                default=3,
            ),
            "quote": st.column_config.TextColumn("From the ad", width="large"),
        },
    )

    with st.container(border=True, horizontal=True, vertical_alignment="center"):
        approve = st.toggle(
            "The rubric is right; I approve it",
            value=rubric.approved_at is not None,
            key=f"rubric_approve_{v}",
        )
        if st.button("Save", key="save_rubric", type="primary", icon=":material/save:"):
            sheet = forms.rubric_sheet(
                job,
                company=job.company,
                title=job.title,
                filters={
                    "locations": common.split(locations, ","),
                    "work_modes": list(modes or []),
                    "required_work_permits": common.split(permits, ","),
                    "min_years_experience": int(years) if years is not None else None,
                },
                rows=rows.to_dict("records"),
                approve=approve,
            )
            _save(ws, job, sheet)


def _save(ws: Workspace, job: Job, sheet: str) -> None:
    try:
        updated = apply_rubric_sheet(job, sheet)
    except RubricError as e:
        st.error(f"Not saved: {e}", icon=":material/error:")
        return
    ws.save_job(updated, "rubric")
    r = updated.rubric
    state = "Approved" if r.approved_at else "Saved as a draft"
    st.session_state["flash"] = (
        f"{state}: version {r.version}, {len(r.criteria)} criteria."
    )
    st.rerun()


PAGES = {"Job ad": job_ad_page, "Rubric": rubric_page}
