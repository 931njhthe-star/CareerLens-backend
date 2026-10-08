"""Provider-independent structured coaching contracts."""

from pydantic import BaseModel, ConfigDict, Field


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=600)
    evidence_quote: str = Field(min_length=8, max_length=600)


class Coaching(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=1000)
    recommendations: list[Recommendation] = Field(min_length=1, max_length=3)
    reference_ids: list[str] = Field(max_length=5)
