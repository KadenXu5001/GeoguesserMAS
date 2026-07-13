from __future__ import annotations

import numpy as np
from PIL import Image

from geoguesser import quality


def test_quality_accepts_sharp_wrapped_equirectangular_image(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(quality, "MINIMUM_WIDTH", 512)
    monkeypatch.setattr(quality, "MINIMUM_HEIGHT", 256)
    rng = np.random.default_rng(7)
    pixels = rng.integers(20, 235, size=(256, 512, 3), dtype=np.uint8)
    pixels[:, -4:] = pixels[:, :4][:, ::-1]
    path = tmp_path / "good.png"
    Image.fromarray(pixels).save(path)

    assessment = quality.assess_panorama(path)

    assert assessment.automatic_pass is True
    assert assessment.wrap_mae == 0
    assert assessment.rejection_reasons == ()


def test_quality_rejects_low_resolution_blurred_image(tmp_path) -> None:
    path = tmp_path / "bad.png"
    Image.new("RGB", (400, 200), "gray").save(path)

    assessment = quality.assess_panorama(path)

    assert assessment.automatic_pass is False
    assert "resolution_below_4096x2048" in assessment.rejection_reasons
    assert "excessive_blur" in assessment.rejection_reasons
