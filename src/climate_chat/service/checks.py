"""Code checks that keep the model to the retrieved facts (Design.md, Two-stage reply).

Each check returns a list of problems; an empty list means the output passed.
"""

from __future__ import annotations

import re

from climate_chat.service.cards import AnswerCard

# A number not glued to a preceding letter (so CO2, CH4 and N2O aren't numbers), with
# optional thousands commas and decimals. Units or suffixes after it don't matter.
_NUMBER = re.compile(r"(?<![A-Za-z\d])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![A-Za-z\d.,])\d+(?:\.\d+)?")


def _normalise(number: str) -> str:
    number = number.replace(",", "")
    if "." in number:
        number = number.rstrip("0").rstrip(".")
    return number


def numbers_in(text: str) -> set[str]:
    return {_normalise(m) for m in _NUMBER.findall(text)}


def _card_text(card: AnswerCard) -> str:
    parts = [card.claim, card.fallacy or "", card.bottom_line]
    parts += [kp.point for kp in card.key_points]
    return "\n".join(parts)


MAX_FALLACY_WORDS = 4


def check_card(card: AnswerCard, retrieved_ids: set[str]) -> list[str]:
    """Every key point must cite at least one chunk, and only chunks that were retrieved.
    The fallacy is a short label the UI can show, not an explanation."""
    problems = []
    if card.fallacy and len(card.fallacy.split()) > MAX_FALLACY_WORDS:
        problems.append(f"the fallacy is more than {MAX_FALLACY_WORDS} words")
    if not card.key_points:
        problems.append("the card has no key points")
    for n, kp in enumerate(card.key_points, 1):
        if not kp.source_ids:
            problems.append(f"key point {n} cites no source")
        problems += [
            f"key point {n} cites {sid}, which wasn't retrieved"
            for sid in kp.source_ids
            if sid not in retrieved_ids
        ]
    return problems


def check_reply(
    reply: str, source_ids: list[str], card: AnswerCard, max_chars: int | None = None
) -> list[str]:
    """The reply may only cite the card's sources and use the card's numbers, and must fit
    the platform's length."""
    if not reply.strip():
        return ["the reply is empty"]
    if max_chars is not None and len(reply.strip()) > max_chars:
        return [f"the reply is longer than {max_chars} characters"]
    allowed_ids = set(card.source_ids)
    problems = [
        f"the reply cites {sid}, which isn't in the card"
        for sid in source_ids
        if sid not in allowed_ids
    ]
    allowed_numbers = numbers_in(_card_text(card))
    problems += [
        f"the reply uses the number {n}, which isn't in the card"
        for n in sorted(numbers_in(reply) - allowed_numbers)
    ]
    return problems
