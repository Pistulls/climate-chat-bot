import datetime as dt
import re

import pytest

from climate_chat.config import repo_root
from climate_chat.ingest.manifest import (
    ManifestError,
    load_manifest,
    missing_files,
    parse_manifest,
    to_ingest,
)

INDEX = repo_root() / "sources" / "index.md"
# Table rows: | 7 | Data | [title](url) | [`07-....pdf`](docs/07-....pdf) | ...
ROW = re.compile(r"^\|\s*(\d+)\s*\|.*?\[`([^`]+\.pdf)`\]", re.MULTILINE)


def index_entries():
    return {f"{int(n):02d}": file for n, file in ROW.findall(INDEX.read_text())}


def entry(**overrides):
    base = {
        "id": "05",
        "file": "05-report.pdf",
        "title": "A report",
        "url": "https://example.org/report",
        "type": "annual_report",
        "published": 2026,
        "snapshot": False,
        "licence": "open",
        "ingest": True,
    }
    return {**base, **overrides}


def parse(*entries):
    return parse_manifest({"source": list(entries)})


class TestRepoManifest:
    """The real sources/manifest.toml."""

    def test_loads(self):
        assert len(load_manifest()) == 29

    def test_matches_index_ids_and_files(self):
        index = index_entries()
        assert len(index) == 29
        assert {s.id: s.file for s in load_manifest()} == index

    def test_known_problems_are_marked(self):
        by_id = {s.id: s for s in load_manifest()}
        assert by_id["10"].ingest is False
        assert [i for i, s in by_id.items() if s.licence == "non-commercial"] == [
            "08",
            "21",
            "22",
            "23",
        ]

    def test_snapshots_have_capture_dates(self):
        snapshots = [s for s in load_manifest() if s.snapshot]
        assert {s.id for s in snapshots} == {"07", "08", "09", "10", "25", "26", "27", "28", "29"}
        assert all(s.captured == dt.date(2026, 11, 22) for s in snapshots)


class TestValidation:
    def test_valid_entry(self):
        (source,) = parse(entry())
        assert source.id == "05"
        assert source.captured is None

    def test_snapshot_with_captured_date(self):
        (source,) = parse(entry(snapshot=True, captured=dt.date(2026, 11, 22)))
        assert source.captured == dt.date(2026, 11, 22)

    @pytest.mark.parametrize(
        ("overrides", "message"),
        [
            ({"id": "5"}, "two digits"),
            ({"file": "06-report.pdf"}, "file must be '05-<name>.pdf'"),
            ({"file": "05-report.txt"}, "file must be '05-<name>.pdf'"),
            ({"file": "05-sub/report.pdf"}, "bare name"),
            ({"url": "http://example.org"}, "https"),
            ({"type": "blog"}, "type must be one of"),
            ({"licence": "cc-by-nc"}, "licence must be one of"),
            ({"published": "2026"}, "'published' must be int"),
            ({"published": True}, "'published' must be int"),
            ({"ingest": "yes"}, "'ingest' must be bool"),
            ({"snapshot": True}, "snapshots need 'captured'"),
            ({"captured": dt.date(2026, 11, 22)}, "snapshots need 'captured'"),
            ({"snapshot": True, "captured": "2026-11-22"}, "'captured' must be date"),
            ({"colour": "red"}, "unknown keys"),
        ],
    )
    def test_rejects(self, overrides, message):
        with pytest.raises(ManifestError, match=re.escape(message)):
            parse(entry(**overrides))

    def test_missing_key(self):
        bad = entry()
        del bad["licence"]
        with pytest.raises(ManifestError, match="missing 'licence'"):
            parse(bad)

    def test_duplicate_id(self):
        with pytest.raises(ManifestError, match="repeats entry 1"):
            parse(entry(), entry(file="05-other.pdf"))

    def test_empty_manifest(self):
        with pytest.raises(ManifestError, match="at least one"):
            parse_manifest({})

    def test_unknown_top_level_key(self):
        with pytest.raises(ManifestError, match="Unknown top-level"):
            parse_manifest({"source": [entry()], "sources": []})

    def test_bad_toml(self, tmp_path):
        path = tmp_path / "manifest.toml"
        path.write_text("[[source]\n")
        with pytest.raises(ManifestError, match=str(path)):
            load_manifest(path)

    def test_missing_file(self, tmp_path):
        with pytest.raises(ManifestError, match="No manifest"):
            load_manifest(tmp_path / "nope.toml")


class TestSelection:
    sources = parse(
        entry(),
        entry(id="06", file="06-a.pdf"),
        entry(id="10", file="10-b.pdf", ingest=False),
    )

    def test_all_skips_ingest_false(self):
        assert [s.id for s in to_ingest(self.sources)] == ["05", "06"]

    def test_by_id_keeps_requested_order(self):
        assert [s.id for s in to_ingest(self.sources, ["06", "05"])] == ["06", "05"]

    def test_unknown_id(self):
        with pytest.raises(ManifestError, match="No source with id '99'"):
            to_ingest(self.sources, ["99"])

    def test_excluded_id(self):
        with pytest.raises(ManifestError, match="ingest = false"):
            to_ingest(self.sources, ["10"])

    def test_missing_files(self, tmp_path):
        (tmp_path / "05-report.pdf").write_bytes(b"%PDF")
        assert [s.id for s in missing_files(self.sources, tmp_path)] == ["06", "10"]
