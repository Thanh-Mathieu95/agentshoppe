"""Chuẩn hóa số tiếng Việt nói (mục 10 của đặc tả)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from app.confirm.confusables import confusable_words_in

DIGITS = {
    "không": 0, "một": 1, "mốt": 1, "hai": 2, "ba": 3, "bốn": 4, "tư": 4,
    "năm": 5, "lăm": 5, "sáu": 6, "bảy": 7, "bẩy": 7, "tám": 8, "chín": 9,
}
SCALES = {"nghìn": 1000, "ngàn": 1000, "k": 1000, "triệu": 1_000_000, "củ": 1_000_000, "tỷ": 1_000_000_000, "tỉ": 1_000_000_000}
VOLUME_WORDS = {"lít": "l", "l": "l", "ml": "ml", "mi-li-lít": "ml", "mililít": "ml", "xị": "xi"}
WEIGHT_WORDS = {"cân": "kg", "kg": "kg", "ký": "kg", "kí": "kg", "lạng": "lang", "gam": "g", "gram": "g", "g": "g"}
MONEY_WORDS = {"đồng", "đ", "vnd", "vnđ"}
ITEM_WORDS = {"chai", "hũ", "lọ", "gói", "cái", "hộp", "túi", "bó", "chiếc", "bình"}
WEIGHT_FACTOR = {"kg": 1000, "lang": 100, "g": 1}
NUMBER_WORDS = set(DIGITS) | set(SCALES) | {"mười", "mươi", "chục", "trăm", "linh", "lẻ", "rưỡi", "nửa"}

_DIGIT_TOKEN = re.compile(r"^(\d+(?:[.,]\d+)*)(k|tr|đ|ml|l|kg|g)?$")


@dataclass
class ParsedNumber:
    value: float
    unit: str | None
    raw: str
    confusable_words: list[str] = field(default_factory=list)
    assumed_unit: bool = False

    @property
    def int_value(self) -> int:
        return int(round(self.value))


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").lower()
    text = re.sub(r"[!?;:\"“”()]", " ", text)
    text = re.sub(r"(?<!\d)[.,]|[.,](?!\d)", " ", text)  # giữ dấu phân cách trong số
    return re.sub(r"\s+", " ", text).strip()


def _context_kind(context: str | None) -> str | None:
    if not context:
        return None
    last = context.split(":")[-1]
    if last in ("price", "price_change"):
        return "price"
    if last in ("volume_ml", "volume"):
        return "volume"
    if last in ("weight_g", "weight"):
        return "weight"
    if last in ("stock", "stock_update", "quantity"):
        return "stock"
    return last


def _parse_digit_literal(s: str) -> float:
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):
        return float(re.sub(r"[.,]", "", s))
    return float(s.replace(",", "."))


def _runs(tokens: list[str]) -> list[tuple[int, list[str]]]:
    """Tách các cụm liên tiếp là từ số (kèm đơn vị dính ngay sau). Trả (vị trí bắt đầu, cụm)."""
    runs, cur, start = [], [], 0
    after_unit = False
    for i, t in enumerate(tokens):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if after_unit:
            after_unit = False
            if t == "rưỡi":          # "hai lít rưỡi"
                cur.append(t)
                continue
            runs.append((start, cur))
            cur = []
        # "ba trăm nghìn | một chai": số đứng ngay trước từ chỉ cái/chai là số lượng, không phải số viết tắt
        if cur and t in DIGITS and nxt in ITEM_WORDS and any(w in SCALES or w == "trăm" for w in cur):
            runs.append((start, cur))
            cur = []
        is_num = t in NUMBER_WORDS or _DIGIT_TOKEN.match(t)
        is_unit = t in VOLUME_WORDS or t in MONEY_WORDS or t in WEIGHT_WORDS
        if is_num or (cur and is_unit):
            if not cur:
                start = i
            cur.append(t)
            if is_unit and not is_num:
                after_unit = True
        else:
            if cur:
                runs.append((start, cur))
            cur = []
    if cur:
        runs.append((start, cur))
    return [(s, r) for s, r in runs if any(t in NUMBER_WORDS or _DIGIT_TOKEN.match(t) for t in r)]


def _eval_run(run: list[str]) -> tuple[float | None, dict]:
    """Tính giá trị một cụm từ số. Trả (giá trị, thông tin đơn vị)."""
    info = {"scale_seen": False, "money": False, "volume": None, "weight": None, "half": False}
    total = 0.0          # phần đã nhân bậc nghìn/triệu
    group = 0.0          # phần dưới 1000 đang gom
    pending: float | None = None
    last_unit = None     # "ten" | "hundred" | "chuc" | scale value
    linh = False
    meaningful = False

    def flush_pending_for_scale():
        nonlocal group, pending
        if pending is None:
            return
        if last_unit == "hundred" and not linh:
            group += pending * 10           # "hai trăm mốt nghìn" -> 210
        else:
            group += pending
        pending = None

    for t in run:
        m = _DIGIT_TOKEN.match(t)
        if m:
            meaningful = True
            num = _parse_digit_literal(m.group(1))
            suf = m.group(2)
            if suf == "k":
                total += num * 1000
                info["scale_seen"] = True
                last_unit = 1000
            elif suf == "tr":
                total += num * 1_000_000
                info["scale_seen"] = True
                last_unit = 1_000_000
            elif suf in ("ml", "l"):
                group += num
                info["volume"] = suf
            elif suf in ("kg", "g"):
                group += num
                info["weight"] = suf
            elif suf == "đ":
                group += num
                info["money"] = True
            else:
                group += num
            continue
        if t in DIGITS:
            if t != "không":
                meaningful = True
            if pending is not None and last_unit is None:
                group += pending        # "hai ba" -> bỏ qua thừa
            pending = DIGITS[t]
            continue
        if t == "mười":
            meaningful = True
            group += 10
            last_unit = "ten"
            continue
        if t == "mươi":
            meaningful = True
            group += (pending if pending is not None else 1) * 10
            pending = None
            last_unit = "ten"
            continue
        if t == "chục":
            meaningful = True
            group += (pending if pending is not None else 1) * 10
            pending = None
            last_unit = "chuc"
            continue
        if t == "trăm":
            meaningful = True
            group += (pending if pending is not None else 1) * 100
            pending = None
            last_unit = "hundred"
            linh = False
            continue
        if t in ("linh", "lẻ"):
            linh = True
            continue
        if t in SCALES:
            meaningful = True
            flush_pending_for_scale()
            if group == 0:
                group = 1
            total += group * SCALES[t]
            group = 0
            last_unit = SCALES[t]
            info["scale_seen"] = True
            linh = False
            continue
        if t == "nửa":
            meaningful = True
            info["half"] = True
            continue
        if t == "rưỡi":
            meaningful = True
            if info["volume"] == "l" or info["weight"] in ("kg", "lang"):
                group += 0.5
            elif last_unit == "hundred":
                if pending is not None:
                    group += pending * 10
                    pending = None
                group += 50
            elif last_unit == "chuc":
                group += 5
            elif isinstance(last_unit, int):
                total += last_unit / 2
            elif pending is not None:
                group += pending + 0.5
                pending = None
            continue
        if t in VOLUME_WORDS:
            flush_tail = pending
            if flush_tail is not None:
                group += flush_tail
                pending = None
            info["volume"] = VOLUME_WORDS[t]
            continue
        if t in WEIGHT_WORDS:
            if pending is not None:
                group += pending
                pending = None
            info["weight"] = WEIGHT_WORDS[t]
            continue
        if t in MONEY_WORDS:
            info["money"] = True
            continue

    if pending is not None:
        if linh or last_unit in ("ten", "chuc") or last_unit is None:
            group += pending
        elif last_unit == "hundred":
            group += pending * 10                 # "hai trăm mốt" = 210
        elif isinstance(last_unit, int):
            total += pending * last_unit / 10     # "một triệu hai" = 1.200.000
    value = total + group
    if info["half"] and value == 0:
        value = 0.5   # "nửa lít", "nửa cân"
    if not meaningful:
        return None, info
    return value, info


def _score_run(run: list[str], kind: str | None) -> int:
    s = 0
    if kind == "price" and any(t in SCALES or t in MONEY_WORDS or t == "trăm" or _DIGIT_TOKEN.match(t) for t in run):
        s += 2
    if kind == "volume" and any(t in VOLUME_WORDS or t == "nửa" for t in run):
        s += 2
    if kind == "weight" and any(t in WEIGHT_WORDS or t == "nửa" for t in run):
        s += 2
    return s


def parse(text: str, context: str | None = None) -> ParsedNumber | None:
    kind = _context_kind(context)
    norm = normalize_text(text)
    tokens = norm.split()
    # "300k", "2,5l" có thể dính đơn vị; tách "300 k" cũng được xử lý vì k là SCALE
    runs = _runs(tokens)
    if not runs:
        return None
    idx, best = max(runs, key=lambda sr: _score_run(sr[1], kind))  # max giữ cụm đầu khi bằng điểm
    value, info = _eval_run(best)
    if value is None or value == 0:
        return None

    raw = " ".join(best)
    after = tokens[idx + len(best): idx + len(best) + 1]
    unit_after = [w for w in after if w in ITEM_WORDS or w in VOLUME_WORDS or w in WEIGHT_WORDS]
    confusables = confusable_words_in(best + unit_after)
    assumed = False
    unit: str | None = None

    if kind == "price" or (kind is None and (info["money"] or info["scale_seen"])):
        unit = "VND"
        if value < 10_000 and not info["money"] and not info["scale_seen"]:
            value *= 1000
            assumed = True
    elif kind == "volume" or (kind is None and info["volume"]):
        unit = "ml"
        v = info["volume"]
        if v == "l" or (v is None and info["half"]):
            value *= 1000
        elif v == "xi":
            value *= 250
            assumed = True
        elif v is None:
            if value <= 5:
                value *= 1000
            assumed = True
    elif kind == "weight" or (kind is None and info["weight"]):
        unit = "g"
        w = info["weight"]
        if w:
            value *= WEIGHT_FACTOR[w]
        else:
            if value <= 5 or info["half"]:
                value *= 1000
            assumed = True
    elif kind == "stock" or (after and after[0] in ITEM_WORDS):
        unit = "item"
    return ParsedNumber(value=value, unit=unit, raw=raw, confusable_words=confusables, assumed_unit=assumed)


# ---------- số -> chữ ----------
_W = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]


def _three(n: int, full: bool) -> str:
    h, t, u = n // 100, (n // 10) % 10, n % 10
    out = []
    if full or h:
        out += [_W[h], "trăm"]
    if t == 0:
        if u and (full or h):
            out += ["linh", _W[u]]
        elif u:
            out.append(_W[u])
    elif t == 1:
        out.append("mười")
        if u:
            out.append("lăm" if u == 5 else _W[u])
    else:
        out += [_W[t], "mươi"]
        if u == 1:
            out.append("mốt")
        elif u == 4:
            out.append("tư")
        elif u == 5:
            out.append("lăm")
        elif u:
            out.append(_W[u])
    return " ".join(out)


def number_to_words(n: int) -> str:
    if n == 0:
        return "không"
    parts = []
    units = [(1_000_000_000, "tỷ"), (1_000_000, "triệu"), (1000, "nghìn"), (1, "")]
    started = False
    for size, name in units:
        chunk = (n // size) % 1000 if size != 1_000_000_000 else n // size
        if chunk:
            parts.append((_three(chunk, started) + (" " + name if name else "")).strip())
            started = True
    return " ".join(parts)


if __name__ == "__main__":
    for s, c in [("ba trăm nghìn", "price"), ("một triệu hai", "price"), ("hai lít rưỡi", "volume")]:
        print(s, parse(s, c))
    print(number_to_words(1_250_000), "|", number_to_words(105), "|", number_to_words(24))
