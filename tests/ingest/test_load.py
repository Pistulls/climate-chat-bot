import dataclasses

import numpy as np
import pytest
from fakes import FakeS3Vectors

from climate_chat.ingest.chunk import Chunk
from climate_chat.ingest.embed import Store, document_text, text_hash
from climate_chat.ingest.load import LoadError, apply, citation_url, metadata, plan, records
from climate_chat.ingest.manifest import Source
from climate_chat.vectors import VectorIndex

MODEL = "openai/text-embedding-3-small"
SOURCE = Source(
    id="05",
    file="05-wmo.pdf",
    title="WMO State of the Global Climate 2025",
    url="https://library.wmo.int/idurl/4/69807",
    type="annual_report",
    published=2026,
    snapshot=False,
    licence="restricted",
    ingest=True,
)


def chunk(n, text=None, pages=(3, 4)):
    return Chunk(f"05-{n:04d}", "05", n, pages[0], pages[1], 10, text or f"chunk {n} text")


def store_for(chunks, source=SOURCE):
    rows = [
        {"chunk_id": c.chunk_id, "hash": text_hash(MODEL, document_text(c, source.title))}
        for c in chunks
    ]
    vectors = np.arange(len(chunks) * 3, dtype=np.float32).reshape(len(chunks), 3)
    return Store(3, rows, vectors)


class TestMetadata:
    def test_keys_and_values(self):
        meta = metadata(chunk(42, pages=(12, 13)), SOURCE)
        assert meta == {
            "source_id": "05",
            "type": "annual_report",
            "published": 2026,
            "licence": "restricted",
            "page_start": 12,
            "page_end": 13,
            "title": "WMO State of the Global Climate 2025",
            "citation_url": "https://library.wmo.int/idurl/4/69807",
            "chunk_text": "chunk 42 text",
        }

    def test_pdf_urls_link_to_the_page(self):
        pdf = dataclasses.replace(SOURCE, url="https://example.org/report.pdf")
        assert citation_url(pdf, 12) == "https://example.org/report.pdf#page=12"
        assert citation_url(SOURCE, 12) == SOURCE.url


class TestRecords:
    def test_one_record_per_chunk_with_its_vector(self):
        chunks = [chunk(1), chunk(2)]
        out = records(MODEL, chunks, SOURCE, store_for(chunks))
        assert [r.key for r in out] == ["05-0001", "05-0002"]
        assert out[1].vector.tolist() == [3.0, 4.0, 5.0]
        assert out[1].metadata["chunk_text"] == "chunk 2 text"

    def test_missing_vector(self):
        with pytest.raises(LoadError, match="no vector"):
            records(MODEL, [chunk(1), chunk(2)], SOURCE, store_for([chunk(1)]))

    def test_stale_vector(self):
        store = store_for([chunk(1, "old text")])
        with pytest.raises(LoadError, match="stale"):
            records(MODEL, [chunk(1, "new text")], SOURCE, store)


class TestPlanAndApply:
    def setup_method(self):
        self.fake = FakeS3Vectors()
        self.index = VectorIndex("b", "sources", self.fake)

    def load(self, chunks):
        recs = records(MODEL, chunks, SOURCE, store_for(chunks))
        p = plan("05", recs, self.index.keys())
        return p, apply(self.index, p)

    def test_first_load_writes_everything(self):
        p, (written, deleted) = self.load([chunk(1), chunk(2)])
        assert (p.new, p.stale, written, deleted) == (2, [], 2, 0)
        assert sorted(self.fake.stored) == ["05-0001", "05-0002"]

    def test_reload_is_idempotent(self):
        self.load([chunk(1), chunk(2)])
        p, (_, deleted) = self.load([chunk(1), chunk(2)])
        assert (p.new, p.stale, deleted) == (0, [], 0)
        assert sorted(self.fake.stored) == ["05-0001", "05-0002"]

    def test_fewer_chunks_delete_the_leftovers(self):
        self.load([chunk(n) for n in range(1, 5)])
        p, (_, deleted) = self.load([chunk(1), chunk(2)])
        assert p.stale == ["05-0003", "05-0004"] and deleted == 2
        assert sorted(self.fake.stored) == ["05-0001", "05-0002"]

    def test_other_sources_are_untouched(self):
        self.fake.stored["12-0001"] = {"key": "12-0001"}
        self.fake.stored["050-0001"] = {"key": "050-0001"}  # not source 05, despite the prefix
        p, _ = self.load([chunk(1)])
        assert p.stale == []
        assert {"12-0001", "050-0001"} <= set(self.fake.stored)

    def test_writes_happen_before_deletes(self):
        self.load([chunk(n) for n in range(1, 4)])
        self.fake.calls.clear()
        self.load([chunk(1)])
        assert [op for op, _ in self.fake.calls] == ["put", "delete"]
