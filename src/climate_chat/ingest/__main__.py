"""Ingestion command line: python -m climate_chat.ingest <stage> [--source ID ...]

Stages read and write the gitignored build/ folder, so each can be re-run on its own:

    extract   sources/docs/<file>.pdf  -> build/text/<id>.jsonl    one record per page
    chunk     build/text/<id>.jsonl    -> build/chunks/<id>.jsonl  ~500-token chunks
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from climate_chat.config import repo_root
from climate_chat.ingest import chunk as chunking
from climate_chat.ingest import extract as extraction
from climate_chat.ingest.manifest import (
    ManifestError,
    Source,
    docs_dir,
    load_manifest,
    missing_files,
    to_ingest,
)


def build_dir() -> Path:
    return repo_root() / "build"


def run_extract(sources: Sequence[Source], build: Path) -> int:
    missing = missing_files(sources)
    if missing:
        names = ", ".join(s.file for s in missing)
        print(f"Missing PDFs in {docs_dir()}: {names}", file=sys.stderr)
        return 1
    print(f"{'id':<4}{'pages':>6}{'words':>9}{'kept':>6}  {'dropped':<44}{'secs':>5}")
    for source in sources:
        started = time.monotonic()
        raw = extraction.read_pdf(source.path(docs_dir()))
        result = extraction.clean(raw)
        extraction.write_pages(build / "text" / f"{source.id}.jsonl", result.pages)
        before = sum(len(p.text.split()) for p in raw)
        after = sum(len(p.text.split()) for p in result.pages)
        dropped = ", ".join(f"{k} {v}" for k, v in result.dropped.items() if v) or "-"
        kept = f"{after / before:.0%}" if before else "-"
        secs = time.monotonic() - started
        print(f"{source.id:<4}{len(raw):>6}{before:>9}{kept:>6}  {dropped:<44}{secs:>5.0f}")
        for warning in result.warnings:
            print(f"    warning: {warning}")
    return 0


def run_chunk(sources: Sequence[Source], build: Path) -> int:
    missing = [s.id for s in sources if not (build / "text" / f"{s.id}.jsonl").is_file()]
    if missing:
        print(f"No extracted text for {', '.join(missing)}: run `extract` first", file=sys.stderr)
        return 1
    total_chunks = total_tokens = 0
    print(f"{'id':<4}{'chunks':>7}{'tokens':>9}{'smallest':>10}{'largest':>9}{'skipped':>9}")
    for source in sources:
        pages = extraction.read_pages(build / "text" / f"{source.id}.jsonl")
        result = chunking.chunk_pages(source.id, pages)
        chunks = result.chunks
        chunking.write_chunks(build / "chunks" / f"{source.id}.jsonl", chunks)
        sizes = [c.tokens for c in chunks] or [0]
        total_chunks += len(chunks)
        total_tokens += sum(sizes)
        print(
            f"{source.id:<4}{len(chunks):>7}{sum(sizes):>9}{min(sizes):>10}{max(sizes):>9}"
            f"{result.skipped:>9}"
        )
    print(f"{'all':<4}{total_chunks:>7}{total_tokens:>9}")
    return 0


STAGES = {"extract": run_extract, "chunk": run_chunk}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m climate_chat.ingest", description=__doc__)
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument(
        "--source",
        action="append",
        metavar="ID",
        help="process only this source id, e.g. 05 (repeatable; default: all with ingest = true)",
    )
    parser.add_argument("--build", type=Path, default=None, help="build folder (default: build/)")
    args = parser.parse_args(argv)

    # pdfminer logs every malformed font descriptor; the text is still extracted.
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    try:
        sources = to_ingest(load_manifest(), args.source)
    except ManifestError as e:
        print(e, file=sys.stderr)
        return 2
    return STAGES[args.stage](sources, args.build or build_dir())


if __name__ == "__main__":
    sys.exit(main())
