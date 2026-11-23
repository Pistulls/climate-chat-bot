from climate_chat.ingest.extract import (
    RawPage,
    _rows,
    clean,
    find_gutter,
    is_citation_page,
    normalise,
    read_pages,
    write_pages,
)

NAMES = [
    "alpha",
    "bravo",
    "charlie",
    "delta",
    "echo",
    "foxtrot",
    "golf",
    "hotel",
    "india",
    "juliet",
    "kilo",
    "lima",
]


def body(n, page=0):
    """Prose lines that differ between pages (digits are ignored when matching repeats)."""
    return [
        f"Body {NAMES[i]} on sheet {NAMES[page]} has enough words to read as prose."
        for i in range(n)
    ]


def pages(*texts, **kw):
    return [RawPage(i, t, **kw) for i, t in enumerate(texts, start=1)]


def texts(result):
    return [p.text for p in result.pages]


class TestNormalise:
    def test_ligatures_cid_and_spaces(self):
        assert normalise("ﬁrst  (cid:12)ﬂow\u00a0rate") == "first flow rate"

    def test_dot_leaders(self):
        assert normalise("Introduction . . . . . . . 9") == "Introduction 9"
        assert normalise("See Fig. 2. Then...") == "See Fig. 2. Then..."

    def test_subscripts_and_soft_hyphens(self):
        assert normalise("CO₂ emis­sions") == "CO2 emissions"


class TestHeadersAndFooters:
    def test_repeated_edge_lines_are_dropped(self):
        raw = pages(
            *(f"Journal of Things\n{chr(10).join(body(6, n))}\nPage {n}" for n in range(1, 6))
        )
        result = clean(raw)
        assert all("Journal of Things" not in t and "Page" not in t for t in texts(result))
        assert all("Body alpha on sheet" in t for t in texts(result))
        assert result.dropped["header/footer"] == 10

    def test_a_running_footer_moved_mid_page_by_columns_is_dropped(self):
        raw = pages(
            *(
                "\n".join([*body(3, n), "Earth Syst. Sci. Data, 18, 3211-3288, 2026", *body(3, n)])
                if n % 2
                else "\n".join([*body(6, n), "Earth Syst. Sci. Data, 18, 3211-3288, 2026"])
                for n in range(6)
            )
        )
        assert not any("Earth Syst" in t for t in texts(clean(raw)))

    def test_page_numbers_mid_page_are_kept(self):
        raw = pages(*("\n".join([*body(3, n), "42", *body(2, n), str(n)]) for n in range(6)))
        assert all("\n42\n" in t for t in texts(clean(raw)))

    def test_a_line_repeated_mid_page_on_few_pages_is_kept(self):
        page = "\n".join([*body(4), "Solar output falls at night.", *body(4)])
        raw = pages(page, *("\n".join(body(9, n)) for n in range(4)))
        assert "Solar output falls at night." in texts(clean(raw))[0]

    def test_boilerplate_anywhere_on_most_pages_is_dropped(self):
        raw = pages(*("\n".join([*body(3, n), "Manage Consent", *body(3, n)]) for n in range(5)))
        assert not any("Manage Consent" in t for t in texts(clean(raw)))

    def test_repeated_table_headers_are_kept(self):
        raw = pages(
            *(
                "\n".join(["Country", "CAP (MW) 2016 2017 2018 2019 2020", *body(5, n)])
                for n in range(6)
            )
        )
        result = clean(raw)
        assert all("CAP (MW) 2016" in t for t in texts(result))

    def test_short_documents_keep_repeats(self):
        raw = pages("Title\n" + "\n".join(body(3)), "Title\n" + "\n".join(body(3)))
        assert all(t.startswith("Title") for t in texts(clean(raw)))


class TestAxisTicks:
    def test_evenly_spaced_numbers_are_dropped(self):
        raw = pages("\n".join(["Figure 2 Prices", "100%", "80%", "60%", "40%", *body(2)]))
        text = texts(clean(raw))[0]
        assert "80%" not in text and "Figure 2 Prices" in text

    def test_table_cells_are_kept(self):
        raw = pages("\n".join(["Capacity", "412", "97", "1530", *body(2)]))
        assert "97\n1530" in texts(clean(raw))[0]


class TestBackMatter:
    refs = (
        "Collins, M., Sutherland, M., Bouwer, L.: Extremes, in: IPCC Special Report,",
        "Cambridge University Press, https://doi.org/10.1017/x, 2013.",
        "Smith, J. and Jones, K.: Ocean heat, Geophys. Res. Lett., 51, 2024.",
        "Brown, A. B.: A paper title that runs on, Nature, 12, 1\u20139, 2020.",
    )

    def test_references_are_dropped_to_the_end_of_the_page(self):
        raw = pages("\n".join([*body(3), "References", *self.refs]))
        result = clean(raw)
        assert texts(result)[0] == "\n".join(body(3))
        assert result.dropped["back matter"] == 5

    def test_numbered_and_capitalised_headings(self):
        for heading in ("7 References", "REFERENCES", "Acknowledgements", "Acknowledgments"):
            raw = pages("\n".join([*body(2), heading, *self.refs]))
            assert texts(clean(raw))[0] == "\n".join(body(2)), heading

    def test_reference_pages_continue_until_prose(self):
        raw = pages(
            "\n".join([*body(2), "References", *self.refs]),
            "\n".join(list(self.refs) * 3),
            "\n".join(body(5)),
        )
        assert texts(clean(raw)) == ["\n".join(body(2)), "", "\n".join(body(5))]

    def test_heading_words_inside_sentences_are_not_headings(self):
        raw = pages("\n".join(["See the references in section 2.", *body(2)]))
        assert texts(clean(raw))[0].startswith("See the references")

    def test_numbered_vancouver_references(self):
        numbers = [f"{n}." for n in range(1, 9)]
        refs = [
            "Poland GA, Spier R. Fear, misinformation, and innumerates. Vaccine. 2010; 28(12).",
            "Cook J, Nuccitelli D, Green SA. Quantifying the consensus on global warming.",
            "Environmental Research Letters. 2013; 8(2):024024.",
            "Lewandowsky S, Ecker UKH. Misinformation and its correction. Psychol Sci.",
        ] * 2
        assert is_citation_page(numbers + refs)

    def test_citation_page_detection(self):
        assert is_citation_page(self.refs)
        assert not is_citation_page(body(6))
        assert not is_citation_page([])


class TestHyphenation:
    def test_line_break_hyphens_are_joined(self):
        assert texts(clean(pages("perfluo-\nrocarbons")))[0] == "perfluorocarbons"

    def test_real_hyphens_are_kept(self):
        assert (
            texts(clean(pages("CO2-\nequivalent\nlong-term")))[0] == "CO2-\nequivalent\nlong-term"
        )


class TestWarnings:
    def test_little_text_over_an_image_warns(self):
        result = clean(pages("Scanned page", images=1, vectors=0))
        assert result.warnings == ["page 1: 2 words over an image; scanned?"]

    def test_blank_pages_and_charts_do_not_warn(self):
        assert clean(pages("", images=0)).warnings == []
        assert clean(pages("Figure 3", images=1, vectors=200)).warnings == []


def word(text, x0, top, width=None):
    width = width or 6 * len(text)
    return {"text": text, "x0": x0, "x1": x0 + width, "top": top, "bottom": top + 10}


def column_rows(left, right, gutter_words=0, rows=10):
    words = []
    for i in range(rows):
        top = 100 + 14 * i
        shift = 7 * (i % 4)  # ragged word positions, as in real text
        words += [word(w, 50 + shift + 36 * j, top, 30) for j, w in enumerate(left.split())]
        words += [word(w, 320 + shift + 36 * j, top, 30) for j, w in enumerate(right.split())]
    for i in range(gutter_words):
        words.append(word("Title spanning the page", 50, 20 + 14 * i, 500))
    return _rows(words)


class TestColumns:
    def test_two_prose_columns_have_a_gutter(self):
        rows = column_rows("one two three four five six", "seven eight nine ten eleven twelve")
        gutter = find_gutter(0, 612, rows)
        assert gutter is not None and 285 <= gutter <= 320

    def test_table_cells_are_not_columns(self):
        assert find_gutter(0, 612, column_rows("Haiti Haiti", "Haïti Haití")) is None

    def test_prose_beside_a_chart_splits(self):
        rows = column_rows("one two three four five six", "40%")
        assert find_gutter(0, 612, rows) is not None

    def test_too_many_rows_crossing_means_one_column(self):
        rows = column_rows("one two three four five six", "seven eight nine ten", gutter_words=6)
        assert find_gutter(0, 612, rows) is None

    def test_few_rows_are_never_split(self):
        rows = column_rows("one two three four five six", "seven eight nine ten", rows=4)
        assert find_gutter(0, 612, rows) is None


def test_pages_round_trip(tmp_path):
    result = clean(pages("café ﬁrst", "two"))
    path = tmp_path / "text" / "05.jsonl"
    write_pages(path, result.pages)
    assert read_pages(path) == result.pages
