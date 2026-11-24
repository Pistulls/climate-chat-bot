"""The 20 myths in eval/retrieval_myths.toml, through the service's own embed-and-search
code against the dev `sources` index. Run with: uv run pytest -m live

At least MIN_HITS myths must find an expected source in the top 5 (plan 06: Titan V2 finds
18 of 20; plan 02's target is 0.8). Titan's known misses are "There has been no global
warming since 1998" (rank 10; its top source, #03, isn't on that myth's list) and "Petrol
and diesel prices are soaring because of climate policies" (rank 16).
"""

import pytest

from climate_chat.ingest.evaluate import load_myths

pytestmark = pytest.mark.live

MIN_HITS = 18


@pytest.fixture(scope="module")
def pipeline():
    from climate_chat.service.app import build_app

    app = build_app()
    return app.pipeline()


def test_myths_find_an_expected_source(pipeline):
    myths = load_myths()
    misses = []
    for myth in myths:
        matches = pipeline.search(pipeline.embedder.embed_query(myth.claim))
        found = [m.metadata.get("source_id") for m in matches]
        if not set(found) & set(myth.expected):
            misses.append(f"{myth.claim[:60]!r}: expected {myth.expected}, top 5 {found}")
    hits = len(myths) - len(misses)
    assert hits >= MIN_HITS, f"{hits}/{len(myths)} found a source. Misses:\n" + "\n".join(misses)
