from datetime import date
from decimal import Decimal

import pytest
from fakes import FakeLogTable

from climate_chat.service.logs import BadCursor, read_logs

TODAY = date(2026, 11, 26)


def row(day, time, rid, **extra):
    return {
        "pk": f"day#{day}",
        "sk": f"{day}T{time}.000Z#{rid}",
        "expires_at": Decimal(1),
        "comment": f"comment {rid}",
        "outcome": "reply",
        "cost": Decimal("0.0002"),
        "latency_ms": Decimal(1200),
        **extra,
    }


def ids(page):
    return [i["request_id"] for i in page["items"]]


def test_newest_first_across_days_and_pages():
    table = FakeLogTable(
        [
            row("2026-11-26", "09:00:00", "a"),
            row("2026-11-26", "10:00:00", "b"),
            row("2026-11-24", "23:00:00", "c"),  # 25th had no traffic
            row("2026-11-24", "08:00:00", "d"),
            row("2026-11-24", "07:00:00", "e"),
        ]
    )
    first = read_logs(table, today=TODAY, days=90, limit=3, cursor=None)
    assert ids(first) == ["b", "a", "c"]
    assert first["next"]

    second = read_logs(table, today=TODAY, days=90, limit=3, cursor=first["next"])
    assert ids(second) == ["d", "e"]
    assert second["next"] is None


def test_page_ending_on_a_day_boundary_continues_from_the_previous_day():
    table = FakeLogTable([row("2026-11-26", "10:00:00", "a"), row("2026-11-25", "10:00:00", "b")])
    first = read_logs(table, today=TODAY, days=90, limit=1, cursor=None)
    assert ids(first) == ["a"]
    second = read_logs(table, today=TODAY, days=90, limit=1, cursor=first["next"])
    assert ids(second) == ["b"]


def test_stops_at_the_retention_window():
    table = FakeLogTable([row("2026-11-20", "10:00:00", "old")])
    page = read_logs(table, today=TODAY, days=3, limit=10, cursor=None)
    assert page == {"items": [], "next": None}
    assert len(table.queries) == 3  # the 26th, 25th and 24th, never the 20th


def test_items_are_json_ready_and_drop_storage_keys():
    table = FakeLogTable([row("2026-11-26", "10:00:00", "a", cached=True)])
    (item,) = read_logs(table, today=TODAY, days=90, limit=5, cursor=None)["items"]
    assert item["time"] == "2026-11-26T10:00:00.000Z"
    assert item["request_id"] == "a"
    assert item["cost"] == 0.0002 and isinstance(item["cost"], float)
    assert item["latency_ms"] == 1200 and isinstance(item["latency_ms"], int)
    assert item["cached"] is True
    assert {"pk", "sk", "expires_at"}.isdisjoint(item)


@pytest.mark.parametrize("cursor", ["not base64!", "e30", "eyJkYXkiOiAieCJ9"])
def test_bad_cursor_is_refused(cursor):
    with pytest.raises(BadCursor):
        read_logs(FakeLogTable([]), today=TODAY, days=90, limit=5, cursor=cursor)
