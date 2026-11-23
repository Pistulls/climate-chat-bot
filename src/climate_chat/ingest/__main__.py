"""Ingestion command line: python -m climate_chat.ingest <stage> [--source ID ...]

Stages read and write the gitignored build/ folder, so each can be re-run on its own:

    extract   sources/docs/<file>.pdf  -> build/text/<id>.jsonl    one record per page
    chunk     build/text/<id>.jsonl    -> build/chunks/<id>.jsonl  ~500-token chunks
    embed     build/chunks/            -> build/embeddings/<model>/ vectors, cached by hash
    evaluate  build/embeddings/<model>/ -> build/reports/embedding-eval.md  (--in-memory)

`embed` and `evaluate` call OpenRouter with the ingest key (INGEST_OPENROUTER_API_KEY in
.env, else SSM). They default to both bake-off candidates; pick one with --model.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from climate_chat.config import ConfigError, load_settings, repo_root
from climate_chat.ingest import chunk as chunking
from climate_chat.ingest import embed as embedding
from climate_chat.ingest import evaluate as evaluation
from climate_chat.ingest import extract as extraction
from climate_chat.ingest.manifest import (
    ManifestError,
    Source,
    docs_dir,
    load_manifest,
    missing_files,
    to_ingest,
)
from climate_chat.openrouter import CreditCapReached, EmbeddingClient, resolve_ingest_api_key


def build_dir() -> Path:
    return repo_root() / "build"


def run_extract(sources: Sequence[Source], build: Path, args: argparse.Namespace) -> int:
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


def run_chunk(sources: Sequence[Source], build: Path, args: argparse.Namespace) -> int:
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


def _read_chunks(sources: Sequence[Source], build: Path) -> list[chunking.Chunk] | None:
    missing = [s.id for s in sources if not (build / "chunks" / f"{s.id}.jsonl").is_file()]
    if missing:
        print(f"No chunks for {', '.join(missing)}: run `chunk` first", file=sys.stderr)
        return None
    return [c for s in sources for c in chunking.read_chunks(build / "chunks" / f"{s.id}.jsonl")]


def _client(model: str) -> EmbeddingClient:
    settings = load_settings()
    return EmbeddingClient.for_model(
        model, embedding.CANDIDATES[model], resolve_ingest_api_key(settings)
    )


def run_embed(sources: Sequence[Source], build: Path, args: argparse.Namespace) -> int:
    chunks = _read_chunks(sources, build)
    if chunks is None:
        return 1
    titles = {s.id: s.title for s in sources}
    for model in args.model:
        client = _client(model)
        directory = embedding.model_dir(build, model)
        store = embedding.load_store(directory, client.dimension)
        started = time.monotonic()
        try:
            result = embedding.embed_chunks(
                model,
                store,
                chunks,
                titles,
                client.embed_documents,
                save=lambda s, d=directory: embedding.save_store(d, s),
            )
        except CreditCapReached as e:
            print(f"{model}: {e}. Progress so far is saved; re-run to resume.", file=sys.stderr)
            return 1
        print(
            f"{model}: {result.embedded} embedded, {result.reused} from cache, "
            f"{client.tokens_used} tokens, {time.monotonic() - started:.0f} s "
            f"-> {directory} ({len(result.store)} rows)"
        )
    return 0


def run_evaluate(sources: Sequence[Source], build: Path, args: argparse.Namespace) -> int:
    if not args.in_memory:
        print("Only --in-memory is available until the index is loaded (Phase 5)", file=sys.stderr)
        return 2
    chunks = _read_chunks(sources, build)
    if chunks is None:
        return 1
    current = sorted(c.chunk_id for c in chunks)
    myths = evaluation.load_myths(known_ids={s.id for s in sources})
    results = []
    for model in args.model:
        client = _client(model)
        store = embedding.load_store(embedding.model_dir(build, model), client.dimension)
        if store.ids() != current:
            print(f"{model}: embeddings don't match the chunks; run `embed` first", file=sys.stderr)
            return 1
        client.embed_query("warm-up")  # connection set-up isn't query latency
        results.append(
            evaluation.evaluate(model, myths, store.ids(), store.vectors, client.embed_query)
        )
    winner, reasons = evaluation.pick_winner(results)
    text = evaluation.report(results, winner, reasons)
    path = build / "reports" / "embedding-eval.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    print(text)
    print(f"Report: {path}")
    return 0


STAGES = {"extract": run_extract, "chunk": run_chunk, "embed": run_embed, "evaluate": run_evaluate}


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
    parser.add_argument(
        "--model",
        action="append",
        choices=embedding.CANDIDATES,
        help="embed/evaluate: this model only (repeatable; default: both candidates)",
    )
    parser.add_argument(
        "--in-memory",
        action="store_true",
        help="evaluate: search the cached vectors locally instead of the S3 Vectors index",
    )
    args = parser.parse_args(argv)
    args.model = args.model or list(embedding.CANDIDATES)

    # pdfminer logs every malformed font descriptor; the text is still extracted.
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    try:
        sources = to_ingest(load_manifest(), args.source)
    except ManifestError as e:
        print(e, file=sys.stderr)
        return 2
    try:
        return STAGES[args.stage](sources, args.build or build_dir(), args)
    except (ConfigError, evaluation.EvalError) as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
