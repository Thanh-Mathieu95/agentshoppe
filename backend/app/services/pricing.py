from app import catalog


def payout(category: str, price: int, qty: int = 1) -> dict:
    f = catalog.fees()
    gross = price * qty
    commission = round(gross * f["commission_rate"])
    payment = round(gross * f["payment_fee_rate"])
    packaging = catalog.category(category).get("packaging_cost", 0) * qty
    fee = commission + payment + f["fixed_fee_per_order"]
    return {"gross": gross, "fee": fee, "packaging": packaging, "payout": gross - fee - packaging,
            "note": f["note"]}


def order_payout(price: int, qty: int) -> int:
    """Số tiền sàn chuyển cho người bán (chưa trừ bao bì)."""
    f = catalog.fees()
    gross = price * qty
    return int(gross - round(gross * f["commission_rate"]) - round(gross * f["payment_fee_rate"]) - f["fixed_fee_per_order"])


def price_check(category: str, price: int) -> dict:
    m = catalog.market(category)
    p = payout(category, price)
    above = sum(1 for s in m["samples"] if s < price) / len(m["samples"])
    return {**m, **p, "price": price, "percentile": round(above, 2)}
