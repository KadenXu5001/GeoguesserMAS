from __future__ import annotations

from PIL import Image


def normalize_bbox_1000(
    bbox: tuple[int, int, int, int] | list[int],
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    """Convert Gemini-style normalized [ymin, xmin, ymax, xmax] to pixels."""
    if len(bbox) != 4:
        raise ValueError("bbox must contain four coordinates")
    ymin, xmin, ymax, xmax = bbox
    if not all(0 <= value <= 1000 for value in bbox):
        raise ValueError("normalized bbox coordinates must be in [0, 1000]")
    if ymin >= ymax or xmin >= xmax:
        raise ValueError("bbox must have positive area")
    return (
        round(xmin * width / 1000),
        round(ymin * height / 1000),
        round(xmax * width / 1000),
        round(ymax * height / 1000),
    )


def pad_bbox(
    bbox: tuple[int, int, int, int],
    width: int,
    height: int,
    *,
    padding_fraction: float = 0.25,
) -> tuple[int, int, int, int]:
    """Pad an [xmin, ymin, xmax, ymax] pixel box and clamp to image bounds."""
    if padding_fraction < 0:
        raise ValueError("padding fraction cannot be negative")
    xmin, ymin, xmax, ymax = bbox
    if not (0 <= xmin < xmax <= width and 0 <= ymin < ymax <= height):
        raise ValueError("bbox must be a positive-area box inside the image")
    pad_x = (xmax - xmin) * padding_fraction
    pad_y = (ymax - ymin) * padding_fraction
    return (
        max(0, round(xmin - pad_x)),
        max(0, round(ymin - pad_y)),
        min(width, round(xmax + pad_x)),
        min(height, round(ymax + pad_y)),
    )


def crop_normalized_bbox(
    image: Image.Image,
    bbox: tuple[int, int, int, int] | list[int],
    *,
    padding_fraction: float = 0.25,
) -> Image.Image:
    pixel_bbox = normalize_bbox_1000(bbox, image.width, image.height)
    return image.crop(
        pad_bbox(
            pixel_bbox,
            image.width,
            image.height,
            padding_fraction=padding_fraction,
        )
    )
