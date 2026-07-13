from __future__ import annotations

from pydantic import BaseModel, Field


class SpecialistResult(BaseModel):
    candidates: list[str] = Field(max_length=5)
    evidence: list[str]
    contradictions: list[str]
    confidence: int = Field(ge=0, le=100)


class CountryPrediction(BaseModel):
    country: str
    confidence: int = Field(ge=0, le=100)
    alternatives: list[str] = Field(max_length=3)
    evidence: list[str]

