from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = ROOT / "data" / "sources.json"
RAW_DIR = ROOT / "data" / "raw"
METADATA_PATH = ROOT / "data" / "metadata.jsonl"

USER_AGENT = (
    "reverse-1999-word-cloud/0.1 "
    "(research word-frequency project; contact: repository owner)"
)


@dataclass(frozen=True)
class Source:
    name: str
    type: str
    url: str


def load_sources(path: Path) -> list[Source]:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Copy data/sources.example.json to data/sources.json first."
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    sources: list[Source] = []
    for item in payload:
        sources.append(Source(name=item["name"], type=item["type"], url=item["url"]))
    return sources


def fetch(url: str, timeout: int) -> str:
    response = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"},
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_page_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return normalize_space(soup.get_text(" "))


def extract_rss_text(xml: str) -> str:
    soup = BeautifulSoup(xml, "xml")
    chunks: list[str] = []
    for item in soup.find_all(["item", "entry"]):
        fields = []
        for tag_name in ["title", "summary", "description", "content"]:
            tag = item.find(tag_name)
            if tag:
                fields.append(tag.get_text(" "))
        if fields:
            chunks.append(normalize_space(" ".join(fields)))
    return "\n".join(chunks)


def safe_stem(source: Source) -> str:
    digest = hashlib.sha1(source.url.encode("utf-8")).hexdigest()[:10]
    parsed = urlparse(source.url)
    host = parsed.netloc.replace(":", "_") or "local"
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", source.name).strip("-") or "source"
    return f"{name}-{host}-{digest}"


def save_text(source: Source, text: str) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    output = RAW_DIR / f"{safe_stem(source)}.txt"
    output.write_text(text, encoding="utf-8")
    return output


def append_metadata(records: Iterable[dict]) -> None:
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with METADATA_PATH.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def collect(sources: list[Source], timeout: int, delay: float) -> list[dict]:
    records = []
    for index, source in enumerate(sources, start=1):
        print(f"[{index}/{len(sources)}] fetching {source.name}: {source.url}")
        html = fetch(source.url, timeout)
        if source.type == "rss":
            text = extract_rss_text(html)
        elif source.type == "page":
            text = extract_page_text(html)
        else:
            raise ValueError(f"Unsupported source type: {source.type}")

        output = save_text(source, text)
        records.append(
            {
                "name": source.name,
                "type": source.type,
                "url": source.url,
                "path": str(output.relative_to(ROOT)),
                "characters": len(text),
                "collected_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        if delay and index < len(sources):
            time.sleep(delay)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Reverse: 1999 text sources.")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()

    sources = load_sources(args.sources)
    records = collect(sources, timeout=args.timeout, delay=args.delay)
    append_metadata(records)
    print(f"Collected {len(records)} source(s).")


if __name__ == "__main__":
    main()
