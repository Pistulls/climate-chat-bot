import numpy as np
import pytest

from climate_chat.ingest.chunk import Chunk
from climate_chat.ingest.embed import (
    Store,
    document_text,
    embed_chunks,
    load_store,
    model_dir,
    save_store,
    text_hash,
)

DIM = 3
TITLES = {"05": "WMO State of the Global Climate 2025", "22": "IRENA costs"}


def chunk(cid, text):
    source, no = cid.split("-")
    return Chunk(cid, source, int(no), 1, 1, len(text.split()), text)


class FakeEmbedder:
    """Vector = [len(text), call number, 1]; records every batch."""

    def __init__(self, fail_after=None):
        self.batches, self.fail_after = [], fail_after

    def __call__(self, texts):
        if self.fail_after is not None and len(self.batches) >= self.fail_after:
            raise RuntimeError("credit cap")
        self.batches.append(list(texts))
        n = len(self.batches)
        return np.array([[len(t), n, 1] for t in texts], dtype=np.float32)


def run(store, chunks, embedder, **kw):
    return embed_chunks("m", store, chunks, TITLES, embedder, **kw)


def test_model_dir_and_document_text(tmp_path):
    assert (
        model_dir(tmp_path, "openai/text-embedding-3-small").name
        == "openai--text-embedding-3-small"
    )
    assert document_text(chunk("05-0001", "Warmest year."), TITLES["05"]) == (
        "WMO State of the Global Climate 2025\n\nWarmest year."
    )


def test_hash_depends_on_model_and_text():
    assert text_hash("a", "x") != text_hash("b", "x")
    assert text_hash("a", "x") != text_hash("a", "y")
    assert text_hash("a", "x") == text_hash("a", "x")


def test_first_run_embeds_everything_in_chunk_id_order():
    fake = FakeEmbedder()
    result = run(Store(DIM), [chunk("05-0002", "b"), chunk("05-0001", "a")], fake)
    assert result.embedded == 2 and result.reused == 0
    assert result.store.ids() == ["05-0001", "05-0002"]
    assert result.store.vectors.dtype == np.float32
    assert result.store.vectors.shape == (2, DIM)


def test_second_run_reuses_the_cache():
    chunks = [chunk("05-0001", "a"), chunk("05-0002", "b")]
    first = run(Store(DIM), chunks, FakeEmbedder()).store
    fake = FakeEmbedder()
    result = run(first, chunks, fake)
    assert fake.batches == []
    assert result.reused == 2
    np.testing.assert_array_equal(result.store.vectors, first.vectors)


def test_only_changed_text_is_embedded_and_renumbered_chunks_reuse_vectors():
    first = run(Store(DIM), [chunk("05-0001", "a"), chunk("05-0002", "b")], FakeEmbedder()).store
    fake = FakeEmbedder()
    # "b" moved to 05-0001; "c" is new; "a" is gone.
    result = run(first, [chunk("05-0001", "b"), chunk("05-0002", "c")], fake)
    assert result.embedded == 1 and result.reused == 1
    assert fake.batches == [[document_text(chunk("05-0002", "c"), TITLES["05"])]]
    assert result.store.ids() == ["05-0001", "05-0002"]
    np.testing.assert_array_equal(result.store.vectors[0], first.vectors[1])


def test_other_sources_are_kept_and_this_source_replaced():
    first = run(Store(DIM), [chunk("05-0001", "a"), chunk("22-0001", "z")], FakeEmbedder()).store
    result = run(first, [chunk("22-0001", "y")], FakeEmbedder())
    assert result.store.ids() == ["05-0001", "22-0001"]
    hashes = {r["chunk_id"]: r["hash"] for r in result.store.rows}
    assert hashes["22-0001"] == text_hash("m", "IRENA costs\n\ny")


def test_identical_texts_are_embedded_once():
    fake = FakeEmbedder()
    result = run(Store(DIM), [chunk("05-0001", "same"), chunk("05-0002", "same")], fake)
    assert sum(map(len, fake.batches)) == 1
    assert len(result.store) == 2


def test_progress_is_saved_so_a_failed_run_resumes(tmp_path):
    saved = []
    chunks = [chunk(f"05-{i:04d}", f"text {i}") for i in range(1, 6)]
    with pytest.raises(RuntimeError):
        run(Store(DIM), chunks, FakeEmbedder(fail_after=2), save=saved.append, save_every=2)
    assert [len(s) for s in saved] == [2, 4]
    fake = FakeEmbedder()
    result = run(saved[-1], chunks, fake, save_every=2)
    assert sum(map(len, fake.batches)) == 1
    assert len(result.store) == 5


def test_store_round_trip(tmp_path):
    store = run(Store(DIM), [chunk("05-0001", "a"), chunk("05-0002", "b")], FakeEmbedder()).store
    save_store(tmp_path, store)
    loaded = load_store(tmp_path, DIM)
    assert loaded.rows == store.rows
    np.testing.assert_array_equal(loaded.vectors, store.vectors)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["rows.jsonl", "vectors.npy"]


def test_missing_store_is_empty_and_mismatched_store_fails(tmp_path):
    assert len(load_store(tmp_path, DIM)) == 0
    store = run(Store(DIM), [chunk("05-0001", "a")], FakeEmbedder()).store
    save_store(tmp_path, store)
    with pytest.raises(ValueError, match="expected"):
        load_store(tmp_path, 4)
