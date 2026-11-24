"""Comment in, cited reply out (Design.md, Two-stage reply).

Classify → embed the claim → cache lookup → on a miss: sources search, Facts, citation
check, cache write → Reply → reply checks. Each model call whose output fails to parse or
fails its check is retried once; a second failure is a 502. Steps run one after another.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
import openai

from climate_chat.config import ServiceSettings
from climate_chat.openrouter import ChatResult, ContentBlocked, CreditCapReached, EmbeddingError
from climate_chat.service import prompts
from climate_chat.service.api import unavailable, upstream_error
from climate_chat.service.cache import AnswerCache, Sources
from climate_chat.service.cards import AnswerCard, Classification
from climate_chat.service.checks import check_card, check_reply
from climate_chat.vectors import Match, VectorIndex

TOP_K = 5
MAX_LOGGED_OUTPUT = 1000  # characters of a failed model output kept for the logs

NOT_A_CLAIM_REPLY = (
    "I only reply to comments that question climate science or climate solutions, "
    "and this one doesn't look like that kind of claim."
)

BLOCKED_REPLY = "Sorry, I can't reply to that comment."


class _Chat(Protocol):
    def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        schema: dict[str, Any],
        reasoning: bool = False,
    ) -> ChatResult: ...


class _Embedder(Protocol):
    def embed_query(self, text: str) -> np.ndarray: ...


@dataclass
class Trace:
    """What the request did, filled in as it goes, so a failed request is logged too."""

    calls: list[tuple[str, ChatResult]] = field(default_factory=list)
    claim: str | None = None
    cards_category: str | None = None
    cached: bool = False
    card: AnswerCard | None = None  # for evaluation reports
    # One entry per failed attempt: {role, problems, output}, so a 502 can be diagnosed.
    failures: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class PipelineResult:
    reply: str
    citations: list[dict[str, Any]]
    fallacy: str | None
    cached: bool
    outcome: str  # "reply" | "not_a_claim" | "blocked"


class _Retry(Exception):
    """The model's output failed a check; `problems` are sent back with the retry."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _pages(meta: dict[str, Any]) -> str:
    start, end = meta.get("page_start"), meta.get("page_end")
    return str(start) if start == end or end is None else f"{start}-{end}"


class Pipeline:
    def __init__(
        self,
        *,
        chat: _Chat,
        embedder: _Embedder,
        sources: VectorIndex,
        cache: AnswerCache,
        settings: ServiceSettings,
    ):
        self.chat = chat
        self.embedder = embedder
        self.sources = sources
        self.cache = cache
        self.settings = settings

    def run(self, comment: str, style: str, platform: str | None, trace: Trace) -> PipelineResult:
        try:
            return self._run(comment, style, platform, trace)
        except ContentBlocked as e:
            # OpenRouter refused the text itself (e.g. a prompt injection attempt).
            print(f"comment blocked by OpenRouter: {e}")
            return PipelineResult(BLOCKED_REPLY, [], None, False, "blocked")
        except CreditCapReached:
            raise unavailable() from None
        except (openai.OpenAIError, EmbeddingError) as e:
            raise upstream_error() from e

    def _run(self, comment: str, style: str, platform: str | None, trace: Trace) -> PipelineResult:
        s = self.settings
        classification = self._call(
            trace,
            "classify",
            s.model_classify,
            prompts.classify_messages(comment),
            prompts.CLASSIFY_SCHEMA,
            lambda data: Classification.from_dict(data),
        )
        if not classification.is_target or not classification.claim.strip():
            return PipelineResult(NOT_A_CLAIM_REPLY, [], None, False, "not_a_claim")
        trace.claim = classification.claim
        trace.cards_category = classification.cards_category

        vector = self.embedder.embed_query(classification.claim)
        hit = self.cache.get(vector)
        if hit:
            trace.cached = True
            card, sources = hit.card, hit.sources
        else:
            card, sources = self._facts(classification.claim, vector, trace)
            self.cache.put(vector, card, sources)
        trace.card = card

        def parse_reply(data: Any) -> tuple[str, list[str]]:
            text, ids = data.get("reply"), data.get("source_ids")
            if not isinstance(text, str) or not isinstance(ids, list):
                raise ValueError("reply has the wrong shape")
            problems = check_reply(text, ids, card, prompts.reply_length(platform))
            if problems:
                raise _Retry(problems)
            return text.strip(), [str(i) for i in ids]

        reply, cited = self._call(
            trace,
            "reply",
            s.model_reply,
            prompts.reply_messages(comment, classification.tone, card, style, platform),
            prompts.REPLY_SCHEMA,
            parse_reply,
        )
        ids = list(dict.fromkeys(cited)) or card.source_ids
        citations = [{"source_id": i, **sources[i]} for i in ids if i in sources]
        return PipelineResult(reply, citations, card.fallacy, trace.cached, "reply")

    def search(self, vector: np.ndarray) -> list[Match]:
        """The Facts Search: top 5 chunks, leaving out any excluded licences."""
        excluded = list(self.settings.excluded_licences)
        query_filter = {"licence": {"$nin": excluded}} if excluded else None
        return self.sources.query(vector, top_k=TOP_K, filter=query_filter)

    def _facts(self, claim: str, vector: np.ndarray, trace: Trace) -> tuple[AnswerCard, Sources]:
        s = self.settings
        matches = self.search(vector)
        if not matches:
            raise upstream_error()
        retrieved = {m.key for m in matches}

        def parse_card(data: Any) -> AnswerCard:
            card = AnswerCard.from_dict(data)
            problems = check_card(card, retrieved)
            if problems:
                raise _Retry(problems)
            return card

        card = self._call(
            trace,
            "facts",
            s.model_facts,
            prompts.facts_messages(claim, matches),
            prompts.FACTS_SCHEMA,
            parse_card,
        )
        by_key = {m.key: m.metadata for m in matches}
        sources = {
            sid: {
                "title": by_key[sid].get("title", ""),
                "url": by_key[sid].get("citation_url", ""),
                "pages": _pages(by_key[sid]),
            }
            for sid in card.source_ids
        }
        return card, sources

    def _call[T](
        self,
        trace: Trace,
        role: str,
        model: str,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        parse: Callable[[Any], T],
    ) -> T:
        """One model call plus one retry if its output is empty, unparseable or fails its
        check. The retry carries the failed output and the problems found. Every attempt is
        recorded in the trace, so its cost is logged."""
        attempt = messages
        for _ in range(2):
            result = self.chat.complete(
                model, attempt, max_tokens=self.settings.max_tokens[role], schema=schema
            )
            trace.calls.append((role, result))
            try:
                return parse(json.loads(result.text))
            except _Retry as e:
                problems = e.problems
            except (ValueError, TypeError, AttributeError) as e:
                problems = [f"the output wasn't valid JSON in the required shape ({e})"]
            trace.failures.append(
                {"role": role, "problems": problems, "output": result.text[:MAX_LOGGED_OUTPUT]}
            )
            # Retry once, showing the model its output and what was wrong with it.
            attempt = [
                *messages,
                {"role": "assistant", "content": result.text},
                {
                    "role": "user",
                    "content": "That output failed these checks:\n"
                    + "\n".join(f"- {p}" for p in problems)
                    + "\nReturn a corrected version that passes them, as valid JSON.",
                },
            ]
        raise upstream_error()
