from app import catalog


def check(category: str, text: str = "") -> dict:
    p = catalog.policies()
    rules = p.get(category, {}).get("rules", [])
    low = (text or "").lower()
    hits = [w for w in p["common_banned"] if w in low]
    return {"rules": rules, "banned_hits": hits, "auto_append": p.get(category, {}).get("auto_append")}
