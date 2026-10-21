from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=500)


class EvidenceItem(BaseModel):
    kind: Literal["fact", "metric"]
    name: str
    value: str
    source: Literal["database", "calculation", "provider", "unavailable"]
    id: str = ""
    label: str = ""
    method: str = ""
    as_of: str = ""
    unit: str = ""
    availability: Literal["available", "unavailable"] = "available"


class AssistantAnswer(BaseModel):
    portfolio_id: UUID
    question: str
    facts: list[EvidenceItem]
    metrics: list[EvidenceItem]
    interpretation: str
    interpretation_source: Literal["template", "llm"]
    disclaimer: str
