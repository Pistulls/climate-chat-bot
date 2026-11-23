"""Pages -> overlapping chunks of about 500 tokens, each with its page range.

Chunks are built from whole lines, so a table row (one line from pdfplumber) is never
split. Each chunk breaks at the last paragraph or heading boundary that leaves it at least
60% full, and never straight after a table or figure caption.
"""

from __future__ import annotations

import itertools
import json
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path

from climate_chat.ingest.extract import Page

CHUNK_TOKENS = 500
OVERLAP_TOKENS = 80
MIN_CHUNK_TOKENS = 40
MIN_FILL = 0.6  # a chunk may end early at a paragraph break once it's this full
# Chunks with fewer real words than this share are skipped: number grids without labels
# (most of #23's statistics tables) and scrambled chart labels can't answer a claim.
MIN_WORD_SHARE = 0.2
ENCODING = "cl100k_base"  # close enough for both candidate embedding models

TokenCounter = Callable[[str], int]

_SENTENCE_END = re.compile(r"[.!?:;)\]\"”]$")
_CAPTION = re.compile(r"^(Table|Figure|Fig\.|Box|Chart)\s+[A-Z]?\d", re.IGNORECASE)
_HEADING = re.compile(r"^([A-Z0-9]|\d+(\.\d+)*\s)")
_WORD = re.compile(r"[A-Za-z]{3}")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source_id: str
    chunk_no: int
    page_start: int
    page_end: int
    tokens: int
    text: str


@dataclass
class Chunked:
    chunks: list[Chunk]
    skipped: int  # mostly-number chunks left out


def word_share(text: str) -> float:
    """Share of tokens that are words (three or more letters)."""
    tokens = text.split()
    return sum(1 for t in tokens if _WORD.search(t)) / len(tokens) if tokens else 0.0


@cache
def _encoding():
    import tiktoken

    return tiktoken.get_encoding(ENCODING)


def count_tokens(text: str) -> int:
    return len(_encoding().encode_ordinary(text))


def chunk_id(source_id: str, chunk_no: int) -> str:
    return f"{source_id}-{chunk_no:04d}"


def _is_heading(line: str) -> bool:
    words = line.split()
    return 0 < len(words) <= 8 and not _SENTENCE_END.search(line) and bool(_HEADING.match(line))


def _boundaries(lines: Sequence[tuple[int, str]]) -> list[bool]:
    """good[i]: a chunk may start at line i (a new paragraph, heading or page)."""
    good = [True]
    for (prev_page, prev), (page, line) in itertools.pairwise(lines):
        if _CAPTION.match(prev):
            good.append(False)  # keep a caption with its table or figure
        else:
            good.append(page != prev_page or bool(_SENTENCE_END.search(prev)) or _is_heading(line))
    return good


def _split_long(line: str, limit: int, count: TokenCounter) -> list[str]:
    """A line longer than a chunk, cut at word boundaries."""
    parts: list[str] = []
    current: list[str] = []
    for word in line.split():
        if current and count(" ".join([*current, word])) > limit:
            parts.append(" ".join(current))
            current = []
        current.append(word)
    if current:
        parts.append(" ".join(current))
    return parts


def chunk_pages(
    source_id: str,
    pages: Iterable[Page],
    count: TokenCounter = count_tokens,
    size: int = CHUNK_TOKENS,
    overlap: int = OVERLAP_TOKENS,
    min_tokens: int = MIN_CHUNK_TOKENS,
    min_word_share: float = MIN_WORD_SHARE,
) -> Chunked:
    lines: list[tuple[int, str]] = []
    for page in pages:
        for line in page.text.splitlines():
            if not line.strip():
                continue
            if count(line) > size:
                lines.extend((page.page, part) for part in _split_long(line, size, count))
            else:
                lines.append((page.page, line))
    if not lines:
        return Chunked([], 0)

    tokens = [count(line) + 1 for _, line in lines]  # +1 for the newline that joins lines
    good = _boundaries(lines)
    spans: list[tuple[int, int]] = []  # [start, end) line ranges

    start, filled, i = 0, 0, 0
    while i < len(lines):
        if i > start and filled + tokens[i] > size:
            # End at the last good boundary that leaves the chunk MIN_FILL full, else here.
            end, acc = i, 0
            for j in range(start + 1, i + 1):
                acc += tokens[j - 1]
                if good[j] and acc >= MIN_FILL * size:
                    end = j
            spans.append((start, end))
            # The next chunk starts far enough back to repeat about `overlap` tokens,
            # always after this chunk's start so the loop moves on.
            new_start, acc = end, 0
            while new_start - 1 > start and acc < overlap:
                new_start -= 1
                acc += tokens[new_start]
            start = new_start
            filled = sum(tokens[start:i])
            continue
        filled += tokens[i]
        i += 1
    spans.append((start, len(lines)))

    # A short tail is folded into the chunk before it.
    if len(spans) > 1 and sum(tokens[spans[-1][0] : spans[-1][1]]) < min_tokens:
        tail = spans.pop()
        spans[-1] = (spans[-1][0], tail[1])

    texts = [("\n".join(line for _, line in lines[a:b]), a, b) for a, b in spans]
    kept = [(text, a, b) for text, a, b in texts if word_share(text) >= min_word_share]
    chunks = []
    for n, (text, a, b) in enumerate(kept, start=1):
        chunks.append(
            Chunk(
                chunk_id=chunk_id(source_id, n),
                source_id=source_id,
                chunk_no=n,
                page_start=lines[a][0],
                page_end=lines[b - 1][0],
                tokens=count(text),
                text=text,
            )
        )
    return Chunked(chunks, len(texts) - len(kept))


def write_chunks(path: Path, chunks: Iterable[Chunk]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for chunk in chunks:
            fh.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")


def read_chunks(path: Path) -> list[Chunk]:
    with path.open() as fh:
        return [Chunk(**json.loads(line)) for line in fh]
