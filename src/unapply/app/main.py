"""The unapply app. Run with `unapply app`.

Two sides, switched in the sidebar: candidates (material, review, questions,
profile) and employers (job ad, rubric). Paid API calls are off unless the sidebar
toggle is on in this session; demo workspaces replay recorded answers instead.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import streamlit as st
from dotenv import find_dotenv, load_dotenv

from unapply.app import candidate, common, demo, employer
from unapply.llm import logged_spend
from unapply.workspace import Workspace, data_dir, jobs_dir

SIDES = ["Candidate", "Employer"]


def main() -> None:
    """Draw the app."""
    load_dotenv(find_dotenv(usecwd=True))
    st.set_page_config(page_title="unapply", page_icon=":material/work:", layout="wide")
    # A workspace created or opened in the last run is selected before its
    # selectbox exists; Streamlit doesn't allow changing it afterwards.
    for pending, key, step in [
        ("open_workspace", "workspace", "step"),
        ("open_job", "job_workspace", "job_step"),
    ]:
        if opened := st.session_state.pop(pending, None):
            st.session_state[key] = opened
            st.session_state.pop(step, None)

    with st.sidebar:
        st.markdown("### :material/work: unapply")
        st.caption("Apply without applying")
        side = st.segmented_control(
            "Side",
            SIDES,
            key="side",
            default=SIDES[0],
            required=True,
            label_visibility="collapsed",
            width="stretch",
        )
        if side == "Employer":
            ws = _picker(
                "Job",
                jobs_dir(),
                "job_workspace",
                "new_job_name",
                "create_job",
                "open_job",
                "demo_job",
                demo.create_demo_job,
                "Fjord Grocery, a made-up job. Replays a recorded answer, so it costs "
                "nothing.",
                ":material/add_business:",
            )
        else:
            ws = _picker(
                "Candidate",
                data_dir(),
                "workspace",
                "new_name",
                "create",
                "open_workspace",
                "demo",
                demo.create_demo,
                "John Doe, a made-up candidate. Replays recorded answers, so it costs "
                "nothing.",
                ":material/person_add:",
            )
        _session_settings(ws, side)

    if side == "Employer":
        if ws is None:
            employer.welcome()
            return
        step = common.step_selector(
            "job_step", employer.STEPS, employer.ICONS, employer.steps_done(ws)
        )
        common.show(employer.PAGES, step, ws)
        return
    if ws is None:
        candidate.welcome()
        return
    steps = candidate.STEPS + (
        [candidate.INTERNAL] if st.session_state.get("dev_view") else []
    )
    step = common.step_selector(
        "step", steps, candidate.ICONS, candidate.steps_done(ws)
    )
    common.show(candidate.PAGES, step, ws)


def _picker(
    label: str,
    base: Path,
    key: str,
    name_key: str,
    create_key: str,
    pending: str,
    demo_key: str,
    make_demo: Callable[[], Workspace],
    demo_help: str,
    new_icon: str,
) -> Workspace | None:
    """Choose, create or open the demo for one side; return the chosen workspace."""
    names = Workspace.names(base)
    st.selectbox(
        label, names, index=None, placeholder=f"Choose a {label.lower()}", key=key
    )
    with st.container(horizontal=True):
        with st.popover("New", icon=new_icon, width="stretch"):
            name = st.text_input(
                "Name",
                key=name_key,
                placeholder="lowercase-name",
                help="Lowercase letters, digits, '-' and '_'.",
            )
            if st.button("Create", key=create_key, type="primary"):
                try:
                    _open(pending, Workspace.create(name.strip(), base))
                except ValueError as e:
                    st.error(str(e))
        if demo.available() and st.button(
            "Demo",
            key=demo_key,
            icon=":material/play_circle:",
            width="stretch",
            help=demo_help,
        ):
            _open(pending, make_demo())
    current = st.session_state.get(key)
    return Workspace(base / current) if current in names else None


def _session_settings(ws: Workspace | None, side: str) -> None:
    """Draw the API toggle, the spend so far and, for candidates, the developer view."""
    st.space("large")
    if ws is not None and common.is_demo(ws):
        st.caption(":material/play_circle: Demo: recorded answers, no API calls.")
    else:
        st.toggle(
            "Allow paid API calls",
            value=False,
            key="allow_api",
            help="Off in every new session. Buttons that call Claude say so.",
        )
        calls, cost = logged_spend()
        st.caption(f"{calls} logged API calls, about ${cost:.2f} in total.")
    if side == "Candidate":
        st.toggle(
            "Developer view",
            value=False,
            key="dev_view",
            help="Adds an internal Assessment step. Candidates never see it.",
        )


def _open(pending: str, ws: Workspace) -> None:
    st.session_state[pending] = ws.name
    st.rerun()


main()
