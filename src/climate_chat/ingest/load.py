"""Cached chunk vectors -> the S3 Vectors `sources` index, one source at a time.

Re-loads are idempotent without a state file: the index's existing keys for a source are
listed first, the current chunks are written (overwriting same-key vectors), and keys the
run didn't write are deleted.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from climate_chat.ingest.chunk import Chunk
from climate_chat.ingest.embed import Store, document_text, text_hash
from climate_chat.ingest.manifest import Source
from climate_chat.vectors import Record, VectorIndex


class LoadError(Exception):
    pass


def citation_url(source: Source, page: int) -> str:
    """A link to the page for PDF URLs; the plain URL for web pages and landing pages."""
    if source.url.lower().split("?")[0].endswith(".pdf"):
        return f"{source.url}#page={page}"
    return source.url


def metadata(chunk: Chunk, source: Source) -> dict[str, Any]:
    return {
        # Filterable
        "source_id": source.id,
        "type": source.type,
        "published": source.published,
        "licence": source.licence,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        # Non-filterable (Infrastructure/app/vectors.tf)
        "title": source.title,
        "citation_url": citation_url(source, chunk.page_start),
        "chunk_text": chunk.text,
    }


def records(model: str, chunks: Sequence[Chunk], source: Source, store: Store) -> list[Record]:
    """One record per chunk, with its cached vector. Fails if a vector is missing or stale."""
    assert store.vectors is not None
    rows = {row["chunk_id"]: (i, row["hash"]) for i, row in enumerate(store.rows)}
    out = []
    for chunk in chunks:
        if chunk.chunk_id not in rows:
            raise LoadError(f"{chunk.chunk_id} has no vector: run `embed` first")
        i, h = rows[chunk.chunk_id]
        if h != text_hash(model, document_text(chunk, source.title)):
            raise LoadError(f"{chunk.chunk_id}'s vector is stale: run `embed` again")
        out.append(Record(chunk.chunk_id, np.asarray(store.vectors[i]), metadata(chunk, source)))
    return out


@dataclass
class LoadPlan:
    source_id: str
    records: list[Record]
    existing: set[str]  # this source's keys already in the index

    @property
    def stale(self) -> list[str]:
        """Keys in the index for this source that this run won't write."""
        writing = {r.key for r in self.records}
        return sorted(self.existing - writing)

    @property
    def new(self) -> int:
        return sum(1 for r in self.records if r.key not in self.existing)


def plan(source_id: str, records: list[Record], index_keys: Iterable[str]) -> LoadPlan:
    existing = {k for k in index_keys if k.split("-")[0] == source_id}
    return LoadPlan(source_id, records, existing)


def apply(index: VectorIndex, load_plan: LoadPlan) -> tuple[int, int]:
    """Write first, then delete, so a failed run never leaves a source with fewer vectors."""
    written = index.put(load_plan.records)
    deleted = index.delete(load_plan.stale)
    return written, deleted
