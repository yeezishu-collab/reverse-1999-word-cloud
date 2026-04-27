from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

try:
    import requests
except ImportError:  # pragma: no cover - standard-library fallback
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - standard-library fallback
    BeautifulSoup = None


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = ROOT / "data" / "sources.json"
RAW_DIR = ROOT / "data" / "raw"
CORPUS_DIR = ROOT / "data" / "corpus"
METADATA_PATH = ROOT / "data" / "metadata.jsonl"

USER_AGENT = (
    "reverse-1999-word-cloud/0.2 "
    "(public-source word-frequency research; contact: repository owner)"
)


@dataclass(frozen=True)
class Source:
    name: str
    type: str
    url: str
    platform: str = "unknown"
    tags: list[str] = field(default_factory=list)
    enabled: bool = True
    selector: str | None = None


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_sources(path: Path) -> list[Source]:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Copy data/sources.example.json to data/sources.json first."
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    sources: list[Source] = []
    for item in payload:
        sources.append(
            Source(
                name=item["name"],
                type=item["type"],
                url=item["url"],
                platform=item.get("platform", "unknown"),
                tags=list(item.get("tags", [])),
                enabled=bool(item.get("enabled", True)),
                selector=item.get("selector"),
            )
        )
    return sources


def fetch(url: str, timeout: int) -> str:
    if requests is not None:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6"},
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding
        return response.text

    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6"},
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - user-configured public URLs.
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.skip_depth = 0
        self.title_depth = 0
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg", "iframe"}:
            self.skip_depth += 1
        if tag == "title":
            self.title_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg", "iframe"} and self.skip_depth:
            self.skip_depth -= 1
        if tag == "title" and self.title_depth:
            self.title_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.title_depth:
            self.title_parts.append(data)
        if not self.skip_depth and not self.title_depth:
            self.text_parts.append(data)


def fallback_extract_page_text(payload: str) -> tuple[str, str]:
    parser = TextExtractor()
    parser.feed(payload)
    return normalize_space(" ".join(parser.title_parts)), normalize_space(" ".join(parser.text_parts))


def document_title(soup) -> str:
    if soup.title and soup.title.string:
        return normalize_space(soup.title.string)
    heading = soup.find(["h1", "h2"])
    if heading:
        return normalize_space(heading.get_text(" "))
    return ""


def extract_page_text(html: str, selector: str | None = None) -> tuple[str, str]:
    if BeautifulSoup is None:
        return fallback_extract_page_text(html)

    soup = BeautifulSoup(html, "html.parser")
    title = document_title(soup)
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()

    if selector:
        selected = soup.select(selector)
        text = " ".join(node.get_text(" ") for node in selected)
    else:
        candidates = soup.find_all(["article", "main"])
        if candidates:
            text = " ".join(node.get_text(" ") for node in candidates)
        else:
            text = soup.get_text(" ")
    return title, normalize_space(text)


def extract_rss_records(xml: str, source: Source) -> list[dict]:
    if BeautifulSoup is None:
        return fallback_extract_rss_records(xml, source)

    soup = BeautifulSoup(xml, "xml")
    records: list[dict] = []
    for index, item in enumerate(soup.find_all(["item", "entry"]), start=1):
        fields = []
        for tag_name in ["title", "summary", "description", "content"]:
            tag = item.find(tag_name)
            if tag:
                fields.append(tag.get_text(" "))
        text = normalize_space(" ".join(fields))
        if text:
            records.append(build_record(source, text=text, title="", suffix=str(index)))
    return records


def fallback_extract_rss_records(xml: str, source: Source) -> list[dict]:
    records: list[dict] = []
    root = ET.fromstring(xml)
    for index, item in enumerate(root.findall(".//item") + root.findall(".//entry"), start=1):
        fields = []
        for tag_name in ["title", "summary", "description", "content"]:
            node = item.find(tag_name)
            if node is not None and node.text:
                fields.append(node.text)
        text = normalize_space(" ".join(fields))
        if text:
            records.append(build_record(source, text=text, title="", suffix=str(index)))
    return records


def safe_stem(source: Source) -> str:
    digest = hashlib.sha1(source.url.encode("utf-8")).hexdigest()[:10]
    parsed = urlparse(source.url)
    host = parsed.netloc.replace(":", "_") or "local"
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", source.name).strip("-") or "source"
    return f"{name}-{host}-{digest}"


def build_record(source: Source, text: str, title: str = "", suffix: str = "page") -> dict:
    doc_id = hashlib.sha1(f"{source.url}:{suffix}:{text[:500]}".encode("utf-8")).hexdigest()
    return {
        "id": doc_id,
        "source": source.name,
        "platform": source.platform,
        "type": source.type,
        "url": source.url,
        "title": title,
        "tags": source.tags,
        "text": text,
        "characters": len(text),
        "collected_at": now_utc(),
    }


def save_raw(source: Source, html: str) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    output = RAW_DIR / f"{safe_stem(source)}.html"
    output.write_text(html, encoding="utf-8")
    return output


def write_corpus(records: Iterable[dict], output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def append_metadata(records: Iterable[dict]) -> None:
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with METADATA_PATH.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def collect(sources: list[Source], timeout: int, delay: float, keep_raw: bool) -> list[dict]:
    records: list[dict] = []
    enabled_sources = [source for source in sources if source.enabled]
    for index, source in enumerate(enabled_sources, start=1):
        print(f"[{index}/{len(enabled_sources)}] fetching {source.name}: {source.url}")
        try:
            payload = fetch(source.url, timeout)
            if keep_raw:
                save_raw(source, payload)

            if source.type == "rss":
                source_records = extract_rss_records(payload, source)
            elif source.type == "page":
                title, text = extract_page_text(payload, source.selector)
                source_records = [build_record(source, title=title, text=text)]
            else:
                raise ValueError(f"Unsupported source type: {source.type}")

            records.extend(record for record in source_records if record["characters"] > 0)
        except Exception as exc:  # noqa: BLE001 - collection should continue source by source.
            records.append(
                {
                    "source": source.name,
                    "platform": source.platform,
                    "url": source.url,
                    "error": str(exc),
                    "collected_at": now_utc(),
                }
            )

        if delay and index < len(enabled_sources):
            time.sleep(delay)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Reverse: 1999 public text sources.")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--keep-raw", action="store_true")
    parser.add_argument("--output", type=Path, default=CORPUS_DIR / "latest.jsonl")
    args = parser.parse_args()

    sources = load_sources(args.sources)
    records = collect(sources, timeout=args.timeout, delay=args.delay, keep_raw=args.keep_raw)
    good_records = [record for record in records if "text" in record]
    write_corpus(good_records, args.output)
    append_metadata(records)
    print(f"Collected {len(good_records)} document(s); {len(records) - len(good_records)} error(s).")


if __name__ == "__main__":
    main()
