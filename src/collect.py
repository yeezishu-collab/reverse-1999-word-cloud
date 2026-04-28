from __future__ import annotations

import argparse
from email.utils import parsedate_to_datetime
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
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
EXAMPLE_SOURCES = ROOT / "data" / "sources.example.json"
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
    crawl_depth: int = 0
    max_pages: int = 1
    allow_domains: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=list)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_sources(path: Path) -> list[Source]:
    if not path.exists():
        if path == DEFAULT_SOURCES and EXAMPLE_SOURCES.exists():
            print(f"Missing {path}; using {EXAMPLE_SOURCES} as a starter source list.")
            path = EXAMPLE_SOURCES
        else:
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
                crawl_depth=int(item.get("crawl_depth", 0)),
                max_pages=int(item.get("max_pages", 1)),
                allow_domains=list(item.get("allow_domains", [])),
                include_patterns=list(item.get("include_patterns", [])),
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


def normalize_datetime(value: str | None) -> str:
    if not value:
        return ""
    text = normalize_space(value)
    for parser in (
        lambda raw: datetime.fromisoformat(raw.replace("Z", "+00:00")),
        parsedate_to_datetime,
    ):
        try:
            parsed = parser(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
        except (TypeError, ValueError, IndexError, OverflowError):
            continue
    return ""


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.skip_depth = 0
        self.title_depth = 0
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[str] = []
        self.meta_dates: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value for key, value in attrs if key and value}
        if tag in {"script", "style", "noscript", "svg", "iframe"}:
            self.skip_depth += 1
        if tag == "title":
            self.title_depth += 1
        if tag == "a" and attr_map.get("href"):
            self.links.append(attr_map["href"])
        if tag == "meta":
            key = (attr_map.get("property") or attr_map.get("name") or "").lower()
            if key in {"article:published_time", "article:modified_time", "pubdate", "date", "datepublished"}:
                self.meta_dates.append(attr_map.get("content", ""))
        if tag == "time" and attr_map.get("datetime"):
            self.meta_dates.append(attr_map["datetime"])

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


def fallback_extract_page_details(payload: str) -> tuple[str, str, list[str], str]:
    parser = TextExtractor()
    parser.feed(payload)
    return (
        normalize_space(" ".join(parser.title_parts)),
        normalize_space(" ".join(parser.text_parts)),
        parser.links,
        normalize_datetime(next((date for date in parser.meta_dates if date), "")),
    )


def document_title(soup) -> str:
    if soup.title and soup.title.string:
        return normalize_space(soup.title.string)
    heading = soup.find(["h1", "h2"])
    if heading:
        return normalize_space(heading.get_text(" "))
    return ""


def document_date(soup) -> str:
    candidates = []
    for selector in [
        {"property": "article:published_time"},
        {"property": "article:modified_time"},
        {"name": "date"},
        {"name": "datePublished"},
        {"itemprop": "datePublished"},
    ]:
        tag = soup.find("meta", attrs=selector)
        if tag and tag.get("content"):
            candidates.append(tag.get("content"))
    for tag in soup.find_all("time"):
        if tag.get("datetime"):
            candidates.append(tag.get("datetime"))
    return normalize_datetime(next((date for date in candidates if date), ""))


def extract_page_text(html: str, selector: str | None = None) -> tuple[str, str]:
    title, text, _, _ = extract_page_details(html, selector)
    return title, text


def extract_page_details(html: str, selector: str | None = None) -> tuple[str, str, list[str], str]:
    if BeautifulSoup is None:
        return fallback_extract_page_details(html)

    soup = BeautifulSoup(html, "html.parser")
    title = document_title(soup)
    published_at = document_date(soup)
    links = [tag.get("href", "") for tag in soup.find_all("a") if tag.get("href")]
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
    return title, normalize_space(text), links, published_at


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
        published_at = ""
        for tag_name in ["pubDate", "published", "updated", "dc:date"]:
            tag = item.find(tag_name)
            if tag:
                published_at = normalize_datetime(tag.get_text(" "))
                if published_at:
                    break
        text = normalize_space(" ".join(fields))
        if text:
            records.append(build_record(source, text=text, title="", suffix=str(index), published_at=published_at))
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
        published_at = ""
        for tag_name in ["pubDate", "published", "updated"]:
            node = item.find(tag_name)
            if node is not None and node.text:
                published_at = normalize_datetime(node.text)
                if published_at:
                    break
        text = normalize_space(" ".join(fields))
        if text:
            records.append(build_record(source, text=text, title="", suffix=str(index), published_at=published_at))
    return records


def safe_stem(source: Source) -> str:
    digest = hashlib.sha1(source.url.encode("utf-8")).hexdigest()[:10]
    parsed = urlparse(source.url)
    host = parsed.netloc.replace(":", "_") or "local"
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", source.name).strip("-") or "source"
    return f"{name}-{host}-{digest}"


def build_record(
    source: Source,
    text: str,
    title: str = "",
    suffix: str = "page",
    url: str | None = None,
    depth: int = 0,
    published_at: str = "",
) -> dict:
    record_url = url or source.url
    doc_id = hashlib.sha1(f"{record_url}:{suffix}:{text[:500]}".encode("utf-8")).hexdigest()
    return {
        "id": doc_id,
        "source": source.name,
        "platform": source.platform,
        "type": source.type,
        "url": record_url,
        "title": title,
        "tags": source.tags,
        "depth": depth,
        "text": text,
        "characters": len(text),
        "published_at": published_at,
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


def default_keywords() -> list[str]:
    return [
        "重返未来",
        "重返未来1999",
        "Reverse 1999",
        "Reverse: 1999",
        "维尔汀",
        "十四行诗",
        "心相",
        "洞悉",
        "共鸣",
        "鬃毛邮报",
        "深眠域",
    ]


def url_allowed(source: Source, url: str) -> bool:
    parsed_seed = urlparse(source.url)
    parsed = urlparse(url)
    allowed_domains = source.allow_domains or [parsed_seed.netloc]
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.netloc not in allowed_domains:
        return False
    patterns = source.include_patterns
    if patterns and not any(re.search(pattern, url, re.IGNORECASE) for pattern in patterns):
        return False
    return True


def relevant_for_expansion(title: str, text: str, url: str, keywords: list[str]) -> bool:
    haystack = f"{title} {text[:2000]} {url}".lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def normalize_link(base_url: str, href: str) -> str:
    joined = urljoin(base_url, href.split("#", 1)[0])
    parsed = urlparse(joined)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return joined


def collect(sources: list[Source], timeout: int, delay: float, keep_raw: bool, keywords: list[str]) -> list[dict]:
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
                source_records = crawl_page_source(source, payload, timeout, delay, keep_raw, keywords)
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


def crawl_page_source(
    source: Source,
    seed_payload: str,
    timeout: int,
    delay: float,
    keep_raw: bool,
    keywords: list[str],
) -> list[dict]:
    records: list[dict] = []
    queue: list[tuple[str, int, str | None]] = [(source.url, 0, seed_payload)]
    seen: set[str] = set()
    max_pages = max(1, source.max_pages)
    max_depth = max(0, source.crawl_depth)

    while queue and len(seen) < max_pages:
        url, depth, preloaded = queue.pop(0)
        if url in seen or not url_allowed(source, url):
            continue
        seen.add(url)
        payload = preloaded if preloaded is not None else fetch(url, timeout)
        if keep_raw and preloaded is None:
            save_raw(Source(**{**source.__dict__, "url": url}), payload)
        title, text, links, published_at = extract_page_details(payload, source.selector)
        if relevant_for_expansion(title, text, url, keywords):
            records.append(
                build_record(
                    source,
                    title=title,
                    text=text,
                    url=url,
                    suffix=f"depth-{depth}-{len(seen)}",
                    depth=depth,
                    published_at=published_at,
                )
            )

        if depth >= max_depth:
            continue

        for href in links:
            next_url = normalize_link(url, href)
            if next_url and next_url not in seen and url_allowed(source, next_url):
                queue.append((next_url, depth + 1, None))
                if len(seen) + len(queue) >= max_pages:
                    break
        if delay and queue:
            time.sleep(delay)

    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Reverse: 1999 public text sources.")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--keep-raw", action="store_true")
    parser.add_argument("--output", type=Path, default=CORPUS_DIR / "latest.jsonl")
    parser.add_argument("--keywords", nargs="*", default=default_keywords())
    parser.add_argument("--replace", action="store_true", help="Replace output corpus instead of appending.")
    args = parser.parse_args()

    sources = load_sources(args.sources)
    records = collect(sources, timeout=args.timeout, delay=args.delay, keep_raw=args.keep_raw, keywords=args.keywords)
    good_records = [record for record in records if "text" in record]
    if args.replace and args.output.exists():
        args.output.unlink()
    write_corpus(good_records, args.output)
    append_metadata(records)
    print(f"Collected {len(good_records)} document(s); {len(records) - len(good_records)} error(s).")


if __name__ == "__main__":
    main()
