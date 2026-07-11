from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


CARDINAL_HEADINGS = (0, 90, 180, 270)


def render_perspective(
    panorama: Image.Image,
    heading_degrees: float,
    *,
    field_of_view_degrees: float = 90.0,
    size: int = 1024,
) -> Image.Image:
    """Render a rectilinear view from an equirectangular panorama.

    Heading 0 points at the panorama center, and positive headings rotate right.
    Pitch is fixed at the horizon for the v1 four-cardinal-view dataset.
    """
    if not 1.0 <= field_of_view_degrees < 180.0:
        raise ValueError("field of view must be in [1, 180) degrees")
    if size <= 0:
        raise ValueError("size must be positive")

    source = np.asarray(panorama.convert("RGB"))
    source_height, source_width = source.shape[:2]

    axis = np.linspace(-1.0, 1.0, size, endpoint=False) + (1.0 / size)
    grid_x, grid_y = np.meshgrid(axis, -axis)
    focal = 1.0 / np.tan(np.deg2rad(field_of_view_degrees) / 2.0)

    directions = np.stack((grid_x, np.full_like(grid_x, focal), grid_y), axis=-1)
    directions /= np.linalg.norm(directions, axis=-1, keepdims=True)

    yaw = np.deg2rad(heading_degrees)
    x = directions[..., 0] * np.cos(yaw) + directions[..., 1] * np.sin(yaw)
    y = -directions[..., 0] * np.sin(yaw) + directions[..., 1] * np.cos(yaw)
    z = directions[..., 2]

    longitude = np.arctan2(x, y)
    latitude = np.arcsin(np.clip(z, -1.0, 1.0))
    source_x = ((longitude / (2.0 * np.pi) + 0.5) * source_width) % source_width
    source_y = (0.5 - latitude / np.pi) * (source_height - 1)

    x0 = np.floor(source_x).astype(np.int64)
    y0 = np.floor(source_y).astype(np.int64)
    x1 = (x0 + 1) % source_width
    y1 = np.minimum(y0 + 1, source_height - 1)
    wx = (source_x - x0)[..., None]
    wy = (source_y - y0)[..., None]

    top = source[y0, x0] * (1 - wx) + source[y0, x1] * wx
    bottom = source[y1, x0] * (1 - wx) + source[y1, x1] * wx
    rendered = top * (1 - wy) + bottom * wy
    return Image.fromarray(np.clip(rendered, 0, 255).astype(np.uint8), mode="RGB")


def render_cardinal_views(
    panorama_path: str | Path,
    output_dir: str | Path,
    *,
    field_of_view_degrees: float = 90.0,
    size: int = 1024,
    image_format: str = "JPEG",
) -> list[Path]:
    """Render and save the four fixed cardinal views for one panorama."""
    panorama_path = Path(panorama_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".jpg" if image_format.upper() == "JPEG" else f".{image_format.lower()}"

    outputs: list[Path] = []
    with Image.open(panorama_path) as panorama:
        for heading in CARDINAL_HEADINGS:
            view = render_perspective(
                panorama,
                heading,
                field_of_view_degrees=field_of_view_degrees,
                size=size,
            )
            output = output_dir / f"{panorama_path.stem}_h{heading:03d}{suffix}"
            view.save(output, format=image_format, quality=92)
            outputs.append(output)
    return outputs
