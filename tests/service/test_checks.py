from test_cards import CARD

from climate_chat.service.cards import AnswerCard
from climate_chat.service.checks import check_card, check_reply, numbers_in

RETRIEVED = {"24-0010", "24-0003", "20-0001", "05-0042", "11-0007"}


def card(**overrides):
    return AnswerCard.from_dict({**CARD, **overrides})


# --- numbers_in ---


def test_numbers_in_normalises():
    assert numbers_in("1,000 tonnes, 1.5°C and 45% more") == {"1000", "1.5", "45"}


def test_numbers_in_trailing_zeros_equal():
    assert numbers_in("1.50 and 2.0") == {"1.5", "2"}


def test_numbers_in_ignores_chemical_formulas():
    assert numbers_in("CO2, CH4 and N2O rose") == set()


def test_numbers_in_keeps_numbers_with_units_after():
    assert numbers_in("5bn people, the 2nd warmest, 10x cheaper") == {"5", "2", "10"}


def test_numbers_in_ranges_and_years():
    assert numbers_in("between 1.5-2°C since 1998") == {"1.5", "2", "1998"}


def test_numbers_in_sentence_final_full_stop():
    assert numbers_in("It rose by 45.") == {"45"}


# --- check_card ---


def test_card_passes_when_all_sources_retrieved():
    assert check_card(card(), RETRIEVED) == []


def test_card_rejects_unretrieved_id():
    bad = card(key_points=[{"point": "p", "source_ids": ["99-0001"]}])
    problems = check_card(bad, RETRIEVED)
    assert any("99-0001" in p for p in problems)


def test_card_rejects_reformatted_id():
    bad = card(key_points=[{"point": "p", "source_ids": ["05-42"]}])
    assert check_card(bad, RETRIEVED) != []


def test_card_rejects_point_without_source():
    bad = card(key_points=[{"point": "p", "source_ids": []}])
    assert check_card(bad, RETRIEVED) != []


def test_card_rejects_no_key_points():
    assert check_card(card(key_points=[]), RETRIEVED) != []


# --- check_reply ---


def test_reply_passes():
    reply = "Solar made 7% of electricity in 2024, and storage covers the evening."
    assert check_reply(reply, ["24-0003"], card()) == []


def test_reply_rejects_new_number():
    problems = check_reply("Solar made 12% of electricity in 2024.", ["24-0003"], card())
    assert any("12" in p for p in problems)


def test_reply_allows_card_numbers_reformatted():
    c = card(bottom_line="About 1,000 GW were added, 7.0% of the total.")
    assert check_reply("About 1000 GW were added, 7% of the total.", ["24-0003"], c) == []


def test_reply_rejects_unknown_source():
    problems = check_reply("Storage helps.", ["24-0010", "05-0042"], card())
    assert any("05-0042" in p for p in problems)


def test_reply_rejects_empty():
    assert check_reply("  ", [], card()) != []


def test_reply_may_cite_nothing():
    assert check_reply("Storage helps at night.", [], card()) == []


def test_reply_rejects_over_length():
    problems = check_reply("Storage helps. " * 20, [], card(), max_chars=280)
    assert any("280" in p for p in problems)


def test_reply_at_length_limit_passes():
    assert check_reply("a" * 280, [], card(), max_chars=280) == []


def test_card_rejects_long_fallacy():
    long = card(fallacy="Oversimplification and cherry picking: the claim treats natural CO2")
    assert any("fallacy" in p for p in check_card(long, RETRIEVED))


def test_card_allows_short_fallacy_or_none():
    assert check_card(card(fallacy="Cherry picking"), RETRIEVED) == []
    assert check_card(card(fallacy=None), RETRIEVED) == []
