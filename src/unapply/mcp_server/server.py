"""The MCP server a job's matching agent connects to.

One server per job, over the database: `build_server(repo, "fjord-grocery")`, or
`unapply mcp <job>` over stdio. Its tools are thin wrappers around `AgentTools`,
which checks consent and anonymises; refusals become tool errors the agent can
read. Every tool only reads.

Tool and argument descriptions are sent to the agent, so they are written as
instructions, like the server's `instructions.md`.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import resources
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from unapply.db.repository import Repository
from unapply.mcp_server.tools import (
    MAX_RESULTS,
    AgentTools,
    CandidateEntry,
    EvidenceResults,
    ExperiencesView,
    PreferencesView,
    RubricView,
    SkillsView,
    ToolRefused,
)
from unapply.taxonomy import Taxonomy

CandidateId = Annotated[
    str, Field(description="The candidate's id, from list_candidates.")
]
_READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True)


def build_server(
    repo: Repository, job: str, taxonomy: Taxonomy | None = None
) -> MCPServer:
    """Make the MCP server for one job's matching agent.

    Parameters
    ----------
    repo : Repository
        The database.
    job : str
        The job's name in the database.
    taxonomy : Taxonomy or None, optional
        For skills named in searches, by default `default_taxonomy()`.

    Returns
    -------
    MCPServer
        With the tools `get_rubric`, `list_candidates`, `get_experiences`,
        `get_skills`, `search_evidence` and `get_preferences`.

    Raises
    ------
    NotFound
        If there is no such job.
    """
    tools = AgentTools(repo, job, taxonomy)
    instructions = resources.files(__package__).joinpath("instructions.md")
    server = MCPServer(
        name="unapply",
        title=f"unapply: candidates for {job}",
        instructions=instructions.read_text(encoding="utf-8"),
    )

    @server.tool(
        description="The job you are matching for: its title, company, hard filters "
        "and the criteria candidates are scored on, with each criterion's id, skill, "
        "lowest level that meets it (1 to 5) and weight (1 to 5).",
        annotations=_READ_ONLY,
    )
    def get_rubric() -> RubricView:
        return _call(tools.rubric)

    @server.tool(
        description="The candidates who opted in to this job: their id (which the "
        "other tools take), their alias, and which sections of their profile they "
        "shared (experiences, skills, evidence, preferences).",
        annotations=_READ_ONLY,
    )
    def list_candidates() -> list[CandidateEntry]:
        return _call(tools.candidates)

    @server.tool(
        description="A candidate's headline and their roles, projects and "
        "education: title, organisation, dates (YYYY or YYYY-MM; no end means "
        "current or unknown), what they did, the skills used and evidence ids. "
        "Needs the candidate to have shared their experiences.",
        annotations=_READ_ONLY,
    )
    def get_experiences(candidate_id: CandidateId) -> ExperiencesView:
        return _call(tools.experiences, candidate_id)

    @server.tool(
        description="A candidate's skills: for each, the candidate's own level and "
        "the level their evidence supports (both 1 to 5), how sure that estimate is "
        "(0 to 1), and evidence ids. Needs the candidate to have shared their "
        "skills.",
        annotations=_READ_ONLY,
    )
    def get_skills(candidate_id: CandidateId) -> SkillsView:
        return _call(tools.skills, candidate_id)

    @server.tool(
        description="Search a candidate's material for quotes about a skill or "
        "topic. Quotes cited for the skill the query names (or for a skill that "
        "counts towards it, such as dbt for SQL) come first, then quotes with more "
        "of the query's words. Each has an evidence id to cite. Needs the "
        "candidate to have shared their evidence.",
        annotations=_READ_ONLY,
    )
    def search_evidence(
        candidate_id: CandidateId,
        query: Annotated[
            str,
            Field(
                description="A skill, such as 'scikit-learn' or 'sql', or words to "
                "look for, such as 'demand forecasting'."
            ),
        ],
        limit: Annotated[
            int,
            Field(
                ge=1,
                le=MAX_RESULTS,
                description=f"Most quotes to return, 1 to {MAX_RESULTS}.",
            ),
        ] = 10,
    ) -> EvidenceResults:
        return _call(tools.search_evidence, candidate_id, query, limit)

    @server.tool(
        description="What a candidate wants from a job: locations, work modes, "
        "lowest salary, work permits and dealbreakers. Needs the candidate to have "
        "shared their preferences.",
        annotations=_READ_ONLY,
    )
    def get_preferences(candidate_id: CandidateId) -> PreferencesView:
        return _call(tools.preferences, candidate_id)

    return server


def _call[T](read: Callable[..., T], *args: object) -> T:
    """Run a read, turning a refusal into an error the agent sees."""
    try:
        return read(*args)
    except ToolRefused as e:
        raise ToolError(str(e)) from None
