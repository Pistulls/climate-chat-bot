"""Ingestion command line: python -m climate_chat.ingest <stage> [--source ID ...]

Stages read and write the gitignored build/ folder, so each can be re-run on its own:

    extract   sources/docs/<file>.pdf  -> build/text/<id>.jsonl    one record per page
    chunk     build/text/<id>.jsonl    -> build/chunks/<id>.jsonl  ~500-token chunks
    embed     build/chunks/            -> build/embeddings/<model>/ vectors, cached by hash
    load      build/embeddings/<model>/ -> the `sources` index in S3 Vectors (--env, --dry-run)
    evaluate  --in-memory: the cached vectors, searched locally (the model bake-off)
              --env dev|prod: the live index, compared with the in-memory search

All embedding uses MODEL_EMBEDDING from .env. `embed` and `evaluate --in-memory` take
--model (repeatable) to compare candidates instead, as the plan 02 bake-off did.
`embed` and `evaluate` call Bedrock for `amazon.` models (Titan, the default) and
OpenRouter with the ingest key for others (INGEST_OPENROUTER_API_KEY in .env, else SSM).
Bedrock, `load` and `evaluate --env` use your AWS credentials (AWS_PROFILE).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from botocore.exceptions import (
    ClientError,
    NoCredentialsError,
    SSOTokenLoadError,
    TokenRetrievalError,
)

from climate_chat.config import ConfigError, load_settings, repo_root
from climate_chat.embeddings import embedding_client, uses_bedrock
from climate_chat.ingest import chunk as chunking
from climate_chat.ingest import embed as embedding
from climate_chat.ingest import evaluate as evaluation
from climate_chat.ingest import extract as extraction
from climate_chat.ingest import load as loading
from climate_chat.ingest.manifest import (
    ManifestError,
    Source,
    docs_dir,
    load_manifest,
    missing_files,
    to_ingest,
)
from climate_chat.openrouter import EmbeddingError, resolve_ingest_api_key
from climate_chat.vectors import VectorIndex


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


def _client(model: str) -> Any:
    """Titan (`amazon.`) uses your AWS credentials; other models the OpenRouter ingest key."""
    settings = load_settings()
    api_key = None if uses_bedrock(model) else resolve_ingest_api_key(settings)
    return embedding_client(
        model, embedding.CANDIDATES[model], settings=settings, api_key=api_key, for_ingest=True
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
        except EmbeddingError as e:  # includes a spent OpenRouter cap and Bedrock errors
            print(f"{model}: {e}. Progress so far is saved; re-run to resume.", file=sys.stderr)
            return 1
        print(
            f"{model}: {result.embedded} embedded, {result.reused} from cache, "
            f"{client.tokens_used} tokens, {time.monotonic() - started:.0f} s "
            f"-> {directory} ({len(result.store)} rows)"
        )
    return 0


def _winner_store(build: Path, args: argparse.Namespace):
    settings = load_settings(args.env)
    model = settings.model_embedding
    store = embedding.load_store(embedding.model_dir(build, model), settings.embedding_dimension)
    return settings, model, store


def run_load(sources: Sequence[Source], build: Path, args: argparse.Namespace) -> int:
    if not args.env:
        print("load needs --env dev or --env prod", file=sys.stderr)
        return 2
    chunks = _read_chunks(sources, build)
    if chunks is None:
        return 1
    settings, model, store = _winner_store(build, args)
    index = VectorIndex.sources(settings)
    if index.dimension() != settings.embedding_dimension:
        print(
            f"{index.bucket}/{index.index} is {index.dimension()}-d, but {model} vectors are "
            f"{settings.embedding_dimension}-d: apply the Terraform change first",
            file=sys.stderr,
        )
        return 1
    keys = index.keys()
    by_source = {}
    for chunk in chunks:
        by_source.setdefault(chunk.source_id, []).append(chunk)
    try:
        plans = [
            loading.plan(s.id, loading.records(model, by_source.get(s.id, []), s, store), keys)
            for s in sources
        ]
    except loading.LoadError as e:
        print(e, file=sys.stderr)
        return 1
    # A full load also removes sources that are no longer ingested (e.g. ingest = false).
    loaded = {s.id for s in sources}
    orphans = [] if args.source else sorted(k for k in keys if k.split("-")[0] not in loaded)

    action = "Would load" if args.dry_run else "Loading"
    print(f"{action} {model} vectors into {index.bucket}/{index.index} ({len(keys)} keys now)")
    print(f"{'id':<4}{'chunks':>7}{'new':>6}{'delete':>8}")
    written = deleted = 0
    for p in plans:
        if not args.dry_run:
            w, d = loading.apply(index, p)
            written, deleted = written + w, deleted + d
        print(f"{p.source_id:<4}{len(p.records):>7}{p.new:>6}{len(p.stale):>8}")
    if orphans:
        print(f"Not in the manifest's ingested sources: {len(orphans)} keys to delete")
        if not args.dry_run:
            deleted += index.delete(orphans)
    if args.dry_run:
        print("Dry run: nothing written")
    else:
        print(f"Wrote {written} vectors, deleted {deleted}; index now has {len(index.keys())} keys")
    return 0


def run_evaluate(sources: Sequence[Source], build: Path, args: argparse.Namespace) -> int:
    if args.env:
        return _evaluate_index(sources, build, args)
    if not args.in_memory:
        print("evaluate needs --in-memory or --env dev|prod", file=sys.stderr)
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
            evaluation.evaluate(
                model, myths, evaluation.in_memory(store.ids(), store.vectors), client.embed_query
            )
        )
    winner, reasons = evaluation.pick_winner(results)
    text = evaluation.report(results, winner, reasons)
    path = build / "reports" / "embedding-eval.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    print(text)
    print(f"Report: {path}")
    return 0


def _evaluate_index(sources: Sequence[Source], build: Path, args: argparse.Namespace) -> int:
    """The live index should reproduce the in-memory search; a gap points to a load bug."""
    chunks = _read_chunks(sources, build)
    if chunks is None:
        return 1
    settings, model, store = _winner_store(build, args)
    if store.ids() != sorted(c.chunk_id for c in chunks):
        print(f"{model}: embeddings don't match the chunks; run `embed` first", file=sys.stderr)
        return 1
    index = VectorIndex.sources(settings)
    client = _client(model)
    myths = evaluation.load_myths(known_ids={s.id for s in sources})
    client.embed_query("warm-up")
    queries = {m.claim: client.embed_query(m.claim) for m in myths}
    embed = queries.__getitem__
    live = evaluation.evaluate(
        model, myths, lambda q: [m.key for m in index.query(q, top_k=evaluation.K * 2)], embed
    )
    local = evaluation.evaluate(
        model, myths, evaluation.in_memory(store.ids(), store.vectors), embed
    )
    same = sum(a.top_ids == b.top_ids for a, b in zip(live.myths, local.myths, strict=True))
    overlap = sum(
        len(set(a.top_ids) & set(b.top_ids)) for a, b in zip(live.myths, local.myths, strict=True)
    ) / (evaluation.K * len(myths))
    lines = [
        f"# Index evaluation: {index.bucket}/{index.index}",
        "",
        f"Model `{model}`, {len(myths)} myths, topK {evaluation.K}.",
        "",
        "| Search | recall@5 | MRR (top 10) |",
        "|---|---|---|",
        f"| S3 Vectors ({settings.env}) | {live.hits}/{len(myths)} | {live.mrr:.2f} |",
        f"| In memory (exact) | {local.hits}/{len(myths)} | {local.mrr:.2f} |",
        "",
        f"- Identical top 5: {same}/{len(myths)} myths; top-5 overlap {overlap:.0%}.",
    ]
    text = "\n".join(lines) + "\n"
    path = build / "reports" / f"index-eval-{settings.env}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    print(text)
    print(f"Report: {path}")
    return 0 if live.hits == local.hits else 1


STAGES = {
    "extract": run_extract,
    "chunk": run_chunk,
    "embed": run_embed,
    "load": run_load,
    "evaluate": run_evaluate,
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m climate_chat.ingest",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
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
        help="embed/evaluate --in-memory: use this model (repeatable; default: MODEL_EMBEDDING)",
    )
    parser.add_argument(
        "--in-memory",
        action="store_true",
        help="evaluate: search the cached vectors locally instead of the S3 Vectors index",
    )
    parser.add_argument(
        "--env",
        choices=("dev", "prod"),
        help="load/evaluate: the environment whose `sources` index to use",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="load: print what would change, write nothing"
    )
    args = parser.parse_args(argv)

    # pdfminer logs every malformed font descriptor; the text is still extracted.
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    try:
        sources = to_ingest(load_manifest(), args.source)
    except ManifestError as e:
        print(e, file=sys.stderr)
        return 2
    try:
        if args.model is None and args.stage in ("embed", "evaluate"):
            configured = load_settings(args.env).model_embedding
            if configured not in embedding.CANDIDATES:
                print(f"MODEL_EMBEDDING {configured!r} isn't a known model", file=sys.stderr)
                return 2
            args.model = [configured]
        return STAGES[args.stage](sources, args.build or build_dir(), args)
    except (ConfigError, evaluation.EvalError) as e:
        print(e, file=sys.stderr)
        return 2
    except ClientError as e:
        print(f"AWS error: {e}", file=sys.stderr)
        return 1
    except (NoCredentialsError, SSOTokenLoadError, TokenRetrievalError) as e:
        print(
            f"{e}\nSign in first: aws sso login (with the profile in AWS_PROFILE)", file=sys.stderr
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
