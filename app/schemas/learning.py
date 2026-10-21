from uuid import UUID

from pydantic import BaseModel


class LearnTermSummary(BaseModel):
    slug: str
    title: str
    summary: str


class LearnCatalog(BaseModel):
    terms: list[LearnTermSummary]


class LearnFact(BaseModel):
    label: str
    value: str


class LearnObservation(BaseModel):
    available: bool
    summary: str
    facts: list[LearnFact] = []
    unavailable_reason: str | None = None


class LearnPage(BaseModel):
    slug: str
    title: str
    formula: str = ""
    what: str = ""
    example: str = ""
    yours: str = ""
    watch: str = ""
    explanation: str = ""
    meaning: str
    why_it_matters: str
    limitations: str
    portfolio_id: UUID | None = None
    ticker: str | None = None
    observation: LearnObservation
    disclaimer: str


class ExplainIn(BaseModel):
    text: str
    portfolio_id: UUID | None = None
    ticker: str | None = None
    slug: str | None = None


class ExplainOut(BaseModel):
    title: str
    formula: str = ""
    what: str
    example: str = ""
    yours: str = ""
    watch: str = ""
    explanation: str = ""
    source: str
    disclaimer: str
