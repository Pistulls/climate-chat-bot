import pytest

from climate_chat.service.cards import AnswerCard, Classification, KeyPoint, Tone

CARD = {
    "claim": "Solar is pointless because it doesn't generate at night",
    "cards_category": "solutions_wont_work",
    "fallacy": "Oversimplification",
    "key_points": [
        {"point": "Storage covers the evening peak.", "source_ids": ["24-0010"]},
        {"point": "Solar made 7% of electricity in 2024.", "source_ids": ["24-0003", "20-0001"]},
    ],
    "bottom_line": "Night-time is a storage question, not a reason to skip solar.",
    "confidence": 0.8,
}

CLASSIFICATION = {
    "is_climate_claim": True,
    "is_sceptical": True,
    "claim": "Solar is pointless because it doesn't generate at night",
    "cards_category": "solutions_wont_work",
    "tone": {
        "register": "casual",
        "hostility": "mild",
        "emoji": True,
        "slang": True,
        "language": "en",
    },
}


def test_answer_card_round_trip():
    card = AnswerCard.from_dict(CARD)
    assert card.key_points[1] == KeyPoint(
        "Solar made 7% of electricity in 2024.", ["24-0003", "20-0001"]
    )
    assert card.to_dict() == CARD


def test_answer_card_source_ids_in_order_without_duplicates():
    data = {**CARD, "key_points": [*CARD["key_points"], {"point": "p", "source_ids": ["24-0010"]}]}
    assert AnswerCard.from_dict(data).source_ids == ["24-0010", "24-0003", "20-0001"]


def test_answer_card_null_fallacy_allowed():
    assert AnswerCard.from_dict({**CARD, "fallacy": None}).fallacy is None


@pytest.mark.parametrize("field", ["claim", "key_points", "bottom_line", "confidence"])
def test_answer_card_rejects_missing_field(field):
    data = {k: v for k, v in CARD.items() if k != field}
    with pytest.raises(ValueError, match=field):
        AnswerCard.from_dict(data)


@pytest.mark.parametrize(
    "bad",
    [
        {"confidence": "high"},
        {"key_points": "none"},
        {"key_points": [{"point": "p", "source_ids": "24-0010"}]},
        {"key_points": [{"point": 3, "source_ids": []}]},
    ],
)
def test_answer_card_rejects_wrong_types(bad):
    with pytest.raises(ValueError):
        AnswerCard.from_dict({**CARD, **bad})


def test_classification_from_dict():
    c = Classification.from_dict(CLASSIFICATION)
    assert c.tone == Tone("casual", "mild", True, True, "en")
    assert c.is_target
    assert c.to_dict() == CLASSIFICATION


def test_classification_not_sceptical_is_not_target():
    c = Classification.from_dict({**CLASSIFICATION, "is_sceptical": False})
    assert not c.is_target


def test_classification_rejects_missing_tone():
    data = {k: v for k, v in CLASSIFICATION.items() if k != "tone"}
    with pytest.raises(ValueError, match="tone"):
        Classification.from_dict(data)
