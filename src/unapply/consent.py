"""A candidate's consent to one job: which parts of their profile its agent may read.

Consent is per job (see the design principles in the README). A candidate opts in to
a job and chooses which sections of their profile the job's matching agent may read
over MCP (`unapply.mcp_server`); a candidate who hasn't opted in doesn't exist for
that job's agent. Withdrawing consent removes it, and takes effect on the agent's
next call.

Consent belongs to the candidate and the job, not to a profile version: it stays
when the candidate's profile is extracted again, and goes when either is deleted.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class ConsentSection(StrEnum):
    """A part of the profile a candidate can share with a job's agent.

    Each section is what one MCP tool reads: `get_experiences` (with the
    headline), `get_skills`, `search_evidence` and `get_preferences`.
    """

    EXPERIENCES = "experiences"
    SKILLS = "skills"
    EVIDENCE = "evidence"
    PREFERENCES = "preferences"


class Consent(BaseModel):
    """A candidate's opt-in to one job.

    Parameters
    ----------
    candidate : str
        The candidate's name in the database. Never shown to the job's agent.
    job : str
        The job's name in the database.
    sections : list of ConsentSection
        What the job's agent may read, in `ConsentSection` order, each once. By
        default everything; empty is allowed and means the candidate is listed
        to the agent but shares nothing yet.
    granted_at : datetime
        When the candidate opted in or last changed the sections, local time.
    """

    candidate: str
    job: str
    sections: list[ConsentSection] = Field(default_factory=lambda: list(ConsentSection))
    granted_at: datetime = Field(default_factory=datetime.now)

    @field_validator("sections")
    @classmethod
    def _ordered(cls, v: list[ConsentSection]) -> list[ConsentSection]:
        return [s for s in ConsentSection if s in v]

    def allows(self, section: ConsentSection) -> bool:
        """Say whether the job's agent may read a section.

        Parameters
        ----------
        section : ConsentSection
            The section.

        Returns
        -------
        bool
            True if the candidate shared it with this job.
        """
        return section in self.sections
