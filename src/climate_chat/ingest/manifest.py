"""The source manifest: sources/manifest.toml, one [[source]] table per PDF.

Loading validates every entry, so a typo fails before anything is extracted or embedded.
"""

from __future__ import annotations

import datetime as dt
import re
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from climate_chat.config import repo_root

TYPES = frozenset(
    {"assessment", "annual_report", "data", "paper", "consensus", "method", "taxonomy", "energy"}
)
LICENCES = frozenset({"open", "cc-by", "non-commercial", "gov", "restricted", "unverified"})

_REQUIRED = {
    "id": str,
    "file": str,
    "title": str,
    "url": str,
    "type": str,
    "published": int,
    "snapshot": bool,
    "licence": str,
    "ingest": bool,
}
_OPTIONAL = {"captured": dt.date}
_ID = re.compile(r"\d{2}")


class ManifestError(Exception):
    """The manifest is missing, malformed or inconsistent."""


@dataclass(frozen=True)
class Source:
    id: str
    file: str
    title: str
    url: str
    type: str
    published: int
    snapshot: bool
    licence: str
    ingest: bool
    captured: dt.date | None = None

    def path(self, docs_dir: Path) -> Path:
        return docs_dir / self.file


def default_path() -> Path:
    return repo_root() / "sources" / "manifest.toml"


def docs_dir() -> Path:
    return repo_root() / "sources" / "docs"


def load_manifest(path: Path | None = None) -> list[Source]:
    path = path or default_path()
    try:
        data = tomllib.loads(path.read_text())
    except FileNotFoundError as e:
        raise ManifestError(f"No manifest at {path}") from e
    except tomllib.TOMLDecodeError as e:
        raise ManifestError(f"{path}: {e}") from e
    return parse_manifest(data)


def parse_manifest(data: Mapping[str, Any]) -> list[Source]:
    unknown_top = set(data) - {"source"}
    if unknown_top:
        raise ManifestError(f"Unknown top-level keys: {sorted(unknown_top)}")
    entries = data.get("source")
    if not isinstance(entries, list) or not entries:
        raise ManifestError("The manifest needs at least one [[source]] table")

    sources = [_parse_entry(i, entry) for i, entry in enumerate(entries, start=1)]

    seen: dict[str, int] = {}
    for n, source in enumerate(sources, start=1):
        if source.id in seen:
            raise ManifestError(f"Entry {n}: id {source.id!r} repeats entry {seen[source.id]}")
        seen[source.id] = n
    files = [s.file for s in sources]
    if len(set(files)) != len(files):
        raise ManifestError("Two sources share a file name")
    return sources


def _parse_entry(n: int, entry: Any) -> Source:
    if not isinstance(entry, dict):
        raise ManifestError(f"Entry {n} is not a table")
    where = f"Entry {n} (id {entry.get('id')!r})"

    unknown = set(entry) - set(_REQUIRED) - set(_OPTIONAL)
    if unknown:
        raise ManifestError(f"{where}: unknown keys {sorted(unknown)}")
    for key, kind in _REQUIRED.items():
        if key not in entry:
            raise ManifestError(f"{where}: missing {key!r}")
        _check_type(where, key, entry[key], kind)
    for key, kind in _OPTIONAL.items():
        if key in entry:
            _check_type(where, key, entry[key], kind)

    if not _ID.fullmatch(entry["id"]):
        raise ManifestError(f"{where}: id must be two digits")
    if not entry["file"].startswith(f"{entry['id']}-") or not entry["file"].endswith(".pdf"):
        raise ManifestError(f"{where}: file must be '{entry['id']}-<name>.pdf'")
    if "/" in entry["file"]:
        raise ManifestError(f"{where}: file must be a bare name, not a path")
    if not entry["url"].startswith("https://"):
        raise ManifestError(f"{where}: url must be https")
    if entry["type"] not in TYPES:
        raise ManifestError(f"{where}: type must be one of {sorted(TYPES)}")
    if entry["licence"] not in LICENCES:
        raise ManifestError(f"{where}: licence must be one of {sorted(LICENCES)}")
    if entry["snapshot"] != ("captured" in entry):
        raise ManifestError(f"{where}: snapshots need 'captured', other sources must not have it")

    return Source(**entry)


def _check_type(where: str, key: str, value: Any, kind: type) -> None:
    # bool is a subclass of int, and datetime a subclass of date; neither is wanted here.
    ok = isinstance(value, kind)
    if kind is int and isinstance(value, bool):
        ok = False
    if kind is dt.date and isinstance(value, dt.datetime):
        ok = False
    if not ok:
        raise ManifestError(f"{where}: {key!r} must be {kind.__name__}, got {value!r}")


def to_ingest(sources: Iterable[Source], ids: Iterable[str] | None = None) -> list[Source]:
    """The sources to process: `ingest = true`, narrowed to `ids` if given.

    Asking for an id that isn't in the manifest, or that is marked `ingest = false`, is an
    error rather than a silent skip.
    """
    sources = list(sources)
    if ids is None:
        return [s for s in sources if s.ingest]
    by_id = {s.id: s for s in sources}
    chosen = []
    for wanted in ids:
        source = by_id.get(wanted)
        if source is None:
            raise ManifestError(f"No source with id {wanted!r}")
        if not source.ingest:
            raise ManifestError(f"Source {wanted} is marked ingest = false")
        chosen.append(source)
    return chosen


def missing_files(sources: Iterable[Source], docs: Path | None = None) -> list[Source]:
    """Sources whose PDF isn't in sources/docs/ (the folder is gitignored)."""
    docs = docs or docs_dir()
    return [s for s in sources if not s.path(docs).is_file()]
