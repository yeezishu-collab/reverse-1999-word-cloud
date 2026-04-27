from __future__ import annotations

import argparse
import html
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

try:
    import jieba
except ImportError:  # pragma: no cover - fallback for first local run
    jieba = None


ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = ROOT / "data" / "corpus"
SAMPLE_DIR = ROOT / "data" / "sample_corpus"
STOPWORDS_PATH = ROOT / "data" / "stopwords_zh.txt"
LEXICON_PATH = ROOT / "data" / "lexicon_zh.txt"
DOCS_DIR = ROOT / "docs"

CHINESE_OR_ALNUM = re.compile(r"[\u4e00-\u9fffA-Za-z0-9:+._-]+")
REVERSE_1999_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"重返未来[:：]?\s*1999",
        r"Reverse[:：]?\s*1999",
        r"\bR1999\b",
    ]
]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def read_stopwords(path: Path) -> set[str]:
    return set(read_lines(path))


def load_lexicon(path: Path) -> list[str]:
    words = []
    for line in read_lines(path):
        word = line.split()[0].lower()
        words.append(word)
        if jieba is not None:
            jieba.add_word(word)
    return words


def iter_corpus_records(corpus_dir: Path) -> list[dict]:
    records: list[dict] = []
    if not corpus_dir.exists():
        return records

    for path in sorted(corpus_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("text"):
                records.append(record)
    return records


def sample_records(sample_dir: Path) -> list[dict]:
    records: list[dict] = []
    for path in sorted(sample_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        records.append(
            {
                "id": path.stem,
                "source": path.stem,
                "platform": "sample",
                "type": "sample",
                "url": "",
                "title": path.stem,
                "tags": ["sample"],
                "text": text,
                "characters": len(text),
                "collected_at": now_utc(),
            }
        )
    return records


def normalize_text(text: str) -> str:
    normalized = text.replace("Reverse: 1999", "Reverse1999")
    normalized = normalized.replace("Reverse 1999", "Reverse1999")
    normalized = normalized.replace("重返未来：1999", "重返未来1999")
    normalized = normalized.replace("重返未来 1999", "重返未来1999")
    return " ".join(CHINESE_OR_ALNUM.findall(normalized.lower()))


def fallback_cut(segment: str, lexicon: list[str]) -> list[str]:
    words = sorted(set(lexicon), key=len, reverse=True)
    tokens: list[str] = []
    index = 0
    while index < len(segment):
        match = next((word for word in words if segment.startswith(word, index)), None)
        if match:
            tokens.append(match)
            index += len(match)
            continue

        if segment[index].isascii() and segment[index].isalnum():
            end = index + 1
            while end < len(segment) and segment[end].isascii() and segment[end].isalnum():
                end += 1
            tokens.append(segment[index:end])
            index = end
            continue

        index += 1
    return tokens


def tokenize(text: str, stopwords: set[str], lexicon: list[str]) -> list[str]:
    normalized = normalize_text(text)
    if jieba is None:
        raw_tokens = []
        for segment in CHINESE_OR_ALNUM.findall(normalized):
            raw_tokens.extend(fallback_cut(segment, lexicon))
    else:
        raw_tokens = jieba.cut(normalized)

    tokens: list[str] = []
    for token in raw_tokens:
        token = token.strip().lower()
        if len(token) < 2:
            continue
        if token in stopwords:
            continue
        if token.isdigit():
            continue
        if len(token) > 16 and not any(term == token for term in lexicon):
            continue
        tokens.append(token)
    return tokens


def relevance_score(record: dict, lexicon: list[str]) -> int:
    text = record.get("text", "")
    score = 0
    for pattern in REVERSE_1999_PATTERNS:
        if pattern.search(text):
            score += 5
    score += sum(1 for word in lexicon if word and word in text)
    return score


def word_items(counter: Counter[str], limit: int) -> list[dict]:
    return [{"text": word, "value": count} for word, count in counter.most_common(limit)]


def source_items(counters: dict[str, Counter[str]], limit: int) -> dict[str, list[dict]]:
    return {source: word_items(counter, limit) for source, counter in sorted(counters.items())}


def build_payload(records: list[dict], stopwords: set[str], lexicon: list[str], limit: int) -> dict:
    global_counter: Counter[str] = Counter()
    source_counters: dict[str, Counter[str]] = defaultdict(Counter)
    platform_counters: dict[str, Counter[str]] = defaultdict(Counter)
    document_lengths: list[int] = []
    relevant_records = []

    for record in records:
        score = relevance_score(record, lexicon)
        if score <= 0 and record.get("platform") != "sample":
            continue
        tokens = tokenize(record.get("text", ""), stopwords, lexicon)
        if not tokens:
            continue
        relevant_records.append(record)
        document_lengths.append(record.get("characters", len(record.get("text", ""))))
        global_counter.update(tokens)
        source_counters[record.get("source", "unknown")].update(tokens)
        platform_counters[record.get("platform", "unknown")].update(tokens)

    total_tokens = sum(global_counter.values())
    return {
        "generated_at": now_utc(),
        "summary": {
            "documents": len(relevant_records),
            "tokens": total_tokens,
            "unique_terms": len(global_counter),
            "median_document_characters": int(median(document_lengths)) if document_lengths else 0,
            "sources": sorted({record.get("source", "unknown") for record in relevant_records}),
            "platforms": sorted({record.get("platform", "unknown") for record in relevant_records}),
            "mode": "sample" if all(record.get("platform") == "sample" for record in relevant_records) else "collected",
        },
        "top_words": word_items(global_counter, limit),
        "by_source": source_items(source_counters, 30),
        "by_platform": source_items(platform_counters, 30),
        "documents": [
            {
                "source": record.get("source", "unknown"),
                "platform": record.get("platform", "unknown"),
                "title": record.get("title", ""),
                "characters": record.get("characters", 0),
                "collected_at": record.get("collected_at", ""),
                "url": record.get("url", ""),
            }
            for record in relevant_records
        ],
    }


def write_json(payload: object, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def word_size(value: int, max_value: int) -> int:
    if max_value <= 0:
        return 16
    return round(15 + 50 * math.sqrt(value / max_value))


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
        estimated_width = max(58, len(item["text"]) * size * 0.95)
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
    parser = argparse.ArgumentParser(description="Build Reverse: 1999 word-frequency outputs.")
    parser.add_argument("--limit", type=int, default=160)
    parser.add_argument("--corpus-dir", type=Path, default=CORPUS_DIR)
    parser.add_argument("--allow-sample", action="store_true", default=True)
    parser.add_argument("--sample-only", action="store_true")
    args = parser.parse_args()

    stopwords = read_stopwords(STOPWORDS_PATH)
    lexicon = load_lexicon(LEXICON_PATH)
    records = [] if args.sample_only else iter_corpus_records(args.corpus_dir)
    if not records and args.allow_sample:
        records = sample_records(SAMPLE_DIR)

    payload = build_payload(records, stopwords, lexicon, args.limit)
    write_json(payload, DOCS_DIR / "data.json")
    write_json(payload["top_words"], DOCS_DIR / "wordcloud.json")
    write_svg(payload["top_words"], DOCS_DIR / "wordcloud.svg")
    print(
        "Wrote docs/data.json, docs/wordcloud.json and docs/wordcloud.svg "
        f"from {payload['summary']['documents']} document(s)."
    )


if __name__ == "__main__":
    main()
