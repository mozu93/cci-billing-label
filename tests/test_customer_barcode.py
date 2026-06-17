import pytest


def test_build_barcode_chars_length():
    from app.utils.customer_barcode import build_barcode_chars
    chars = build_barcode_chars("1000013", "1-3-2")
    assert len(chars) == 23


def test_build_barcode_chars_start_stop():
    from app.utils.customer_barcode import build_barcode_chars
    chars = build_barcode_chars("1000013", "1-3-2")
    assert chars[0] == "S"
    assert chars[-1] == "STOP"


def test_invalid_postal_raises():
    from app.utils.customer_barcode import build_barcode_chars
    with pytest.raises(ValueError):
        build_barcode_chars("123", "1-2")


def test_barcode_height_positive():
    from app.utils.customer_barcode import barcode_height
    assert barcode_height() > 0
