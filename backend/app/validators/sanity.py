"""Kiểm tra hợp lý (mục 9.7). Mỗi cảnh báo: {"code", "layer", "params"}."""
from app import catalog
from app.services import pricing

VOLUME_TOLERANCE = 0.30


def warn(code: str, layer: int = 2, **params) -> dict:
    return {"code": code, "layer": layer, "params": params}


def check_price(category: str, price: int) -> list[dict]:
    m = catalog.market(category)
    out = []
    if price < m["median"] / 3:
        out.append(warn("PRICE_OUTLIER_LOW", price=price, alt=price * 10, min=m["min"], max=m["max"], median=m["median"]))
    elif price > m["median"] * 3:
        out.append(warn("PRICE_OUTLIER_HIGH", price=price, alt=price // 10, min=m["min"], max=m["max"], median=m["median"]))
    p = pricing.payout(category, price)
    if p["payout"] <= 0:
        out.append(warn("NEGATIVE_PAYOUT", price=price, loss=-p["payout"]))
    return out


def check_stock(stock: int) -> list[dict]:
    return [warn("STOCK_OUTLIER", stock=stock, alt=stock // 10)] if stock > 1000 else []


def check_contradiction(field, new_value: str, is_correction: bool) -> list[dict]:
    """Cùng trường, giá trị khác trong những lần nghe gần đây mà người bán không chủ động sửa."""
    if is_correction:
        return []
    recent = [v for v in (field.history or [])[-10:] if v]
    if recent and recent[-1] != new_value and field.state.value in ("heard", "checked"):
        return [warn("CONTRADICTION", a=recent[-1], b=new_value, key=field.key)]
    return []


def image_volume_mismatch(observed_ml: float | None, value_ml: float) -> bool:
    if not observed_ml:
        return False
    return abs(observed_ml - value_ml) / value_ml > VOLUME_TOLERANCE


def check_image(listing_images: list, key: str, value: float) -> list[dict]:
    if key != "volume_ml":
        return []
    for img in listing_images:
        if img.accepted:
            obs = (img.observations or {}).get("volume_ml_est")
            if image_volume_mismatch(obs, value):
                return [warn("IMAGE_MISMATCH", layer=3, obs=obs, val=value, image_id=img.id)]
    return []


def check_listing(category: str, fields: dict) -> list[tuple[str, str]]:
    """Lỗi cứng cho cổng đăng tin (trường đã xác nhận vẫn phải hợp lệ về mặt số)."""
    errors = []
    price = fields.get("price")
    if price and price.value and int(price.value) <= 0:
        errors.append(("INVALID_PRICE", price.value))
    stock = fields.get("stock")
    if stock and stock.value is not None and stock.value != "" and int(stock.value) < 1:
        errors.append(("NO_STOCK", stock.value))
    return errors
