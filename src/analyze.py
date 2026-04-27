from __future__ import annotations

import argparse
import html
import json
import math
import re
from collections import Counter
from pathlib import Path

try:
    import jieba
except ImportError:  # pragma: no cover - fallback for first local run
    jieba = None


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
STOPWORDS_PATH = ROOT / "data" / "stopwords_zh.txt"
DOCS_DIR = ROOT / "docs"

CHINESE_OR_ALNUM = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")


def read_stopwords(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def iter_text_files(raw_dir: Path) -> list[Path]:
    if not raw_dir.exists():
        return []
    return sorted(raw_dir.glob("*.txt"))


def tokenize(text: str, stopwords: set[str]) -> list[str]:
    normalized = " ".join(CHINESE_OR_ALNUM.findall(text.lower()))
    tokens: list[str] = []
    if jieba is None:
        raw_tokens = CHINESE_OR_ALNUM.findall(normalized)
    else:
        raw_tokens = jieba.cut(normalized)

    for token in raw_tokens:
        token = token.strip()
        if len(token) < 2:
            continue
        if token in stopwords:
            continue
        if token.isdigit():
            continue
        tokens.append(token)
    return tokens


def count_words(raw_dir: Path, stopwords: set[str]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for path in iter_text_files(raw_dir):
        counter.update(tokenize(path.read_text(encoding="utf-8", errors="ignore"), stopwords))
    return counter


def to_wordcloud_payload(counter: Counter[str], limit: int) -> list[dict]:
    return [
        {"text": word, "value": count}
        for word, count in counter.most_common(limit)
    ]


def write_json(words: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")


def word_size(value: int, max_value: int) -> int:
    if max_value <= 0:
        return 16
    return round(16 + 48 * math.sqrt(value / max_value))


def write_svg(words: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    width = 1200
    height = 720
    max_value = max((item["value"] for item in words), default=1)
    palette = ["#0f766e", "#b91c1c", "#1d4ed8", "#a16207", "#7c3aed", "#166534"]
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720">',
        '<rect width="1200" height="720" fill="#f8fafc"/>',
        '<text x="40" y="72" font-size="34" font-family="Arial, sans-serif" fill="#0f172a">Reverse: 1999 Word Cloud</text>',
    ]

    x = 50
    y = 140
    row_height = 0
    for index, item in enumerate(words):
        text = html.escape(item["text"])
        size = word_size(item["value"], max_value)
        estimated_width = max(56, len(item["text"]) * size * 0.95)
        if x + estimated_width > width - 60:
            x = 50
            y += row_height + 30
            row_height = 0
        if y > height - 40:
            break
        color = palette[index % len(palette)]
        lines.append(
            f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" '
            f'font-family="Arial, Microsoft YaHei, sans-serif" '
            f'font-weight="700" fill="{color}">{text}</text>'
        )
        x += estimated_width + 26
        row_height = max(row_height, size)

    lines.append("</svg>")
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build word frequency outputs.")
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    args = parser.parse_args()

    stopwords = read_stopwords(STOPWORDS_PATH)
    counter = count_words(args.raw_dir, stopwords)
    words = to_wordcloud_payload(counter, args.limit)
    write_json(words, DOCS_DIR / "wordcloud.json")
    write_svg(words, DOCS_DIR / "wordcloud.svg")
    print(f"Wrote {len(words)} word(s) to docs/wordcloud.json and docs/wordcloud.svg")


if __name__ == "__main__":
    main()
