import io

from fontTools.ttLib import TTCollection, TTFont
import pytest

from app.fonts import FontError, validate_font

SANS = "examples/fonts/DejaVuSans.ttf"
SERIF = "examples/fonts/DejaVuSerif.ttf"


def test_accept_static_ttf():
    data = open(SANS, "rb").read()
    info = validate_font(data)
    assert info.font_id
    assert ord("A") in info.codepoints
    assert len(info.font_id) == 64


def test_reject_corrupt():
    with pytest.raises(FontError):
        validate_font(b"not a font at all" + b"\x00" * 100)
    with pytest.raises(FontError):
        validate_font(open(SANS, "rb").read()[:500])  # truncated


def test_reject_collection():
    coll = TTCollection()
    coll.fonts = [TTFont(SANS), TTFont(SERIF)]
    buf = io.BytesIO()
    coll.save(buf)
    with pytest.raises(FontError):
        validate_font(buf.getvalue())


def test_reject_variable_font():
    from fontTools.ttLib.tables._f_v_a_r import Axis
    from fontTools.ttLib import newTable

    font = TTFont(SANS)
    axis = Axis()
    axis.axisTag = "wght"
    axis.minValue, axis.defaultValue, axis.maxValue = 100, 400, 900
    axis.flags = 0
    axis.axisNameID = 256
    fvar = newTable("fvar")
    fvar.Version = 0x00010000
    fvar.Axes = [axis]
    fvar.Instances = []
    name = font["name"]
    name.setName("Weight", 256, 3, 1, 0x409)
    font["fvar"] = fvar
    buf2 = io.BytesIO()
    font.save(buf2)
    with pytest.raises(FontError):
        validate_font(buf2.getvalue())
