from types import SimpleNamespace

from app.models import FieldState
from app.validators import sanity


def codes(ws):
    return [w["code"] for w in ws]


def test_price_outliers():
    low = sanity.check_price("honey", 35000)
    assert "PRICE_OUTLIER_LOW" in codes(low)
    assert low[0]["params"]["alt"] == 350000
    high = sanity.check_price("honey", 3_000_000)
    assert "PRICE_OUTLIER_HIGH" in codes(high) and high[0]["params"]["alt"] == 300000
    assert sanity.check_price("honey", 300000) == []


def test_negative_payout():
    assert "NEGATIVE_PAYOUT" in codes(sanity.check_price("honey", 10000))


def test_stock_outlier():
    assert codes(sanity.check_stock(2000)) == ["STOCK_OUTLIER"]
    assert sanity.check_stock(8) == []


def test_contradiction():
    f = SimpleNamespace(history=["300000"], state=FieldState.HEARD, key="price")
    assert codes(sanity.check_contradiction(f, "350000", is_correction=False)) == ["CONTRADICTION"]
    assert sanity.check_contradiction(f, "350000", is_correction=True) == []


def test_image_mismatch():
    img = SimpleNamespace(accepted=True, observations={"volume_ml_est": 500}, id=1)
    w = sanity.check_image([img], "volume_ml", 1000)
    assert codes(w) == ["IMAGE_MISMATCH"] and w[0]["layer"] == 3
    assert sanity.check_image([img], "volume_ml", 550) == []
