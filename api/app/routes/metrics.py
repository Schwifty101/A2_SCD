"""Prometheus metrics at /metrics (section 4.8).
Exposes:
- Request count and latency
- Retrieval latency and generation latency
- Cache hits and abstentions
- Fallbacks and token throughput
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

router = APIRouter()

REQUESTS = Counter("rahbar_requests_total", "HTTP requests", ["path", "status"])
LATENCY = Histogram(
    "rahbar_request_seconds",
    "HTTP request latency",
    ["path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)

RETRIEVAL_LATENCY = Histogram(
    "rahbar_retrieval_seconds",
    "Vector store retrieval latency",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
GENERATION_LATENCY = Histogram(
    "rahbar_generation_seconds",
    "LLM generation latency",
    buckets=(0.1, 0.5, 1, 2, 5, 10, 20, 40),
)
CACHE_HITS = Counter("rahbar_cache_hits_total", "Semantic cache hits")
ABSTENTIONS = Counter(
    "rahbar_abstentions_total", "Questions declined due to lack of relevant evidence"
)
FALLBACKS = Counter(
    "rahbar_fallbacks_total", "Safe fallback responses triggered on schema or timeout error"
)
TOKENS_IN = Counter("rahbar_tokens_in_total", "Tokens ingested in prompt")
TOKENS_OUT = Counter("rahbar_tokens_out_total", "Tokens generated in responses")


@router.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
