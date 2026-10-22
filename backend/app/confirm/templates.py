"""Sinh câu đọc lại theo chế độ (mục 9.3)."""
from datetime import datetime, timedelta

from app.i18n.vi import DAY_NAMES, WEEKDAY_KEYS
from app.validators.numbers import number_to_words

# Bỏ tờ 200k: người bán vùng cao quen đếm theo tờ 100k ("ba tờ một trăm nghìn").
NOTES = [500_000, 100_000, 50_000, 20_000, 10_000]


def money_spoken(v: int) -> str:
    return f"{number_to_words(int(v))} đồng"


def money_short(v: int) -> str:
    """300000 -> 'ba trăm nghìn' (không 'đồng'), dùng trong câu dài."""
    return number_to_words(int(v))


def money_digits(v: int) -> str:
    return f"{int(v):,}".replace(",", ".") + " đ"


def split_notes(v: int) -> list[tuple[int, int]]:
    out, rest = [], int(v)
    for n in NOTES:
        if rest >= n:
            out.append((n, rest // n))
            rest %= n
    if rest:
        out.append((rest, 0))  # tiền lẻ
    return out


def money_as_notes(v: int) -> str:
    parts = [f"{number_to_words(note)} đồng lẻ" if count == 0 else f"{number_to_words(count)} tờ {number_to_words(note)}"
             for note, count in split_notes(v)]
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " và " + parts[-1]


def notes_visual(v: int) -> str:
    return ",".join(f"{n}x{c}" for n, c in split_notes(v) if c)


def volume_spoken(ml: int) -> str:
    ml = int(ml)
    if ml == 500:
        return "nửa lít"
    if ml % 1000 == 0:
        return f"{number_to_words(ml // 1000)} lít"
    if ml % 1000 == 500:
        return f"{number_to_words(ml // 1000)} lít rưỡi"
    return f"{number_to_words(ml)} mi-li-lít"


def volume_short(ml: int) -> str:
    ml = int(ml)
    return f"{ml / 1000:g} lít".replace(".", ",") if ml >= 1000 or ml == 500 else f"{ml} ml"


def weight_spoken(g: int) -> str:
    g = int(g)
    if g == 500:
        return "nửa cân"
    if g % 1000 == 0:
        return f"{number_to_words(g // 1000)} cân"
    if g % 100 == 0 and g < 1000:
        return f"{number_to_words(g // 100)} lạng"
    return f"{number_to_words(g)} gam"


def deadline_spoken(dt: datetime, now: datetime | None = None) -> str:
    now = now or datetime.now()
    days = (dt.date() - now.date()).days
    if days < 0:
        return "đã quá hạn"
    if days == 0:
        return f"hôm nay, trước {dt.hour} giờ"
    if days == 1:
        return "ngày mai"
    return DAY_NAMES[WEEKDAY_KEYS[dt.weekday()]]


def hours_left(dt: datetime, now: datetime | None = None) -> float:
    return (dt - (now or datetime.now())) / timedelta(hours=1)


SPOKEN_CHAR = {"0": "không", "1": "một", "2": "hai", "3": "ba", "4": "bốn", "5": "năm", "6": "sáu", "7": "bảy", "8": "tám", "9": "chín"}


def tracking_spoken(code: str) -> str:
    """Đọc mã theo nhóm 4 ký tự: 'nhóm một: S-P-X-V, nhóm hai: một-hai-ba-bốn'."""
    code = code.replace(" ", "").upper()
    groups = [code[i:i + 4] for i in range(0, len(code), 4)]
    out = []
    for i, g in enumerate(groups, 1):
        out.append(f"nhóm {number_to_words(i)}: " + "-".join(SPOKEN_CHAR.get(c, c) for c in g))
    return ", ".join(out)


def tracking_grouped(code: str) -> str:
    code = code.replace(" ", "").upper()
    return " ".join(code[i:i + 4] for i in range(0, len(code), 4))
