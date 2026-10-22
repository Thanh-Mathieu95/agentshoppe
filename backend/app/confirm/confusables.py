"""Từ dễ nhầm khi nhận dạng giọng nói (mục 9.4)."""

CONFUSABLE_GROUPS = [
    {"ba", "bảy"},
    {"năm", "lăm", "lăng"},
    {"mười", "mươi"},
    {"một", "mốt"},
    {"tư", "từ", "bốn"},
    {"trăm", "chăm", "tram"},
    {"nghìn", "ngàn"},
    {"triệu", "chiệu"},
    {"lít", "lạng"},
    {"cân", "cặp"},
    {"chai", "hai"},
    {"sáu", "sau"},
]

# Từ chuẩn, xuất hiện trong hầu hết câu số; chỉ cờ khi nghe ra dạng lạ (chăm, chiệu...).
_CANONICAL_SAFE = {"trăm", "nghìn", "ngàn", "triệu", "mươi", "mười", "chai", "lít"}

# Câu nhấn khi đọc lại: chỉ những từ mà nhầm sẽ đổi giá trị.
EMPHASIS = {
    "ba": "BA, số ba, không phải bảy",
    "bảy": "BẢY, số bảy, không phải ba",
    "bẩy": "BẢY, số bảy, không phải ba",
    "sáu": "SÁU, số sáu",
    "năm": "NĂM, số năm",
    "lăm": "LĂM, tức là năm",
    "mốt": "MỐT, tức là một",
    "tư": "TƯ, tức là bốn",
    "bốn": "BỐN, số bốn",
    "hai": "HAI, số hai",
    "một": "MỘT, số một",
}

_ALL = set().union(*CONFUSABLE_GROUPS)

# Nhầm thì đổi hẳn giá trị -> ghi "lỗi đã chặn" lớp 1.
HIGH_RISK = {"ba", "bảy", "bẩy", "chăm", "tram", "chiệu", "lăng", "lạng", "cặp"}


def confusable_words_in(tokens: list[str]) -> list[str]:
    out = []
    for t in tokens:
        if t in _ALL and t not in _CANONICAL_SAFE and t not in out:
            out.append(t)
    return out


def emphasize_confusable(word: str) -> str:
    return EMPHASIS.get(word, word.upper())
