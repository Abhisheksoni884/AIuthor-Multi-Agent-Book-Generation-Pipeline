"""
core/schemas.py - Pydantic models for all structured outputs in the pipeline.

Every piece of data crossing agent boundaries is validated here.
This replaces ad-hoc regex parsing with enforced, typed contracts.
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ────────────────────────────────────────────────────────────────────────────
# Planner output
# ────────────────────────────────────────────────────────────────────────────

class ChapterPlan(BaseModel):
    num: int = Field(..., ge=1, description="Chapter number (1-indexed)")
    title: str = Field(..., min_length=1)
    summary: str = Field(default="")
    key_points: list[str] = Field(default_factory=list)


class BookPlan(BaseModel):
    title: str = Field(..., min_length=1)
    subtitle: str = Field(default="")
    genre: str = Field(default="Non-fiction")
    tone: str = Field(default="conversational")
    author_name: str = Field(default="The Author")
    tagline: str = Field(default="")
    target_audience: str = Field(default="General readers")
    back_cover_theme: str = Field(default="")
    chapters: list[ChapterPlan] = Field(default_factory=list)
    glossary_terms: list[str] = Field(default_factory=list)
    characters: list[dict] = Field(default_factory=list)
    front_matter: list[str] = Field(
        default_factory=lambda: ["half_title", "copyright", "dedication", "epigraph",
                                  "foreword", "preface", "acknowledgments", "introduction", "toc"]
    )
    back_matter: list[str] = Field(
        default_factory=lambda: ["afterword", "appendix", "glossary",
                                  "references", "about_author", "back_cover"]
    )

    @field_validator("tone")
    @classmethod
    def validate_tone(cls, v):
        valid = {"conversational", "academic", "storyteller", "motivational", "witty"}
        if v not in valid:
            return "conversational"
        return v


# ────────────────────────────────────────────────────────────────────────────
# Researcher output
# ────────────────────────────────────────────────────────────────────────────

class FactEntry(BaseModel):
    key: str
    value: str
    source: str = "research"
    chapter: int = 0


class ResearchBrief(BaseModel):
    chapter: int
    facts: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)   # "term: definition" lines
    callbacks: list[str] = Field(default_factory=list)
    retrieved_facts: str = Field(default="")
    raw: str = Field(default="")


# ────────────────────────────────────────────────────────────────────────────
# Fact-checker output
# ────────────────────────────────────────────────────────────────────────────

class FactCheckReport(BaseModel):
    chapter: int
    status: str = Field(default="PASS")        # "PASS" | "NEEDS_REVIEW"
    issues: list[str] = Field(default_factory=list)
    corrections: list[str] = Field(default_factory=list)
    verified_facts: list[str] = Field(default_factory=list)
    unverified_claims: list[str] = Field(default_factory=list)
    report: str = Field(default="")            # raw LLM text (for full log)

    @field_validator("status")
    @classmethod
    def normalise_status(cls, v):
        return "NEEDS_REVIEW" if "REVIEW" in v.upper() else "PASS"


# ────────────────────────────────────────────────────────────────────────────
# Memory Keeper output
# ────────────────────────────────────────────────────────────────────────────

class MemoryKeeperReport(BaseModel):
    chapter: int
    consistency_issues: list[str] = Field(default_factory=list)
    suggested_fixes: list[str] = Field(default_factory=list)
    tonality_signals: str = Field(default="")   # observed tone fingerprint for this chapter
    report: str = Field(default="")


# ────────────────────────────────────────────────────────────────────────────
# Assembler output
# ────────────────────────────────────────────────────────────────────────────

class AssemblerResult(BaseModel):
    pdf: str
    docx: str
    title: str


# ────────────────────────────────────────────────────────────────────────────
# RLHF / preference pair
# ────────────────────────────────────────────────────────────────────────────

class PreferencePair(BaseModel):
    """A (chosen, rejected) pair for Humanizer / tone preference training."""
    context: str              # what agent + chapter this is for
    chosen: str               # preferred output
    rejected: str             # inferior output
    rubric_scores: dict = Field(default_factory=dict)   # {"no_banned": 1.0, "tone": 0.9, ...}
    rationale: str = Field(default="")


# ────────────────────────────────────────────────────────────────────────────
# Validation helpers
# ────────────────────────────────────────────────────────────────────────────

def validate_book_plan(raw: dict) -> BookPlan:
    """Parse and validate a raw dict into a BookPlan. Returns validated model."""
    return BookPlan.model_validate(raw)


def validate_fact_check(raw: dict) -> FactCheckReport:
    return FactCheckReport.model_validate(raw)


def validate_memory_report(raw: dict) -> MemoryKeeperReport:
    return MemoryKeeperReport.model_validate(raw)
