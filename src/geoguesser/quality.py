from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image


MINIMUM_WIDTH = 4_096
MINIMUM_HEIGHT = 2_048
MAXIMUM_ASPECT_ERROR = 0.04
MINIMUM_BLUR_SCORE = 25.0
MAXIMUM_WRAP_MAE = 45.0
MAXIMUM_CLIPPED_FRACTION = 0.35


@dataclass(frozen=True)
class QualityAssessment:
    width: int
    height: int
    aspect_ratio: float
    aspect_error: float
    wrap_mae: float
    blur_score: float
    dark_fraction: float
    bright_fraction: float
    automatic_pass: bool
    rejection_reasons: tuple[str, ...]

    def as_document(self) -> dict:
        document = asdict(self)
        document["rejection_reasons"] = list(self.rejection_reasons)
        document["policy_version"] = "panorama-quality-v1"
        document["manual_review"] = {
            "status": "pending" if self.automatic_pass else "not_required",
            "required_checks": [
                "complete_horizontal_coverage",
                "severe_stitching",
                "camera_or_operator_occlusion",
            ],
        }
        return document


def _blur_score(rgb: np.ndarray) -> float:
    gray = (
        rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    ).astype(np.float32)
    laplacian = (
        -4 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
    )
    return float(laplacian.var())


def assess_panorama(path: Path) -> QualityAssessment:
    with Image.open(path) as image:
        image = image.convert("RGB")
        width, height = image.size
        sample_width = min(width, 2_048)
        sample_height = max(1, round(height * sample_width / width))
        sample = np.asarray(image.resize((sample_width, sample_height)), dtype=np.float32)

    aspect_ratio = width / height
    aspect_error = abs(aspect_ratio - 2.0) / 2.0
    seam_width = max(1, min(4, sample_width // 100))
    wrap_mae = float(
        np.abs(sample[:, :seam_width] - sample[:, -seam_width:][:, ::-1]).mean()
    )
    blur_score = _blur_score(sample)
    luminance = sample.mean(axis=2)
    dark_fraction = float((luminance <= 8).mean())
    bright_fraction = float((luminance >= 247).mean())

    reasons = []
    if width < MINIMUM_WIDTH or height < MINIMUM_HEIGHT:
        reasons.append("resolution_below_4096x2048")
    if aspect_error > MAXIMUM_ASPECT_ERROR:
        reasons.append("not_approximately_2_to_1")
    if wrap_mae > MAXIMUM_WRAP_MAE:
        reasons.append("horizontal_wrap_discontinuity")
    if blur_score < MINIMUM_BLUR_SCORE:
        reasons.append("excessive_blur")
    if dark_fraction + bright_fraction > MAXIMUM_CLIPPED_FRACTION:
        reasons.append("excessive_exposure_clipping")

    return QualityAssessment(
        width=width,
        height=height,
        aspect_ratio=aspect_ratio,
        aspect_error=aspect_error,
        wrap_mae=wrap_mae,
        blur_score=blur_score,
        dark_fraction=dark_fraction,
        bright_fraction=bright_fraction,
        automatic_pass=not reasons,
        rejection_reasons=tuple(reasons),
    )
