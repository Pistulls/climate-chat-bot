"""PDF -> cleaned text, one record per page.

`read_pdf` is the only part that touches pdfplumber; `clean` is pure and works on page text,
so the cleaning rules are unit-tested without PDFs.
"""

from __future__ import annotations

import itertools
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Word gaps are judged relative to font size. pdfplumber's default (3 pt) glues words
# together in most journal PDFs, e.g. "Manydifferentsetsof" in #12.
X_TOLERANCE_RATIO = 0.15
# 5 pt rather than 3 keeps subscripts on their line: "CO2", not "CO" with a stray "2".
Y_TOLERANCE = 5

# Column detection. pdfplumber reads straight across a page, interleaving two-column
# journals line by line. A gutter is an x position that few text rows cross, with prose
# on at least one side. Tables have short cells on both sides, so they're never split.
GUTTER_MAX_CROSSING = 0.25  # share of rows allowed to span the gutter (titles, wide figures)
GUTTER_SEARCH = 0.2  # search between 20% and 80% of the region's width
PROSE_WORDS_PER_LINE = 4.5
MIN_ROWS_FOR_COLUMNS = 6
MAX_COLUMN_DEPTH = 3
SIDEBAR_RATIO = 0.5  # a left column under half the right one's width is a sidebar

EDGE_LINES = 3  # running headers/footers sit in a page's first or last few lines
EDGE_SHARE = 0.3  # ...and repeat on more than this share of pages
ANYWHERE_SHARE = 0.5  # boilerplate (cookie banners, running titles) repeats anywhere
MIN_PAGES_FOR_REPEATS = 4
AXIS_RUN = 3  # this many single-number lines in a row are chart axis ticks
MIN_WORDS = 30
FIGURE_VECTORS = 20  # drawn shapes that make a low-text page a figure, not a scan

BACK_MATTER = re.compile(
    r"^(\d+(\.\d+)*\.?\s+)?"
    r"(references|bibliography|literature cited|works cited|acknowledge?ments?"
    r"|author contributions|competing interests|financial support|endnotes)\s*:?$",
    re.IGNORECASE,
)
CITATION_SHARE = 0.25  # a page is still references if this share of lines look like citations
_YEAR = re.compile(r"\b(19|20)\d{2}[a-z]?\b")
_CITATION_MARK = re.compile(r"et al\.|\bpp?\. ?\d|\d+\(\d+\)")
# "Collins, M., Sutherland, M.," (or Vancouver style, "Poland GA, Spier R.") or a DOI/URL:
# reference lists whose year is lines later.
_AUTHOR_OR_LINK = re.compile(
    r"\b[A-Z][\w'\u2019-]+, (?:[A-Z]\.[ -]?){1,3}|\b[A-Z][a-z]+ [A-Z]{1,3}[,.]|doi|https?://"
)
_LIST_NUMBER = re.compile(r"^\[?\d+[.\]]$")  # "3." or "[3]" left alone by column reading
_CID = re.compile(r"\(cid:\d+\)")
_DOT_LEADER = re.compile(r"(?:\s?\.){4,}")
_STANDALONE_NUMBER = re.compile(r"(?<!\S)[-\u2013\u2212+]?\d[\d.,]*%?(?!\S)")
_SINGLE_NUMBER = re.compile(r"^([-\u2013\u2212+]?\d+(?:[.,]\d+)?)%?$")
_HYPHEN_BREAK = re.compile(r"(?<=[a-z])-\n(?=[a-z])")


@dataclass(frozen=True)
class RawPage:
    page: int
    text: str
    images: int = 0
    vectors: int = 0  # curves + rects: charts are drawn, scans are a single image


@dataclass(frozen=True)
class Page:
    page: int
    text: str


@dataclass
class Cleaned:
    pages: list[Page]
    warnings: list[str] = field(default_factory=list)
    dropped: Counter[str] = field(default_factory=Counter)


def read_pdf(path: Path) -> list[RawPage]:
    import pdfplumber

    pages = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            # Upright characters only: rotated chart labels come out reversed ("2202").
            upright = page.filter(lambda obj: obj.get("upright", True))
            text = _region_text(upright, (0, 0, page.width, page.height), 0)
            vectors = len(page.curves) + len(page.rects)
            pages.append(RawPage(number, text, len(page.images), vectors))
            page.close()  # frees pdfplumber's per-page cache; #22 has 216 pages
    return pages


def _rows(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group words into text rows by their top edge."""
    rows: list[dict[str, Any]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows and abs(word["top"] - rows[-1]["top"]) <= Y_TOLERANCE:
            rows[-1]["words"].append(word)
            rows[-1]["bottom"] = max(rows[-1]["bottom"], word["bottom"])
        else:
            rows.append({"top": word["top"], "bottom": word["bottom"], "words": [word]})
    return rows


def _crosses(row: dict[str, Any], x: float) -> bool:
    return any(w["x0"] - 1 < x < w["x1"] + 1 for w in row["words"])


def find_gutter(x0: float, x1: float, rows: list[dict[str, Any]]) -> float | None:
    """The x of a column gutter in [x0, x1], or None for single-column text."""
    if len(rows) < MIN_ROWS_FOR_COLUMNS:
        return None
    margin = GUTTER_SEARCH * (x1 - x0)
    middle = (x0 + x1) / 2
    candidates = range(int(x0 + margin), int(x1 - margin))
    # Fewest crossing rows; on a tie, the candidate nearest the middle.
    best = min(
        candidates,
        key=lambda x: (sum(_crosses(r, x) for r in rows), abs(x - middle)),
        default=None,
    )
    if best is None or sum(_crosses(r, best) for r in rows) / len(rows) > GUTTER_MAX_CROSSING:
        return None
    sides = []
    for on_side in (lambda w: w["x1"] <= best, lambda w: w["x0"] >= best):
        segments = [n for r in rows if (n := sum(1 for w in r["words"] if on_side(w)))]
        if len(segments) < 3:
            return None
        sides.append(sum(segments) / len(segments))
    return best if max(sides) >= PROSE_WORDS_PER_LINE else None


def _region_text(page: Any, box: tuple[float, float, float, float], depth: int) -> str:
    """Text of a page region, reading columns one after another.

    Rows that span the gutter (titles, full-width figures) split the region into bands;
    each band of column text is read left column first, and each column is checked for
    further columns (three-column layouts).
    """
    x0, top, x1, bottom = box
    region = page.crop(box)
    rows = _rows(region.extract_words(x_tolerance_ratio=X_TOLERANCE_RATIO))
    gutter = find_gutter(x0, x1, rows) if depth < MAX_COLUMN_DEPTH else None
    if gutter is None:
        return region.extract_text(x_tolerance_ratio=X_TOLERANCE_RATIO, y_tolerance=Y_TOLERANCE)

    bands: list[list[Any]] = []  # [spans_gutter, top, bottom]
    for row in rows:
        full = _crosses(row, gutter)
        if bands and bands[-1][0] == full:
            bands[-1][2] = max(bands[-1][2], row["bottom"])
        else:
            bands.append([full, row["top"], row["bottom"]])
    parts = []
    for i, (full, band_top, band_bottom) in enumerate(bands):
        b_top = top if i == 0 else max(top, band_top - 1)
        b_bottom = bottom if i == len(bands) - 1 else min(bottom, band_bottom + 1)
        if full:
            parts.append(_region_text(page, (x0, b_top, x1, b_bottom), MAX_COLUMN_DEPTH))
        else:
            left = _region_text(page, (x0, b_top, gutter, b_bottom), depth + 1)
            right = _region_text(page, (gutter, b_top, x1, b_bottom), depth + 1)
            # A narrow left column is a sidebar (GRL's key points and acknowledgements in
            # #12): read it after the main column, so it can't cut into the main text.
            sidebar = gutter - x0 < SIDEBAR_RATIO * (x1 - gutter)
            parts.extend([right, left] if sidebar else [left, right])
    return "\n".join(p for p in parts if p)


def normalise(line: str) -> str:
    """NFKC (ligatures, superscripts, non-breaking spaces); no (cid:n) or dot leaders."""
    line = _CID.sub("", line)
    line = unicodedata.normalize("NFKC", line).replace("\u00ad", "")  # soft hyphen
    line = _DOT_LEADER.sub(" ", line)  # contents pages: "Introduction . . . . . 9"
    return " ".join(line.split())


def _repeat_key(line: str) -> str:
    return re.sub(r"\d+", "#", line.lower().replace(" ", ""))


def _number_groups(line: str) -> int:
    return len(re.findall(r"\d+", line))


def _boilerplate(pages: Sequence[list[str]]) -> tuple[set[str], set[str]]:
    """Keys of lines repeated across pages: (at the page edges, anywhere on the page)."""
    if len(pages) < MIN_PAGES_FOR_REPEATS:
        return set(), set()
    edge: Counter[str] = Counter()
    anywhere: Counter[str] = Counter()
    for lines in pages:
        # Table header rows such as "CAP (MW) 2016 2017 2018 ..." in #23 repeat on every
        # page, but are content: lines with several standalone numbers never count.
        lines = [x for x in lines if len(_STANDALONE_NUMBER.findall(x)) < 4]
        edge.update({_repeat_key(x) for x in lines[:EDGE_LINES] + lines[-EDGE_LINES:]})
        anywhere.update({_repeat_key(x) for x in lines})
    n = len(pages)
    edge_keys = {k for k, c in edge.items() if c / n > EDGE_SHARE}
    # Anywhere on the page needs words and few numbers: cookie banners, running titles.
    anywhere_keys = {
        k
        for k, c in anywhere.items()
        if c / n > ANYWHERE_SHARE and re.search(r"[a-z]{3}", k) and k.count("#") <= 2
    }
    return edge_keys, anywhere_keys


def _is_axis(run: Sequence[str]) -> bool:
    """Evenly spaced numbers, one per line: chart ticks such as 0, 20, 40, 60."""
    if len(run) < AXIS_RUN:
        return False
    values = []
    for line in run:
        match = _SINGLE_NUMBER.match(line)
        assert match
        values.append(
            float(match.group(1).replace("\u2212", "-").replace("\u2013", "-").replace(",", "."))
        )
    steps = {round(b - a, 6) for a, b in itertools.pairwise(values)}
    return len(steps) == 1 and steps != {0}


def _drop_axis_runs(lines: list[str]) -> tuple[list[str], int]:
    """Drop chart axis ticks. Other single-number lines (table cells) are kept."""
    keep: list[str] = []
    run: list[str] = []
    dropped = 0
    for line in [*lines, ""]:  # the sentinel flushes the last run
        if _SINGLE_NUMBER.match(line):
            run.append(line)
            continue
        if _is_axis(run):
            dropped += len(run)
        else:
            keep.extend(run)
        run = []
        if line:
            keep.append(line)
    return keep, dropped


def is_citation_page(lines: Sequence[str]) -> bool:
    lines = [x for x in lines if not _LIST_NUMBER.match(x)]
    if not lines:
        return False
    hits = sum(
        1
        for x in lines
        if _AUTHOR_OR_LINK.search(x) or (_YEAR.search(x) and _CITATION_MARK.search(x))
    )
    return hits / len(lines) >= CITATION_SHARE


def clean(raw: Sequence[RawPage]) -> Cleaned:
    result = Cleaned(pages=[])
    pages = [[normalise(x) for x in p.text.splitlines()] for p in raw]
    pages = [[x for x in lines if x] for lines in pages]
    edge_keys, anywhere_keys = _boilerplate(pages)

    in_back_matter = False
    for page, lines in zip(raw, pages, strict=True):
        kept = []
        for i, line in enumerate(lines):
            key = _repeat_key(line)
            at_edge = i < EDGE_LINES or i >= len(lines) - EDGE_LINES
            # Column reading can move a column's running footer mid-page, so a worded
            # edge repeat goes wherever it is. Bare page numbers only go at the edges.
            worded_edge = key in edge_keys and re.search(r"[a-z]{3}", key)
            if (at_edge and key in edge_keys) or worded_edge or key in anywhere_keys:
                result.dropped["header/footer"] += 1
                continue
            kept.append(line)
        kept, axis = _drop_axis_runs(kept)
        result.dropped["axis ticks"] += axis

        # Back matter runs from its heading to the end of the page, then on through
        # following pages for as long as they read like reference lists.
        if in_back_matter and not is_citation_page(kept):
            in_back_matter = False
        if in_back_matter:
            result.dropped["back matter"] += len(kept)
            kept = []
        for i, line in enumerate(kept):
            if BACK_MATTER.match(line):
                result.dropped["back matter"] += len(kept) - i
                kept = kept[:i]
                in_back_matter = True
                break

        text = _HYPHEN_BREAK.sub("", "\n".join(kept))
        # A scanned page is an image with little or no text layer. Blank pages and
        # drawn charts don't warn.
        words = len(page.text.split())
        if words < MIN_WORDS and page.images and page.vectors < FIGURE_VECTORS:
            result.warnings.append(f"page {page.page}: {words} words over an image; scanned?")
        result.pages.append(Page(page.page, text))
    return result


def write_pages(path: Path, pages: Iterable[Page]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for page in pages:
            fh.write(json.dumps(asdict(page), ensure_ascii=False) + "\n")


def read_pages(path: Path) -> list[Page]:
    with path.open() as fh:
        return [Page(**json.loads(line)) for line in fh]
