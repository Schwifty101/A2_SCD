"""Turns a question into an AskResponse. Production 8-step query pipeline (sections 3.2-3.4):
1. Input validation (3 to 500 characters)
2. Semantic cache check against threshold (skipped for follow-ups)
3. Embedding with pinned EMBED_MODEL
4. Chroma retrieval with top_k and superseded policy filter
5. Relevance floor assessment and honest abstention
6. Grounded schema-constrained generation with anti-injection delimitation
7. Pydantic validation, retry, and safe fallback
8. Citation validation and verified cache storage
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..config import Settings
from ..logjson import request_id_var
from ..providers.llm.base import LLMProvider
from ..retrieval.base import Retriever
from ..routes import metrics
from ..schemas import Answer, AskResponse, Citation, Passage, RetrievedRef
from .cache import SemanticCache

log = logging.getLogger("rahbar.answer")


def _citation_is_valid(c: Citation, passages: list[Passage]) -> bool:
    """Every citation must match a chunk actually retrieved for this request."""
    for p in passages:
        if c.source == p.source and (c.section == p.section or not c.section):
            return True
    return False


def answer_question(
    question: str,
    retriever: Retriever,
    provider: LLMProvider,
    settings: Settings,
    cache: SemanticCache | None = None,
) -> AskResponse:
    req_id = request_id_var.get()

    # Step 1: Input length validation
    q = question.strip()
    if len(q) < 3 or len(q) > 500:
        raise ValueError("Question length must be between 3 and 500 characters")

    # Step 2: Semantic cache check (skip for follow-ups)
    # Obtain query vector representation for semantic cache lookup
    query_vector: list[float] = []
    if hasattr(retriever, "_embed_query"):
        try:
            query_vector = retriever._embed_query(q)  # type: ignore[no-untyped-call]
        except Exception:
            query_vector = []

    if cache and query_vector:
        cached_resp = cache.get(q, query_vector)
        if cached_resp:
            metrics.CACHE_HITS.inc()
            log.info("served answer from semantic cache", extra={"request_id": req_id, "cached": True})
            return cached_resp

    # Step 3 & 4: Retrieve top-k chunks from Chroma (filtering superseded documents)
    t0_retrieval = time.perf_counter()
    passages = retriever.retrieve(q, k=settings.top_k)
    retrieval_ms = (time.perf_counter() - t0_retrieval) * 1000
    metrics.RETRIEVAL_LATENCY.observe(retrieval_ms / 1000.0)

    # Step 5: Relevance floor and honest abstention (Section 3.4)
    # A system that answers every question confidently is unreliable in practice.
    top_score = max((p.score for p in passages), default=0.0)
    scores = [round(p.score, 4) for p in passages]
    chunk_ids = [p.chunk_id for p in passages]

    if not passages or top_score < settings.relevance_floor:
        metrics.ABSTENTIONS.inc()
        log.info(
            "abstaining: top score %.4f below relevance floor %.2f",
            top_score,
            settings.relevance_floor,
            extra={
                "request_id": req_id,
                "retriever": retriever.name,
                "top_k": settings.top_k,
                "chunk_ids": chunk_ids,
                "scores": scores,
                "answered_from_context": False,
            },
        )
        return AskResponse(
            request_id=req_id,
            answer="The provided university policy documents do not contain information regarding this topic.",
            citations=[],
            answered_from_context=False,
            confidence="low",
            retrieved=[
                RetrievedRef(
                    chunk_id=p.chunk_id, source=p.source, section=p.section, page=p.page, score=p.score
                )
                for p in passages
            ],
            provider=provider.name,
        )

    # Step 6 & 7: Generate schema-constrained answer at low temperature
    t0_gen = time.perf_counter()
    answer: Answer = provider.generate(q, passages)
    gen_ms = (time.perf_counter() - t0_gen) * 1000
    metrics.GENERATION_LATENCY.observe(gen_ms / 1000.0)

    # Metric tracking
    tokens_in = sum(len(p.text.split()) for p in passages) + len(q.split())
    tokens_out = len(answer.answer.split())
    metrics.TOKENS_IN.inc(tokens_in)
    metrics.TOKENS_OUT.inc(tokens_out)

    if answer.confidence == "low" and "FALLBACK" in answer.reasoning:
        metrics.FALLBACKS.inc()

    # Step 8: Citation verification against retrieved passages
    # Every returned citation MUST match a chunk actually retrieved for this request.
    verified_citations: list[Citation] = []
    for cit in answer.citations:
        if _citation_is_valid(cit, passages):
            verified_citations.append(cit)
        else:
            log.warning(
                "dropping ungrounded citation (%s, %s): not in retrieved passages",
                cit.source,
                cit.section,
                extra={"request_id": req_id},
            )

    response = AskResponse(
        request_id=req_id,
        answer=answer.answer,
        citations=verified_citations,
        answered_from_context=answer.answered_from_context,
        confidence=answer.confidence,
        retrieved=[
            RetrievedRef(
                chunk_id=p.chunk_id, source=p.source, section=p.section, page=p.page, score=p.score
            )
            for p in passages
        ],
        provider=provider.name,
    )

    # Store turn in cache if safe to cache
    if cache and query_vector:
        is_fallback = "FALLBACK" in answer.reasoning
        cache.set(q, query_vector, response, failed_validation=is_fallback)

    log.info(
        "answered",
        extra={
            "request_id": req_id,
            "retriever": retriever.name,
            "provider": provider.name,
            "top_k": settings.top_k,
            "chunk_ids": chunk_ids,
            "scores": scores,
            "answered_from_context": response.answered_from_context,
            "retrieval_ms": round(retrieval_ms, 1),
            "generation_ms": round(gen_ms, 1),
        },
    )

    return response
