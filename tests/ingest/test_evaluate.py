import itertools

import numpy as np
import pytest

from climate_chat.ingest.evaluate import (
    EvalError,
    ModelResult,
    Myth,
    MythResult,
    evaluate,
    load_myths,
    myths_path,
    pick_winner,
    report,
)
from climate_chat.ingest.manifest import load_manifest, to_ingest

# Three sources along three axes; source 12 also has a chunk pointing between 05 and 12.
IDS = ["05-0001", "05-0002", "12-0001", "12-0002", "22-0001"]
VECTORS = np.array(
    [[1, 0, 0], [0.9, 0.1, 0], [0, 1, 0], [0.6, 0.8, 0], [0, 0, 1]], dtype=np.float32
)
QUERIES = {"warming": [1, 0, 0], "models": [0, 1, 0], "costs": [0, 0, 1]}


def myth(claim, expected):
    return Myth(claim, "not_happening", tuple(expected))


def run(myths, seconds=0.1, model="m"):
    ticks = itertools.count(step=seconds)
    return evaluate(
        model,
        myths,
        IDS,
        VECTORS,
        lambda q: np.array(QUERIES[q], dtype=np.float32),
        clock=lambda: next(ticks),
    )


class TestEvaluate:
    def test_hits_ranks_and_top_ids(self):
        result = run([myth("warming", ["05"]), myth("models", ["12"]), myth("costs", ["22"])])
        assert [m.first_expected_rank for m in result.myths] == [1, 1, 1]
        assert result.myths[0].top_ids[:2] == ["05-0001", "05-0002"]
        assert result.recall == 1.0 and result.mrr == 1.0

    def test_rank_of_first_expected_chunk(self):
        result = run([myth("warming", ["12"])])
        # 05-0001, 05-0002, then 12-0002 (0.6 along the warming axis)
        assert result.myths[0].first_expected_rank == 3
        assert result.myths[0].hit
        assert result.mrr == pytest.approx(1 / 3)

    def test_miss_beyond_k(self):
        ids = [f"05-{i:04d}" for i in range(1, 7)] + ["12-0001"]
        vectors = np.array([[1, 0, 0]] * 6 + [[0, 1, 0]], dtype=np.float32)
        result = evaluate(
            "m", [myth("warming", ["12"])], ids, vectors, lambda q: np.array([1.0, 0, 0])
        )
        assert result.myths[0].first_expected_rank == 7
        assert not result.myths[0].hit
        assert result.recall == 0.0

    def test_latency_is_measured_per_query(self):
        result = run([myth("warming", ["05"]), myth("costs", ["22"])], seconds=0.5)
        assert result.latency(50) == pytest.approx(0.5)


def model_result(model, hits, seconds=0.2, total=20):
    m = myth("x", ["05"])
    return ModelResult(
        model,
        [MythResult(m, ["05-0001"], 1 if i < hits else None, seconds) for i in range(total)],
    )


class TestWinner:
    def test_higher_recall_wins(self):
        winner, _ = pick_winner(
            [
                model_result("qwen/qwen3-embedding-8b", 18),
                model_result("openai/text-embedding-3-small", 15),
            ]
        )
        assert winner == "qwen/qwen3-embedding-8b"

    def test_tie_within_one_myth_goes_to_the_small_model(self):
        winner, reasons = pick_winner(
            [
                model_result("qwen/qwen3-embedding-8b", 17),
                model_result("openai/text-embedding-3-small", 16),
            ]
        )
        assert winner == "openai/text-embedding-3-small"
        assert "cheaper" in reasons[-1]

    def test_slow_model_is_ruled_out_first(self):
        winner, reasons = pick_winner(
            [
                model_result("qwen/qwen3-embedding-8b", 20, seconds=3.0),
                model_result("openai/text-embedding-3-small", 12),
            ]
        )
        assert winner == "openai/text-embedding-3-small"
        assert "p95" in reasons[0]

    def test_no_winner_when_all_are_slow(self):
        winner, _ = pick_winner([model_result("a", 20, seconds=5)])
        assert winner is None


def test_report_has_summary_and_per_myth_rows():
    results = [
        model_result("qwen/qwen3-embedding-8b", 18),
        model_result("openai/text-embedding-3-small", 15),
    ]
    winner, reasons = pick_winner(results)
    text = report(results, winner, reasons)
    assert "| `qwen/qwen3-embedding-8b` | 18/20 (0.90)" in text
    assert f"**Winner: `{winner}`**" in text
    assert text.count("| x | 05 |") == 20


class TestMythsFile:
    def test_repo_myths_are_valid_and_cover_every_category(self):
        known = {s.id for s in to_ingest(load_manifest())}
        myths = load_myths(known_ids=known)
        assert len(myths) == 20
        assert {m.category for m in myths} == {
            "not_happening",
            "not_us",
            "not_bad",
            "solutions_wont_work",
            "science_unreliable",
        }
        assert myths_path().name == "retrieval_myths.toml"

    @pytest.mark.parametrize(
        ("body", "message"),
        [
            ('[[myth]]\nclaim = "x"\ncategory = "nope"\nexpected = ["05"]', "category"),
            ('[[myth]]\nclaim = "x"\ncategory = "not_us"\nexpected = []', "at least one"),
            ('[[myth]]\nclaim = "x"\ncategory = "not_us"\nexpected = ["10"]', "not ingested"),
            ('[[myth]]\nclaim = "x"\ncategory = "not_us"', "exactly"),
            ("", "No"),
        ],
    )
    def test_rejects(self, tmp_path, body, message):
        path = tmp_path / "m.toml"
        path.write_text(body)
        with pytest.raises(EvalError, match=message):
            load_myths(path, known_ids={"05"})
