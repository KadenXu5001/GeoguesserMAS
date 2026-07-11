import numpy as np
from PIL import Image

from geoguesser.panorama import render_perspective


def test_cardinal_headings_sample_expected_longitudes() -> None:
    width, height = 400, 200
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    pixels[:, :100] = (255, 0, 0)
    pixels[:, 100:200] = (0, 255, 0)
    pixels[:, 200:300] = (0, 0, 255)
    pixels[:, 300:] = (255, 255, 0)
    panorama = Image.fromarray(pixels, mode="RGB")

    expected = {
        0: (0, 0, 255),
        90: (255, 255, 0),
        180: (255, 0, 0),
        270: (0, 255, 0),
    }
    for heading, color in expected.items():
        view = render_perspective(panorama, heading, size=101)
        actual = view.getpixel((50, 50))
        assert all(abs(a - e) <= 1 for a, e in zip(actual, color, strict=True))


def test_rendered_view_has_requested_size() -> None:
    panorama = Image.new("RGB", (400, 200), color="purple")
    assert render_perspective(panorama, 0, size=64).size == (64, 64)
