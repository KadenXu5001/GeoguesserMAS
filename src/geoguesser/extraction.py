from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


DetectionStatus = Literal["not_present", "not_detected", "present_but_illegible", "present"]


class NormalizedBox(BaseModel):
    """Gemini [ymin, xmin, ymax, xmax] coordinates normalized to 0-1000."""

    ymin: int = Field(ge=0, le=1000)
    xmin: int = Field(ge=0, le=1000)
    ymax: int = Field(ge=0, le=1000)
    xmax: int = Field(ge=0, le=1000)

    def model_post_init(self, __context: object) -> None:
        if self.ymax <= self.ymin or self.xmax <= self.xmin:
            raise ValueError("normalized bounding box must have positive area")


class DetectedObject(BaseModel):
    heading: Literal[0, 90, 180, 270]
    bbox: NormalizedBox | None = None
    observation: str = Field(min_length=1, max_length=500)
    confidence: int = Field(ge=0, le=100)
    legibility: Literal["clear", "partial", "illegible", "not_applicable"]
    transcription: str | None = Field(default=None, max_length=250)


class SignalCategory(BaseModel):
    status: DetectionStatus
    objects: list[DetectedObject] = Field(default_factory=list, max_length=20)
    signal: str = Field(max_length=500)


class ExtractionOutput(BaseModel):
    schema_version: Literal["extraction-v1"] = "extraction-v1"
    driving_side_and_markings: SignalCategory
    signs_and_language: SignalCategory
    vehicles_and_plates: SignalCategory
    infrastructure: SignalCategory
    terrain_vegetation_and_climate: SignalCategory
    architecture_and_settlement: SignalCategory

