"""Helpers shared by the candidate and employer sides of the app."""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from unapply.app import demo
from unapply.llm import DEFAULT_MODEL, QUESTION_MODEL, AnthropicLLM, StructuredLLM
from unapply.schemas import Profile
from unapply.workspace import Workspace

# What each kind of model call costs, shown next to the button that makes it.
COST = {
    "extract": "Claude Opus 5.5, roughly $0.10 to $1 depending on the material",
    "questions": "Claude Opus 5.5 and Sonnet 5.5, roughly $0.05 to $0.20",
    "estimate": "Claude Opus 5.5, roughly $0.03 to $0.15",
    "rubric": "Claude Opus 5.5, roughly $0.03 to $0.10",
}


def is_demo(ws: Workspace) -> bool:
    """Tell whether a workspace is a demo, which replays recorded answers.

    Parameters
    ----------
    ws : Workspace
        A candidate or job workspace.

    Returns
    -------
    bool
        True for a demo workspace.
    """
    return bool(ws.settings().get("demo"))


def allowed(ws: Workspace) -> bool:
    """Tell whether model calls can be made for a workspace in this session.

    Parameters
    ----------
    ws : Workspace
        A candidate or job workspace.

    Returns
    -------
    bool
        True for demos (they replay) and when paid calls are allowed in the sidebar.
    """
    return is_demo(ws) or bool(st.session_state.get("allow_api"))


def model(ws: Workspace, purpose: str, profile: Profile | None = None) -> StructuredLLM:
    """Pick the model for a purpose: a replay in a demo, else Claude.

    Parameters
    ----------
    ws : Workspace
        The workspace the call is for.
    purpose : str
        "extract", "estimate", "questions" or "rubric".
    profile : Profile or None, optional
        The profile, which picks the right recording in the candidate demo.

    Returns
    -------
    StructuredLLM
        A replay for demos; otherwise Claude, which refuses to call unless allowed.
    """
    if is_demo(ws):
        return demo.demo_llm(purpose, profile)
    if purpose == "questions":
        return AnthropicLLM(QUESTION_MODEL, "medium", allow=allowed(ws))
    return AnthropicLLM(DEFAULT_MODEL, "high", allow=allowed(ws))


def model_button(ws: Workspace, label: str, cost: str, key: str, icon: str) -> bool:
    """Draw a button for an action that calls the model, disabled unless allowed.

    Parameters
    ----------
    ws : Workspace
        The workspace the call is for.
    label : str
        Button label.
    cost : str
        Key in `COST`, shown under the button.
    key : str
        Widget key.
    icon : str
        Material icon, such as ":material/auto_awesome:".

    Returns
    -------
    bool
        True when clicked.
    """
    ok = allowed(ws)
    clicked = st.button(
        label,
        key=key,
        type="primary",
        icon=icon,
        disabled=not ok,
        help=None if ok else "Turn on 'Allow paid API calls' in the sidebar.",
    )
    if is_demo(ws):
        st.caption("Demo: replays a recorded answer.")
    elif ok:
        st.caption(f"Calls {COST[cost]}.")
    else:
        st.caption(f"Paid API calls are off. This calls {COST[cost]}.")
    return clicked


def step_selector(
    key: str, steps: list[str], icons: dict[str, str], done: set[str]
) -> str:
    """Draw the step selector at the top of a page and return the chosen step.

    Actions ask for another step through `st.session_state["goto_" + key]`, which is
    applied here, before the selector exists: Streamlit doesn't allow changing a
    widget's value after it is drawn.

    Parameters
    ----------
    key : str
        Session state key of the selector.
    steps : list of str
        The steps, in order.
    icons : dict of str to str
        Material icon per step.
    done : set of str
        Finished steps, shown with a check mark.

    Returns
    -------
    str
        The chosen step.
    """
    if goto := st.session_state.pop(f"goto_{key}", None):
        st.session_state[key] = goto
    if st.session_state.get(key) not in steps:
        st.session_state[key] = steps[0]
    st.segmented_control(
        "Step",
        steps,
        key=key,
        required=True,
        label_visibility="collapsed",
        format_func=lambda s: (
            f":material/check_circle: {s}" if s in done else f"{icons[s]} {s}"
        ),
    )
    if flash := st.session_state.pop("flash", None):
        st.success(flash, icon=":material/check_circle:")
    return st.session_state[key]


def show(
    pages: dict[str, Callable[[Workspace], None]], step: str, ws: Workspace
) -> None:
    """Draw the page for a step.

    Parameters
    ----------
    pages : dict of str to callable
        Page function per step.
    step : str
        The step to draw.
    ws : Workspace
        The workspace the page is for.
    """
    pages[step](ws)


def split(text: str, sep: str) -> list[str]:
    """Split text into trimmed, non-empty parts.

    Parameters
    ----------
    text : str
        Text such as "Copenhagen, Aarhus".
    sep : str
        Separator, such as "," or a newline.

    Returns
    -------
    list of str
        The parts.
    """
    return [part.strip() for part in text.split(sep) if part.strip()]
