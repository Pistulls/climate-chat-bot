import itertools

import pytest

from climate_chat.ingest.chunk import (
    chunk_id,
    chunk_pages,
    read_chunks,
    word_share,
    write_chunks,
)
from climate_chat.ingest.extract import Page


def words(text):
    """Stand-in token counter: one token per word."""
    return len(text.split())


def sentence(n, tag):
    """A line of n words ending a sentence, unique per tag."""
    return " ".join([f"{tag}word{i}" for i in range(n - 1)] + [f"{tag}end."])


def run(pages, **kw):
    kw = {"size": 100, "overlap": 20, "min_tokens": 10, **kw}
    return chunk_pages("05", pages, count=words, **kw).chunks


def lines_of(chunk):
    return chunk.text.splitlines()


class TestSizesAndOverlap:
    def test_short_text_is_one_chunk(self):
        (chunk,) = run([Page(1, sentence(30, "a"))])
        assert chunk.chunk_id == "05-0001"
        assert chunk.tokens == 30

    def test_chunks_stay_under_the_size(self):
        page = Page(1, "\n".join(sentence(10, f"s{i}") for i in range(50)))
        chunks = run([page])
        assert len(chunks) > 1
        assert all(c.tokens <= 100 for c in chunks)

    def test_neighbours_overlap_by_about_the_overlap(self):
        page = Page(1, "\n".join(sentence(10, f"s{i}") for i in range(50)))
        chunks = run([page])
        for a, b in itertools.pairwise(chunks):
            shared = [x for x in lines_of(b) if x in lines_of(a)]
            assert shared == lines_of(b)[: len(shared)]
            assert 20 <= words("\n".join(shared)) <= 30

    def test_every_line_is_in_some_chunk(self):
        source = [sentence(7, f"s{i}") for i in range(80)]
        chunks = run([Page(1, "\n".join(source))])
        assert {x for c in chunks for x in lines_of(c)} == set(source)

    def test_ids_are_numbered_from_one(self):
        page = Page(1, "\n".join(sentence(10, f"s{i}") for i in range(30)))
        assert [c.chunk_id for c in run([page])][:3] == ["05-0001", "05-0002", "05-0003"]
        assert chunk_id("21", 42) == "21-0042"


class TestBoundaries:
    def test_breaks_at_a_paragraph_end_rather_than_mid_sentence(self):
        # Sentences of 3 lines; only the last line of each ends with a full stop.
        lines = []
        for s in range(20):
            lines += [f"p{s}a " * 6, f"p{s}b " * 6, sentence(6, f"p{s}c")]
        chunks = run([Page(1, "\n".join(x.strip() for x in lines))])
        assert all(lines_of(c)[-1].endswith(".") for c in chunks[:-1])

    def test_table_rows_are_never_split(self):
        rows = [f"Country{i} Wind 12 34 56 78 90" for i in range(40)]
        chunks = run([Page(1, "\n".join(rows))])
        assert all(x in rows for c in chunks for x in lines_of(c))

    def test_caption_stays_with_its_table(self):
        before = [sentence(10, f"s{i}") for i in range(6)]
        lines = [
            *before,
            "Table 3 Installed capacity by region",
            *(f"Row{i} 1 2 3" for i in range(20)),
        ]
        chunks = run([Page(1, "\n".join(lines))])
        caption_chunk = next(c for c in chunks if "Table 3 Installed capacity by region" in c.text)
        assert lines_of(caption_chunk)[-1] != "Table 3 Installed capacity by region"

    def test_a_line_longer_than_a_chunk_is_cut_at_words(self):
        chunks = run([Page(1, " ".join(f"word{i}" for i in range(250)))])
        assert all(c.tokens <= 100 for c in chunks)
        assert chunks[0].text.split()[0] == "word0"


class TestPages:
    def test_page_ranges(self):
        pages = [
            Page(p, "\n".join(sentence(10, f"p{p}s{i}") for i in range(4))) for p in (3, 4, 5, 6)
        ]
        chunks = run(pages)
        assert chunks[0].page_start == 3
        assert chunks[-1].page_end == 6
        assert any(c.page_start < c.page_end for c in chunks)

    def test_empty_pages_are_skipped(self):
        chunks = run([Page(1, ""), Page(2, sentence(20, "x")), Page(3, "")])
        assert [(c.page_start, c.page_end) for c in chunks] == [(2, 2)]

    def test_no_text_no_chunks(self):
        assert run([Page(1, ""), Page(2, "  ")]) == []


class TestSmallTail:
    def test_a_short_last_chunk_is_merged(self):
        lines = [sentence(10, f"s{i}") for i in range(9)] + ["tail."]
        chunks = run([Page(1, "\n".join(lines))])
        assert chunks[-1].tokens >= 10
        assert lines_of(chunks[-1])[-1] == "tail."

    @pytest.mark.parametrize("n", [1, 5])
    def test_a_short_document_is_still_kept(self, n):
        assert len(run([Page(1, sentence(n, "x"))])) == 1


class TestNumbers:
    def test_number_grids_are_skipped_and_ids_stay_contiguous(self):
        prose = [sentence(10, f"s{i}") for i in range(9)]
        grid = [" ".join(str(n) for n in range(r, r + 10)) for r in range(12)]
        more = [sentence(10, f"t{i}") for i in range(9)]
        result = chunk_pages(
            "23", [Page(1, "\n".join(prose + grid + more))], count=words, size=100, overlap=0
        )
        assert result.skipped >= 1
        assert [c.chunk_no for c in result.chunks] == list(range(1, len(result.chunks) + 1))
        assert all(word_share(c.text) >= 0.2 for c in result.chunks)

    def test_word_share(self):
        assert word_share("Installed capacity 412 GW") == 0.5
        assert word_share("") == 0.0


def test_round_trip(tmp_path):
    chunks = run([Page(1, "\n".join(sentence(10, f"s{i}") for i in range(30)))])
    path = tmp_path / "chunks" / "05.jsonl"
    write_chunks(path, chunks)
    assert read_chunks(path) == chunks
