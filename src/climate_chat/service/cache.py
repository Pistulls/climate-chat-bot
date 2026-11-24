"""The response cache: answer cards keyed on the embedded normalised claim
(Design.md, Response cache writes).

Each entry also stores the title, link and pages of every chunk the card cites, so a cache
hit can build the reply's citations without a second lookup in the sources index.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from climate_chat.service.cards import AnswerCard
from climate_chat.vectors import Record, VectorIndex

# Per cited chunk id: {"title", "url", "pages"}.
Sources = dict[str, dict[str, Any]]


@dataclass(frozen=True)
class CachedAnswer:
    card: AnswerCard
    sources: Sources


class AnswerCache:
    def __init__(self, index: VectorIndex, max_distance: float):
        self.index = index
        self.max_distance = max_distance

    def get(self, vector: np.ndarray) -> CachedAnswer | None:
        matches = self.index.query(vector, top_k=1)
        if not matches or matches[0].distance > self.max_distance:
            return None
        try:
            blob = json.loads(matches[0].metadata["answer_card"])
            return CachedAnswer(AnswerCard.from_dict(blob["card"]), dict(blob["sources"]))
        except KeyError, TypeError, ValueError:
            return None  # an unreadable entry is treated as a miss and rewritten

    def put(self, vector: np.ndarray, card: AnswerCard, sources: Sources) -> None:
        key = hashlib.sha256(card.claim.encode()).hexdigest()[:32]
        blob = json.dumps({"card": card.to_dict(), "sources": sources}, ensure_ascii=False)
        metadata = {
            # Non-filterable (Infrastructure/app/vectors.tf)
            "answer_card": blob,
            "claim": card.claim,
            # Filterable, so weak entries can be found and removed later
            "confidence": card.confidence,
            "cards_category": card.cards_category,
        }
        self.index.put([Record(key, vector, metadata)])
