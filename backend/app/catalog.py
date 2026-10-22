"""Đọc dữ liệu tĩnh trong data/*.json."""
import json
import statistics
from functools import lru_cache

from app.config import DATA_DIR


@lru_cache
def load(name: str):
    return json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))


def categories() -> dict:
    return load("categories")


def category(cat: str) -> dict:
    return categories()[cat]


def field_template(cat: str, key: str) -> dict | None:
    return next((f for f in category(cat)["fields"] if f["key"] == key), None)


def detect_category(text: str) -> str | None:
    t = text.lower()
    for cat, c in categories().items():
        if any(k in t for k in c["keywords"]):
            return cat
    return None


def market(cat: str) -> dict:
    samples = sorted(load("market_prices")[cat]["samples"])
    return {
        "min": samples[0], "max": samples[-1], "median": int(statistics.median(samples)),
        "samples": samples, "unit_note": load("market_prices")[cat]["unit_note"],
    }


def fees() -> dict:
    return load("fees")


def policies() -> dict:
    return load("policies")


def seed() -> dict:
    return load("demo_seed")


def analytics() -> dict:
    return seed()["analytics"]


def demo_script() -> list:
    return load("demo_script")


def demo_photos() -> dict:
    return load("demo_photos")
