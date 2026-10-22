import pytest

from app.confirm.templates import money_as_notes, money_spoken, tracking_spoken, volume_spoken
from app.validators.numbers import number_to_words, parse

CASES = [
    # (đầu vào, ngữ cảnh, giá trị, đơn vị, assumed_unit, từ dễ nhầm phải có)
    ("ba trăm nghìn", "price", 300000, "VND", False, []),
    ("ba trăm", "price", 300000, "VND", True, []),
    ("bảy trăm rưỡi", "price", 750000, "VND", True, ["bảy"]),
    ("một trăm rưỡi", "price", 150000, "VND", True, []),
    ("một triệu hai", "price", 1200000, "VND", False, []),
    ("hai trăm mốt", "price", 210000, "VND", True, ["mốt"]),
    ("ba mươi lăm nghìn", "price", 35000, "VND", False, ["lăm"]),
    ("300k", "price", 300000, "VND", False, []),
    ("một trăm linh năm", "stock", 105, "item", False, []),
    ("hai lít rưỡi", "volume", 2500, "ml", False, []),
    ("nửa lít", "volume", 500, "ml", False, []),
    ("năm chục chai", "stock", 50, "item", False, []),
    ("hai củ", "price", 2000000, "VND", False, []),
    ("bốn mươi tư", "stock", 44, "item", False, []),
    # thêm
    ("300.000", "price", 300000, "VND", False, []),
    ("300,000 đồng", "price", 300000, "VND", False, []),
    ("ba nghìn tư", None, 3400, "VND", False, []),
    ("một triệu rưỡi", "price", 1500000, "VND", False, []),
    ("mật ong rừng ba trăm nghìn một chai", "price", 300000, "VND", False, []),
    ("còn năm chai thôi", "stock", 5, "item", False, ["năm"]),
    ("một lít", "volume", 1000, "ml", False, []),
    ("năm trăm ml", "volume", 500, "ml", False, []),
    ("hai lạng", "weight", 200, "g", False, []),
    ("nửa cân", "weight", 500, "g", False, []),
    ("mười lăm", "stock", 15, "item", False, []),
]


@pytest.mark.parametrize("text,ctx,value,unit,assumed,confusables", CASES)
def test_parse(text, ctx, value, unit, assumed, confusables):
    p = parse(text, ctx)
    assert p is not None, text
    assert p.int_value == value
    assert p.unit == unit
    assert p.assumed_unit == assumed
    for w in confusables:
        assert w in p.confusable_words


def test_parse_none():
    assert parse("không có", "price") is None
    assert parse("mật ong rừng", "price") is None


def test_words():
    assert number_to_words(300000) == "ba trăm nghìn"
    assert number_to_words(1200000) == "một triệu hai trăm nghìn"
    assert number_to_words(105) == "một trăm linh năm"
    assert number_to_words(35000) == "ba mươi lăm nghìn"
    assert number_to_words(24) == "hai mươi tư"
    assert number_to_words(1005000) == "một triệu không trăm linh năm nghìn"
    assert money_spoken(300000) == "ba trăm nghìn đồng"


def test_notes_and_volume():
    assert money_as_notes(300000) == "ba tờ một trăm nghìn"
    assert money_as_notes(150000) == "một tờ một trăm nghìn và một tờ năm mươi nghìn"
    assert volume_spoken(500) == "nửa lít"
    assert volume_spoken(1000) == "một lít"
    assert volume_spoken(250) == "hai trăm năm mươi mi-li-lít"
    assert tracking_spoken("SPXV12345678").startswith("nhóm một: S-P-X-V, nhóm hai: một-hai-ba-bốn")


def test_roundtrip():
    for v in [35000, 150000, 210000, 300000, 750000, 1200000, 2500000]:
        assert parse(number_to_words(v), "price").int_value == v
