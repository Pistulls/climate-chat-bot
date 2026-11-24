"""The Classify output and the answer card (Design.md, Two-stage reply).

`from_dict` checks every field's presence and type, so model output that parses as JSON
but has the wrong shape is rejected the same way as output that doesn't parse.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

CARDS_CATEGORIES = (
    "not_happening",
    "not_us",
    "not_bad",
    "solutions_wont_work",
    "science_unreliable",
    "none",
)


def _get(data: Any, name: str, kind: type | tuple[type, ...]) -> Any:
    if not isinstance(data, dict) or name not in data:
        raise ValueError(f"missing field {name!r}")
    value = data[name]
    # bool is a subclass of int; don't let True pass as a number.
    if not isinstance(value, kind) or (kind in (int, float, (int, float)) and value is True):
        raise ValueError(f"field {name!r} has the wrong type")
    return value


def _str_list(data: Any, name: str) -> list[str]:
    value = _get(data, name, list)
    if not all(isinstance(x, str) for x in value):
        raise ValueError(f"field {name!r} must be a list of strings")
    return list(value)


@dataclass(frozen=True)
class Tone:
    register: str  # casual | formal
    hostility: str  # none | mild | hostile
    emoji: bool
    slang: bool
    language: str  # e.g. "en"

    @classmethod
    def from_dict(cls, data: Any) -> Tone:
        return cls(
            register=_get(data, "register", str),
            hostility=_get(data, "hostility", str),
            emoji=_get(data, "emoji", bool),
            slang=_get(data, "slang", bool),
            language=_get(data, "language", str),
        )


@dataclass(frozen=True)
class Classification:
    is_climate_claim: bool
    is_sceptical: bool
    claim: str
    cards_category: str
    tone: Tone

    @property
    def is_target(self) -> bool:
        """A climate claim presenting a sceptical view: the only kind the bot answers."""
        return self.is_climate_claim and self.is_sceptical

    @classmethod
    def from_dict(cls, data: Any) -> Classification:
        return cls(
            is_climate_claim=_get(data, "is_climate_claim", bool),
            is_sceptical=_get(data, "is_sceptical", bool),
            claim=_get(data, "claim", str),
            cards_category=_get(data, "cards_category", str),
            tone=Tone.from_dict(_get(data, "tone", dict)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KeyPoint:
    point: str
    source_ids: list[str]

    @classmethod
    def from_dict(cls, data: Any) -> KeyPoint:
        return cls(point=_get(data, "point", str), source_ids=_str_list(data, "source_ids"))


@dataclass(frozen=True)
class AnswerCard:
    claim: str
    cards_category: str
    fallacy: str | None
    key_points: list[KeyPoint]
    bottom_line: str
    confidence: float

    @property
    def source_ids(self) -> list[str]:
        """Every cited chunk id, in first-cited order, without duplicates."""
        return list(dict.fromkeys(i for kp in self.key_points for i in kp.source_ids))

    @classmethod
    def from_dict(cls, data: Any) -> AnswerCard:
        fallacy = _get(data, "fallacy", (str, type(None)))
        return cls(
            claim=_get(data, "claim", str),
            cards_category=_get(data, "cards_category", str),
            fallacy=fallacy or None,
            key_points=[KeyPoint.from_dict(kp) for kp in _get(data, "key_points", list)],
            bottom_line=_get(data, "bottom_line", str),
            confidence=float(_get(data, "confidence", (int, float))),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
