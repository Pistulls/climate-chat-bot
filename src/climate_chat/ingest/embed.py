"""Chunks -> vectors, cached on disk so re-runs and re-loads never pay twice.

One store per model, in build/embeddings/<model with "/" -> "--">/:

    vectors.npy   float32, one row per chunk (N x dim)
    rows.jsonl    row i -> {"chunk_id": "05-0042", "hash": sha256(model + embedded text)}

Rows are sorted by chunk id. A vector is reused whenever its hash is already in the store,
even under another chunk id, so re-chunking only pays for text that changed.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from climate_chat.ingest.chunk import Chunk

# The bake-off candidates (Design.md) and their native dimensions.
CANDIDATES = {
    "qwen/qwen3-embedding-8b": 4096,
    "openai/text-embedding-3-small": 1536,
}
SAVE_EVERY = 256  # chunks embedded between saves, so a stopped run keeps its progress

Embedder = Callable[[Sequence[str]], np.ndarray]


def model_dir(build: Path, model: str) -> Path:
    return build / "embeddings" / model.replace("/", "--")


def document_text(chunk: Chunk, title: str) -> str:
    """What gets embedded: the source title, then the chunk. Many chunks never name their
    source ("the 2024 figures show..."), and the title places them."""
    return f"{title}\n\n{chunk.text}"


def text_hash(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()


@dataclass
class Store:
    dimension: int
    rows: list[dict[str, str]] = field(default_factory=list)
    vectors: np.ndarray | None = None

    def __post_init__(self) -> None:
        if self.vectors is None:
            self.vectors = np.empty((0, self.dimension), dtype=np.float32)

    def __len__(self) -> int:
        return len(self.rows)

    def by_hash(self) -> dict[str, np.ndarray]:
        assert self.vectors is not None
        return {row["hash"]: self.vectors[i] for i, row in enumerate(self.rows)}

    def ids(self) -> list[str]:
        return [row["chunk_id"] for row in self.rows]


def load_store(directory: Path, dimension: int) -> Store:
    rows_path, vectors_path = directory / "rows.jsonl", directory / "vectors.npy"
    if not rows_path.is_file() or not vectors_path.is_file():
        return Store(dimension)
    rows = [json.loads(line) for line in rows_path.read_text().splitlines() if line]
    vectors = np.load(vectors_path)
    if vectors.shape != (len(rows), dimension):
        raise ValueError(
            f"{directory}: vectors are {vectors.shape}, expected ({len(rows)}, {dimension})"
        )
    return Store(dimension, rows, vectors)


def save_store(directory: Path, store: Store) -> None:
    """Write both files via temporary names, so a crash never leaves them out of step."""
    directory.mkdir(parents=True, exist_ok=True)
    tmp_vectors = directory / "vectors.tmp.npy"
    tmp_rows = directory / "rows.tmp.jsonl"
    assert store.vectors is not None
    np.save(tmp_vectors, store.vectors.astype(np.float32, copy=False))
    tmp_rows.write_text("".join(json.dumps(row) + "\n" for row in store.rows))
    os.replace(tmp_vectors, directory / "vectors.npy")
    os.replace(tmp_rows, directory / "rows.jsonl")


@dataclass
class EmbedResult:
    store: Store
    embedded: int  # texts sent to the API
    reused: int  # chunks whose vector came from the cache


def embed_chunks(
    model: str,
    store: Store,
    chunks: Sequence[Chunk],
    titles: dict[str, str],
    embed: Embedder,
    save: Callable[[Store], None] | None = None,
    save_every: int = SAVE_EVERY,
) -> EmbedResult:
    """Bring `store` up to date for the sources in `chunks`.

    Rows of those sources are replaced, so chunks that no longer exist are dropped. Rows of
    other sources are kept. New vectors are saved every `save_every` texts.
    """
    texts = {c.chunk_id: document_text(c, titles[c.source_id]) for c in chunks}
    hashes = {cid: text_hash(model, text) for cid, text in texts.items()}
    cached = store.by_hash()
    todo: dict[str, str] = {}  # hash -> text, deduplicated
    for cid, h in hashes.items():
        if h not in cached:
            todo.setdefault(h, texts[cid])

    sources = {c.source_id for c in chunks}
    kept = [i for i, row in enumerate(store.rows) if row["chunk_id"].split("-")[0] not in sources]
    pending = list(todo.items())
    for start in range(0, len(pending), save_every):
        batch = pending[start : start + save_every]
        vectors = embed([text for _, text in batch])
        cached.update({h: vectors[i] for i, (h, _) in enumerate(batch)})
        if save:
            save(_merge(store, kept, hashes, cached, partial=True))

    result = _merge(store, kept, hashes, cached, partial=False)
    if save:
        save(result)
    reused = sum(1 for h in hashes.values() if h not in todo)
    return EmbedResult(result, embedded=len(todo), reused=reused)


def _merge(
    store: Store,
    kept: Iterable[int],
    hashes: dict[str, str],
    cached: dict[str, np.ndarray],
    partial: bool,
) -> Store:
    """Kept rows of other sources plus this run's chunks (those embedded so far if partial)."""
    assert store.vectors is not None
    entries = [(store.rows[i]["chunk_id"], store.rows[i]["hash"], store.vectors[i]) for i in kept]
    for cid, h in hashes.items():
        if h in cached:
            entries.append((cid, h, cached[h]))
        elif not partial:
            raise AssertionError(f"no vector for {cid}")
    entries.sort(key=lambda e: e[0])
    rows = [{"chunk_id": cid, "hash": h} for cid, h, _ in entries]
    vectors = (
        np.vstack([v for _, _, v in entries]).astype(np.float32)
        if entries
        else np.empty((0, store.dimension), dtype=np.float32)
    )
    return Store(store.dimension, rows, vectors)
