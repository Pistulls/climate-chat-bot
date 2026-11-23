import numpy as np
from fakes import FakeS3Vectors

from climate_chat.vectors import Match, Record, VectorIndex, batches


def index(fake=None):
    return VectorIndex("climate-chat-dev-vectors", "sources", fake or FakeS3Vectors())


def record(key):
    return Record(key, np.array([1, 2, 3], dtype=np.float32), {"source_id": key[:2]})


def test_batches():
    assert [len(b) for b in batches(list(range(1201)))] == [500, 500, 201]


def test_put_batches_at_500_and_sends_float32_lists():
    fake = FakeS3Vectors()
    n = index(fake).put([record(f"05-{i:04d}") for i in range(1, 1202)])
    puts = [kw for op, kw in fake.calls if op == "put"]
    assert n == 1201 and [len(p["vectors"]) for p in puts] == [500, 500, 201]
    first = puts[0]
    assert (
        first["vectorBucketName"] == "climate-chat-dev-vectors" and first["indexName"] == "sources"
    )
    assert first["vectors"][0]["data"] == {"float32": [1.0, 2.0, 3.0]}


def test_keys_lists_every_page():
    fake = FakeS3Vectors()
    vi = index(fake)
    vi.put([record(f"05-{i:04d}") for i in range(1, 8)])
    assert vi.keys() == [f"05-{i:04d}" for i in range(1, 8)]


def test_delete_batches_and_counts():
    fake = FakeS3Vectors()
    vi = index(fake)
    assert vi.delete([f"05-{i:04d}" for i in range(600)]) == 600
    assert [len(kw["keys"]) for op, kw in fake.calls if op == "delete"] == [500, 100]
    assert vi.delete([]) == 0


def test_query_returns_matches_with_metadata():
    fake = FakeS3Vectors()
    matches = index(fake).query(np.array([0.1, 0.2, 0.3]), top_k=2, filter={"licence": "open"})
    assert matches[0] == Match("05-0001", 0.1, {"source_id": "05"})
    sent = fake.calls[-1][1]
    assert sent["topK"] == 2 and sent["returnMetadata"] and sent["filter"] == {"licence": "open"}
    assert sent["queryVector"]["float32"] == [0.1, 0.2, 0.3] or np.allclose(
        sent["queryVector"]["float32"], [0.1, 0.2, 0.3]
    )


def test_query_without_filter_sends_none():
    fake = FakeS3Vectors()
    index(fake).query(np.zeros(3))
    assert "filter" not in fake.calls[-1][1]


def test_dimension():
    assert index(FakeS3Vectors(dimension=1536)).dimension() == 1536
