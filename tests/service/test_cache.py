import hashlib
import json

import numpy as np
from test_cards import CARD

from climate_chat.service.cache import AnswerCache, CachedAnswer
from climate_chat.service.cards import AnswerCard
from climate_chat.vectors import VectorIndex

SOURCES = {
    "24-0010": {"title": "Ember 2025", "url": "https://example.org/ember#page=12", "pages": "12"},
    "24-0003": {"title": "Ember 2025", "url": "https://example.org/ember#page=3", "pages": "3"},
    "20-0001": {"title": "IEA 2025", "url": "https://example.org/iea#page=1", "pages": "1-2"},
}


class FakeCacheVectors:
    """query_vectors returns whatever is in `results`; put_vectors records what's written."""

    def __init__(self, results=()):
        self.results = list(results)
        self.queries, self.puts = [], []

    def query_vectors(self, **kwargs):
        self.queries.append(kwargs)
        return {"vectors": self.results}

    def put_vectors(self, **kwargs):
        self.puts.append(kwargs)


def cache(fake, max_distance=0.15):
    return AnswerCache(VectorIndex("bucket", "response-cache", fake), max_distance)


def stored(distance, card=CARD, sources=SOURCES):
    blob = json.dumps({"card": card, "sources": sources})
    return {"key": "k", "distance": distance, "metadata": {"answer_card": blob}}


VECTOR = np.array([0.1, 0.2, 0.3], dtype=np.float32)


def test_cache_miss_when_empty():
    fake = FakeCacheVectors()
    assert cache(fake).get(VECTOR) is None
    assert fake.queries[0]["topK"] == 1


def test_cache_hit_within_distance():
    hit = cache(FakeCacheVectors([stored(0.12)])).get(VECTOR)
    assert hit == CachedAnswer(AnswerCard.from_dict(CARD), SOURCES)


def test_cache_hit_at_exact_threshold():
    assert cache(FakeCacheVectors([stored(0.15)])).get(VECTOR) is not None


def test_cache_miss_beyond_distance():
    assert cache(FakeCacheVectors([stored(0.16)])).get(VECTOR) is None


def test_cache_corrupt_entry_is_a_miss():
    bad = {"key": "k", "distance": 0.01, "metadata": {"answer_card": "{not json"}}
    assert cache(FakeCacheVectors([bad])).get(VECTOR) is None
    wrong_shape = stored(0.01, card={"claim": "only a claim"})
    assert cache(FakeCacheVectors([wrong_shape])).get(VECTOR) is None


def test_cache_put_metadata():
    fake = FakeCacheVectors()
    card = AnswerCard.from_dict(CARD)
    cache(fake).put(VECTOR, card, SOURCES)
    (vector,) = fake.puts[0]["vectors"]
    assert vector["key"] == hashlib.sha256(CARD["claim"].encode()).hexdigest()[:32]
    assert vector["data"]["float32"] == VECTOR.tolist()
    meta = vector["metadata"]
    assert json.loads(meta["answer_card"]) == {"card": CARD, "sources": SOURCES}
    assert meta["claim"] == CARD["claim"]
    assert meta["confidence"] == 0.8
    assert meta["cards_category"] == "solutions_wont_work"
