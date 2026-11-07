"""Semantic cache layer (sections 3.3 and 4.7).
Stores question embeddings and verified answers with similarity thresholding and invalidation.
"""

from __future__ import annotations

import json
import logging
import math
import re
from typing import Any

from ..config import Settings
from ..schemas import AskResponse

log = logging.getLogger("rahbar.cache")


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


def is_followup(question: str) -> bool:
    """Identify conversational follow-up questions that depend on prior turns."""
    patterns = [
        r"^(and|but|also|what about|how about|why|so)\b",
        r"\b(it|they|them|he|she|this rule|that policy|the same)\b",
    ]
    q = question.strip().lower()
    return any(re.search(pat, q) for pat in patterns)


def never_cache(
    question: str,
    answered_from_context: bool,
    confidence: str,
    failed_validation: bool = False,
) -> bool:
    """Rules defining requests that must NEVER be written to the cache:
    1. Abstentions (corpus does not answer).
    2. Conversational follow-ups (context dependent).
    3. Low confidence or validation fallbacks.
    4. Out-of-scope or erroneous answers.
    """
    if not answered_from_context:
        return True
    if is_followup(question):
        return True
    if confidence == "low":
        return True
    if failed_validation:
        return True
    return False


class SemanticCache:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.threshold = settings.cache_threshold
        self._memory_cache: list[dict[str, Any]] = []
        self._redis_client = None

        if settings.cache_enabled and settings.retriever != "stub":
            try:
                import redis
                self._redis_client = redis.Redis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    socket_connect_timeout=0.5,
                    decode_responses=True,
                )
                self._redis_client.ping()
                log.info("connected to Redis at %s:%d", settings.redis_host, settings.redis_port)
            except Exception as exc:
                log.warning("Redis unavailable (%s), using in-memory semantic cache fallback", exc)
                self._redis_client = None

    def get(self, question: str, query_vector: list[float]) -> AskResponse | None:
        """Check cache against similarity threshold. Returns cached AskResponse on hit."""
        if not self.settings.cache_enabled:
            return None
        if is_followup(question):
            return None

        # Search in-memory cache
        best_score = -1.0
        best_entry = None

        # If Redis is active, sync entries from Redis
        entries = self._memory_cache
        if self._redis_client:
            try:
                keys = self._redis_client.keys("cache:*")
                redis_entries = []
                for k in keys:
                    data = self._redis_client.get(k)
                    if data:
                        redis_entries.append(json.loads(data))
                if redis_entries:
                    entries = redis_entries
            except Exception as exc:
                log.warning("error reading Redis cache: %s", exc)

        for entry in entries:
            cached_vector = entry.get("vector")
            if not cached_vector:
                continue
            sim = _cosine_similarity(query_vector, cached_vector)
            if sim > best_score:
                best_score = sim
                best_entry = entry

        if best_entry and best_score >= self.threshold:
            log.info("semantic cache hit (similarity: %.4f >= threshold: %.2f)", best_score, self.threshold)
            resp_dict = best_entry["response"]
            return AskResponse.model_validate(resp_dict)

        return None

    def set(
        self,
        question: str,
        query_vector: list[float],
        response: AskResponse,
        failed_validation: bool = False,
    ) -> None:
        """Store a cache entry if it complies with never-cache safety rules."""
        if not self.settings.cache_enabled:
            return
        if never_cache(
            question=question,
            answered_from_context=response.answered_from_context,
            confidence=response.confidence,
            failed_validation=failed_validation,
        ):
            log.debug("skipping cache storage due to never_cache rule")
            return

        entry = {
            "question": question,
            "vector": query_vector,
            "response": response.model_dump(),
        }
        self._memory_cache.append(entry)

        if self._redis_client:
            try:
                key = f"cache:{len(self._memory_cache)}"
                self._redis_client.set(key, json.dumps(entry), ex=86400)
            except Exception as exc:
                log.warning("failed to write to Redis: %s", exc)

    def invalidate_cache(self) -> None:
        """Invalidate all cached answers upon re-indexing."""
        self._memory_cache.clear()
        if self._redis_client:
            try:
                keys = self._redis_client.keys("cache:*")
                if keys:
                    self._redis_client.delete(*keys)
                log.info("flushed Redis semantic cache on reindex invalidation")
            except Exception as exc:
                log.warning("failed to flush Redis cache: %s", exc)

    def clear_cache(self) -> None:
        self.invalidate_cache()
