"""Request and response bodies of the API.

These are the API's own models, not the domain schemas in `unapply.schemas`: what a
candidate sends and sees is narrower than what is stored. Candidate responses never
carry the assessment (estimates, claim support or why a question was chosen).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from unapply.schemas import (
    CriterionKind,
    Evidence,
    Experience,
    Job,
    Preferences,
    Profile,
    SkillCategory,
    SkillLevel,
    Source,
    WorkMode,
)

# The same names as workspace folders: lowercase letters, digits, "-" and "_".
NAME_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"


class NewCandidate(BaseModel):
    """A candidate to create.

    Parameters
    ----------
    name : str
        Lowercase letters, digits, "-" and "_", at most 64.
    github : str or None
        GitHub username whose public repositories are read at extraction.
    """

    name: str = Field(pattern=NAME_PATTERN)
    github: str | None = None


class CandidateSettings(BaseModel):
    """Settings a candidate can change.

    Parameters
    ----------
    github : str or None
        GitHub username, or None to stop reading GitHub.
    """

    github: str | None = None


class MaterialFile(BaseModel):
    """An uploaded file.

    Parameters
    ----------
    name : str
        File name.
    size : int
        Size in bytes.
    """

    name: str
    size: int


class CandidateSummary(BaseModel):
    """Where a candidate is in their journey.

    Parameters
    ----------
    name : str
        The candidate.
    demo : bool
        Whether model answers are replayed from recordings (free).
    github : str or None
        GitHub username, if set.
    material : list of MaterialFile
        Uploaded files.
    has_profile : bool
        Whether a profile has been extracted.
    approved : bool
        Whether the candidate approved their current profile.
    questions_waiting : int
        Interview questions waiting for answers.
    history : list of str
        Steps taken so far, oldest first, such as ["extracted", "reviewed"].
    """

    name: str
    demo: bool
    github: str | None
    material: list[MaterialFile]
    has_profile: bool
    approved: bool
    questions_waiting: int
    history: list[str]


class CandidateSkill(BaseModel):
    """A skill as the candidate sees it: their own level, no estimate.

    Parameters
    ----------
    name : str
        Canonical lowercase name.
    category : SkillCategory or None
        What kind of skill it is, if known.
    self_level : SkillLevel or None
        The candidate's own level, if they gave one.
    evidence_ids : list of UUID
        Evidence that mentions the skill.
    """

    name: str
    category: SkillCategory | None = None
    self_level: SkillLevel | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)


class CandidateProfile(BaseModel):
    """A profile as the candidate sees it, without the assessment.

    Parameters
    ----------
    id : UUID
        The profile's id.
    headline : str
        One-line summary.
    sources : list of Source
        What the profile was built from.
    evidence : list of Evidence
        Quotes from the sources.
    experiences : list of Experience
        Jobs, projects and education.
    skills : list of CandidateSkill
        Skills with the candidate's own levels.
    preferences : Preferences
        What the candidate wants from a job.
    approved_by_candidate_at : datetime or None
        When the candidate approved it; None for a draft.
    """

    id: UUID
    headline: str
    sources: list[Source]
    evidence: list[Evidence]
    experiences: list[Experience]
    skills: list[CandidateSkill]
    preferences: Preferences
    approved_by_candidate_at: datetime | None

    @classmethod
    def of(cls, profile: Profile) -> CandidateProfile:
        """Build the candidate's view of a full profile.

        Parameters
        ----------
        profile : Profile
            The full profile, possibly with estimates and claim support.

        Returns
        -------
        CandidateProfile
            The same profile without them.
        """
        return cls.model_validate(
            profile.model_dump(
                exclude={"claim_support": True, "skills": {"__all__": {"estimate"}}}
            )
        )


class Extraction(BaseModel):
    """What a profile extraction found.

    Parameters
    ----------
    profile : CandidateProfile
        The draft profile, to review next.
    rejected_quotes : int
        Quotes the model gave that aren't in the material, and were discarded.
    unsupported : list of str
        Items dropped because no quote backed them.
    """

    profile: CandidateProfile
    rejected_quotes: int
    unsupported: list[str]


class ExperienceEdit(BaseModel):
    """One experience in the review form.

    Parameters
    ----------
    id : str
        The experience's id, as given by the form.
    keep : bool
        False removes it.
    title : str
        Role or programme title.
    organisation : str
        Employer, client or institution.
    start : str or None
        "YYYY" or "YYYY-MM", or None if unknown.
    end : str or None
        "YYYY" or "YYYY-MM"; None means now or unknown.
    summary : str
        What the candidate did.
    evidence : list of str
        The quotes behind it, as "source: quote" lines. Shown only; ignored when
        the form is sent back.
    """

    id: str
    keep: bool = True
    title: str
    organisation: str
    start: str | None = None
    end: str | None = None
    summary: str = ""
    evidence: list[str] = Field(default_factory=list)


class SkillEdit(BaseModel):
    """One skill in the review form.

    Parameters
    ----------
    name : str
        The skill's name in the profile.
    category : SkillCategory or None
        What kind of skill it is.
    level : int or None
        The candidate's own level, 1 (aware) to 5 (expert), or None for no level.
    keep : bool
        False removes it.
    evidence : list of str
        The quotes behind it, as "source: quote" lines. Shown only; ignored when
        the form is sent back.
    """

    name: str
    category: SkillCategory | None = None
    level: int | None = Field(default=None, ge=1, le=5)
    keep: bool = True
    evidence: list[str] = Field(default_factory=list)


class NewSkill(BaseModel):
    """A skill the candidate adds, kept as their own statement.

    Parameters
    ----------
    name : str
        The skill.
    category : SkillCategory
        What kind of skill it is.
    level : int or None
        The candidate's own level, 1 to 5, if they give one.
    note : str
        Where they used it. Required.
    """

    name: str
    category: SkillCategory
    level: int | None = Field(default=None, ge=1, le=5)
    note: str


class ReviewForm(BaseModel):
    """The candidate's review of their profile, as read and as sent back.

    The same checks apply as for the review sheet (`unapply.review`).

    Parameters
    ----------
    approve : bool
        Whether the candidate approves the profile.
    headline : str
        One-line summary.
    preferences : Preferences
        What the candidate wants from a job.
    experiences : list of ExperienceEdit
        Every experience in the profile, edited or removed.
    skills : list of SkillEdit
        Every skill in the profile, with levels set, edited or removed.
    add_skills : list of NewSkill
        Skills to add.
    """

    approve: bool = False
    headline: str = ""
    preferences: Preferences = Field(default_factory=Preferences)
    experiences: list[ExperienceEdit] = Field(default_factory=list)
    skills: list[SkillEdit] = Field(default_factory=list)
    add_skills: list[NewSkill] = Field(default_factory=list)


class Question(BaseModel):
    """An interview question waiting for an answer.

    Parameters
    ----------
    skill : str
        The skill it asks about.
    why : str
        Why it is asked, in neutral words.
    text : str
        The question.
    """

    skill: str
    why: str
    text: str


class AnsweredQuestion(BaseModel):
    """A question the candidate answered.

    Parameters
    ----------
    skill : str
        The skill it asked about.
    text : str
        The question.
    answer : str
        The candidate's answer.
    """

    skill: str
    text: str
    answer: str


class Questions(BaseModel):
    """The candidate's interview questions.

    Parameters
    ----------
    waiting : list of Question
        Questions waiting for answers.
    answered : list of AnsweredQuestion
        Questions answered before, oldest first.
    """

    waiting: list[Question]
    answered: list[AnsweredQuestion]


class Answers(BaseModel):
    """Answers to the waiting questions.

    Parameters
    ----------
    answers : dict of str to str
        Skill name to answer. Questions without an answer, or with an empty one,
        are skipped and stay waiting until new questions are prepared.
    """

    answers: dict[str, str]


class AnswerResult(BaseModel):
    """What happened to the answers.

    Parameters
    ----------
    answered : int
        How many answers were added to the profile.
    """

    answered: int


class NewJob(BaseModel):
    """A job to create, before its rubric is extracted.

    Parameters
    ----------
    name : str
        Lowercase letters, digits, "-" and "_", at most 64.
    ad : str
        The job ad as it would be posted. May be set later.
    company : str or None
        Company name; read from the ad if None.
    title : str or None
        Job title; read from the ad if None.
    """

    name: str = Field(pattern=NAME_PATTERN)
    ad: str = ""
    company: str | None = None
    title: str | None = None


class JobAd(BaseModel):
    """A job ad to extract a rubric from.

    Parameters
    ----------
    ad : str
        The job ad as it would be posted.
    company : str or None
        Company name; read from the ad if None.
    title : str or None
        Job title; read from the ad if None.
    """

    ad: str
    company: str | None = None
    title: str | None = None


class JobSummary(BaseModel):
    """Where a job is: its ad and rubric.

    Parameters
    ----------
    name : str
        The job.
    demo : bool
        Whether model answers are replayed from recordings (free).
    ad : JobAd
        The ad, as extracted or as last set.
    has_rubric : bool
        Whether a rubric has been extracted.
    rubric_version : int or None
        The current rubric version, if any.
    approved : bool
        Whether the recruiter approved the current rubric version.
    history : list of str
        Steps taken so far, oldest first, such as ["extracted", "rubric"].
    """

    name: str
    demo: bool
    ad: JobAd
    has_rubric: bool
    rubric_version: int | None
    approved: bool
    history: list[str]


class RubricExtraction(BaseModel):
    """What a rubric extraction found.

    Parameters
    ----------
    job : Job
        The job with its draft rubric.
    dropped : list of str
        Criteria dropped because their quote isn't in the ad or they repeat
        another.
    """

    job: Job
    dropped: list[str]


class FiltersEdit(BaseModel):
    """Hard filters in the rubric form.

    Parameters
    ----------
    locations : list of str
        Where the job is; empty means anywhere.
    work_modes : list of WorkMode
        Work modes offered; empty means any.
    required_work_permits : list of str
        Country codes, or "EU", the candidate must be allowed to work in.
    min_years_experience : int or None
        Fewest years of relevant experience, 0 to 50, or None for no minimum.
    """

    locations: list[str] = Field(default_factory=list)
    work_modes: list[WorkMode] = Field(default_factory=list)
    required_work_permits: list[str] = Field(default_factory=list)
    min_years_experience: int | None = Field(default=None, ge=0, le=50)


class CriterionEdit(BaseModel):
    """One criterion in the rubric form.

    Parameters
    ----------
    id : str or None
        The criterion's id; None for a new criterion.
    keep : bool
        False removes it.
    kind : CriterionKind
        Must-have or nice-to-have.
    description : str
        What is asked for.
    skill : str or None
        The skill it maps to, if one.
    min_level : int or None
        Lowest acceptable level, 1 to 5, or None.
    weight : int
        1 (minor) to 5 (essential).
    """

    id: str | None = None
    keep: bool = True
    kind: CriterionKind
    description: str
    skill: str | None = None
    min_level: int | None = Field(default=None, ge=1, le=5)
    weight: int = Field(default=3, ge=1, le=5)


class RubricForm(BaseModel):
    """The recruiter's edit of a rubric. Any change raises its version.

    The same checks apply as for the rubric sheet (`unapply.jobs.sheet`).

    Parameters
    ----------
    approve : bool
        Whether the recruiter approves the rubric.
    company : str
        Company name.
    title : str
        Job title.
    hard_filters : FiltersEdit
        Pass/fail requirements.
    criteria : list of CriterionEdit
        Every criterion to keep or remove, and new ones without an id.
    """

    approve: bool = False
    company: str
    title: str
    hard_filters: FiltersEdit = Field(default_factory=FiltersEdit)
    criteria: list[CriterionEdit] = Field(default_factory=list)


class Assessment(BaseModel):
    """The internal assessment of a candidate. Never shown to the candidate.

    Parameters
    ----------
    profile : Profile
        The full profile, with estimates and claim support.
    summary : str or None
        Claim support as counts, such as "3 overclaims, 4 unverified, ...", or None
        before it is computed.
    not_estimated : list of str
        Skills without an estimate yet.
    """

    profile: Profile
    summary: str | None
    not_estimated: list[str]
