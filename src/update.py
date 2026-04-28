from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "data" / "sources.json"
EXAMPLE_SOURCES = ROOT / "data" / "sources.example.json"
CORPUS_DIR = ROOT / "data" / "corpus"


def run(args: list[str]) -> None:
    print("+", " ".join(args))
    subprocess.run(args, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect latest Reverse: 1999 corpus and rebuild the dashboard.")
    parser.add_argument("--sources", type=Path, default=SOURCES)
    parser.add_argument("--limit", type=int, default=220)
    parser.add_argument("--max-age-days", type=int, default=365)
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--sample-only", action="store_true")
    args = parser.parse_args()

    if args.sample_only:
        run([sys.executable, "src/analyze.py", "--sample-only", "--limit", str(args.limit)])
        return

    source_path = args.sources
    if not source_path.exists():
        source_path = EXAMPLE_SOURCES
        print(f"Using {source_path} because data/sources.json does not exist.")

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = CORPUS_DIR / f"run-{stamp}.jsonl"
    run(
        [
            sys.executable,
            "src/collect.py",
            "--sources",
            str(source_path),
            "--output",
            str(output),
            "--replace",
            "--delay",
            str(args.delay),
            "--timeout",
            str(args.timeout),
        ]
    )
    run(
        [
            sys.executable,
            "src/analyze.py",
            "--limit",
            str(args.limit),
            "--max-age-days",
            str(args.max_age_days),
        ]
    )


if __name__ == "__main__":
    main()
