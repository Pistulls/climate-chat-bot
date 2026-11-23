"""Retrieval evaluation: do the myths in eval/retrieval_myths.toml find their sources?

`--in-memory` searches a model's cached vectors with exact cosine similarity (numpy), so
candidates are compared without loading anything into S3 Vectors.
"""

from __future__ import annotations

import time
import tomllib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from climate_chat.config import repo_root

K = 5
MAX_P95_SECONDS = 2.0  # slower query embedding would eat the service's 4-6 s reply budget
CATEGORIES = frozenset(
    {"not_happening", "not_us", "not_bad", "solutions_wont_work", "science_unreliable"}
)
# On a recall tie (within one myth), the cheaper and smaller model wins.
PREFERENCE = ("openai/text-embedding-3-small", "qwen/qwen3-embedding-8b")


class EvalError(Exception):
    pass


@dataclass(frozen=True)
class Myth:
    claim: str
    category: str
    expected: tuple[str, ...]


def myths_path() -> Path:
    return repo_root() / "eval" / "retrieval_myths.toml"


def load_myths(path: Path | None = None, known_ids: Iterable[str] | None = None) -> list[Myth]:
    data = tomllib.loads((path or myths_path()).read_text())
    known = set(known_ids) if known_ids is not None else None
    myths = []
    for n, entry in enumerate(data.get("myth", []), start=1):
        if set(entry) != {"claim", "category", "expected"}:
            raise EvalError(f"Myth {n}: needs exactly claim, category and expected")
        if entry["category"] not in CATEGORIES:
            raise EvalError(f"Myth {n}: category must be one of {sorted(CATEGORIES)}")
        if not entry["expected"]:
            raise EvalError(f"Myth {n}: expected needs at least one source id")
        if known is not None and (unknown := set(entry["expected"]) - known):
            raise EvalError(f"Myth {n}: expected sources not ingested: {sorted(unknown)}")
        myths.append(Myth(entry["claim"], entry["category"], tuple(entry["expected"])))
    if not myths:
        raise EvalError("No [[myth]] entries")
    return myths


def normalise_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.where(norms == 0, 1, norms)


@dataclass
class MythResult:
    myth: Myth
    top_ids: list[str]  # top K chunk ids, best first
    first_expected_rank: int | None  # 1-based rank of the first chunk from an expected source
    seconds: float  # time to embed the query

    @property
    def hit(self) -> bool:
        return self.first_expected_rank is not None and self.first_expected_rank <= K

    @property
    def top_source(self) -> str:
        return self.top_ids[0].split("-")[0]


@dataclass
class ModelResult:
    model: str
    myths: list[MythResult] = field(default_factory=list)

    @property
    def recall(self) -> float:
        return sum(m.hit for m in self.myths) / len(self.myths)

    @property
    def hits(self) -> int:
        return sum(m.hit for m in self.myths)

    @property
    def mrr(self) -> float:
        return sum(1 / m.first_expected_rank for m in self.myths if m.first_expected_rank) / len(
            self.myths
        )

    def latency(self, percentile: float) -> float:
        return float(np.percentile([m.seconds for m in self.myths], percentile))


def evaluate(
    model: str,
    myths: Sequence[Myth],
    chunk_ids: Sequence[str],
    vectors: np.ndarray,
    embed_query: Callable[[str], np.ndarray],
    clock: Callable[[], float] = time.perf_counter,
) -> ModelResult:
    matrix = normalise_rows(np.asarray(vectors, dtype=np.float32))
    sources = np.array([cid.split("-")[0] for cid in chunk_ids])
    result = ModelResult(model)
    for myth in myths:
        started = clock()
        query = embed_query(myth.claim)
        seconds = clock() - started
        scores = matrix @ normalise_rows(query[None, :])[0]
        order = np.argsort(-scores, kind="stable")
        expected = np.isin(sources[order], myth.expected)
        rank = int(np.argmax(expected)) + 1 if expected.any() else None
        top = [chunk_ids[i] for i in order[:K]]
        result.myths.append(MythResult(myth, top, rank, seconds))
    return result


def pick_winner(results: Sequence[ModelResult]) -> tuple[str | None, list[str]]:
    """Apply plan 02 step 4.4. Returns (winner, reasons)."""
    reasons = []
    fast = []
    for r in results:
        if r.latency(95) > MAX_P95_SECONDS:
            reasons.append(f"{r.model} is out: p95 query latency {r.latency(95):.2f} s > 2 s")
        else:
            fast.append(r)
    if not fast:
        return None, [*reasons, "No model meets the latency limit"]
    best = max(r.hits for r in fast)
    tied = [r for r in fast if best - r.hits <= 1]
    preference = {m: i for i, m in enumerate(PREFERENCE)}
    winner = min(tied, key=lambda r: preference.get(r.model, len(PREFERENCE)))
    if len(tied) > 1:
        reasons.append(
            f"Recall within one myth ({', '.join(f'{r.model} {r.hits}' for r in tied)}), "
            f"so the cheaper, smaller {winner.model} wins"
        )
    else:
        reasons.append(f"{winner.model} has the best recall@{K}: {winner.hits}/{len(winner.myths)}")
    return winner.model, reasons


def report(results: Sequence[ModelResult], winner: str | None, reasons: Sequence[str]) -> str:
    lines = ["# Embedding bake-off", ""]
    lines += [f"| Model | recall@{K} | MRR | p50 query | p95 query |", "|---|---|---|---|---|"]
    for r in results:
        lines.append(
            f"| `{r.model}` | {r.hits}/{len(r.myths)} ({r.recall:.2f}) | {r.mrr:.2f} "
            f"| {r.latency(50):.2f} s | {r.latency(95):.2f} s |"
        )
    lines += ["", f"**Winner: `{winner}`**" if winner else "**No winner**", ""]
    lines += [f"- {reason}" for reason in reasons]
    lines += ["", "## Per myth", ""]
    header = "| Claim | Expected | " + " | ".join(f"`{r.model.split('/')[-1]}`" for r in results)
    lines += [header + " |", "|---|---|" + "---|" * len(results)]
    for i, myth_result in enumerate(results[0].myths):
        cells = []
        for r in results:
            m = r.myths[i]
            mark = "✓" if m.hit else "✗"
            rank = m.first_expected_rank or "-"
            cells.append(f"{mark} rank {rank}, top {m.top_source}")
        expected = ", ".join(myth_result.myth.expected)
        lines.append(f"| {myth_result.myth.claim} | {expected} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
