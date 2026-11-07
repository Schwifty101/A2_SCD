# ADR 0003: Semantic Cache Storage and Invalidation Strategy

## Status
Accepted · 2026-11-05

## Context
Generative inference against LLMs is computationally expensive and introduces substantial latency (500ms to 4s per request). In an academic portal, many student questions exhibit semantic equivalence (e.g. *"What is the minimum attendance to sit exams?"* vs. *"How much attendance is required for finals?"*).

A semantic cache captures question embeddings and returns verified responses when cosine similarity exceeds a strict threshold. However, semantic caching introduces acute operational risks:
1. Serving stale answers after corpus re-indexing.
2. Caching erroneous model outputs, hallucinations, or prompt-injected responses.
3. Caching conversational follow-up questions that depend on conversational context.
4. Caching honest abstentions, causing the system to refuse future questions that might now be answerable.

## Decision
1. **Cache Store**: We choose **Redis** deployed with persistent storage (`PersistentVolumeClaim`) in the `rahbar` namespace, with an in-memory fallback for lightweight testing.
2. **Similarity Threshold**: We set `CACHE_THRESHOLD = 0.90`. During testing, a threshold of 0.80 yielded false-positive hits (e.g. confusing *Academic Warning* at 2.00 GPA with *Academic Probation* after two consecutive semesters). A threshold of 0.90 produced 0% false hits across our golden evaluation suite while successfully matching semantically rephrased queries.
3. **Never-Cache Safety Guardrails**:
   - Out-of-scope answers and honest abstentions (`answered_from_context: false`) are NEVER cached.
   - Low confidence responses (`confidence: "low"`) or responses generated via the fallback handler are NEVER cached.
   - Conversational follow-up turns (detected via linguistic markers and pronoun antecedents) are NEVER cached.
4. **Cache Invalidation on Re-index**:
   - The indexer Job or operator can execute `invalidate_cache()`, purging Redis keys upon successful index updates to ensure new documents are served immediately.

## Options Considered
1. **Second Chroma Collection for Cache**:
   - Feasible, but ChromaDB adds unnecessary disk I/O overhead and complex TTL management compared to dedicated in-memory key-value data stores.
2. **Exact String Match Cache (MD5/SHA256)**:
   - Fails on trivial punctuation or synonym differences; cache hit ratio remains under 10%.
3. **Redis Semantic Cache with 0.90 Cosine Threshold (Chosen)**:
   - Provides sub-millisecond retrieval on cache hits, native key expiration (TTL: 86400s), and straightforward atomic invalidation.

## Consequences
- **Positive**:
  - Dramatically reduces LLM token consumption and p99 query latency for frequent student questions.
  - Guardrails prevent poisoning the cache with hallucinated or fallback outputs.
- **Negative / Trade-offs**:
  - Requires deploying and maintaining a Redis Deployment, PVC, and Service in Kubernetes, with associated NetworkPolicy rules.

