from io import BytesIO
from types import SimpleNamespace

from PIL import Image

from app.services.pdf.seal_image import _make_white_transparent, seal_image_reader


def test_white_background_becomes_transparent_and_red_seal_remains():
    source = Image.new("RGB", (3, 1), "white")
    source.putpixel((1, 0), (220, 40, 40))
    converted = _make_white_transparent(source)

    assert converted.getpixel((0, 0))[3] == 0
    assert converted.getpixel((1, 0))[3] == 255
    assert converted.getpixel((2, 0))[3] == 0


def test_existing_transparency_is_preserved():
    source = Image.new("RGBA", (1, 1), (220, 40, 40, 80))
    assert _make_white_transparent(source).getpixel((0, 0))[3] == 80


def test_blob_is_returned_as_transparent_png_reader():
    source = Image.new("RGB", (2, 2), "white")
    source.putpixel((1, 1), (220, 40, 40))
    blob = BytesIO()
    source.save(blob, format="JPEG")

    reader = seal_image_reader(SimpleNamespace(image_data=blob.getvalue(), path=None))
    rendered = reader.getRGBData()

    assert reader.getSize() == (2, 2)
    assert rendered
