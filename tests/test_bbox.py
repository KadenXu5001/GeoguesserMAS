from geoguesser.bbox import normalize_bbox_1000, pad_bbox


def test_normalized_yxyx_conversion() -> None:
    assert normalize_bbox_1000([100, 200, 500, 800], 1000, 500) == (200, 50, 800, 250)


def test_padding_clamps_to_image() -> None:
    assert pad_bbox((0, 0, 100, 100), 500, 500) == (0, 0, 125, 125)
