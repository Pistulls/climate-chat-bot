"""The 20 myths in eval/retrieval_myths.toml, through the service's own embed-and-search
code against the dev `sources` index. Run with: uv run pytest -m live"""

import pytest

from climate_chat.ingest.evaluate import load_myths

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def pipeline():
    from climate_chat.service.app import build_app

    app = build_app()
    return app.pipeline()


@pytest.mark.parametrize("myth", load_myths(), ids=lambda m: m.claim[:40])
def test_myth_finds_an_expected_source(pipeline, myth):
    matches = pipeline.search(pipeline.embedder.embed_query(myth.claim))
    found = [m.metadata.get("source_id") for m in matches]
    assert set(found) & set(myth.expected), f"top 5 came from {found}"
