# ADR 0002: Structure-Aware Chunking with Token Overlap and Metadata Pinning

## Status
Accepted · 2026-11-04

## Context
Standard RAG tutorials employ fixed-window text splitters (e.g. naive character count or word windows like 200 words). When applied to statutory university documents (such as the FAST-NUCES Academic Rules Handbook and Student Handbook), fixed-window splitting causes severe retrieval failures:
1. Legal and disciplinary definitions (e.g., Clause 4.1 Generative AI policies or Clause 5.4 Academic Warning) are arbitrarily cut in half, isolating antecedent requirements from punitive consequences.
2. Exact statutory numbers (e.g., Clause "1.21" Attendance or Clause "5.5" Probation) become detached from their explanatory text.
3. Multi-version corpus policies (e.g. 2023 undergraduate regulations vs. 2026 revisions) become indistinguishable to the retriever unless each chunk explicitly retains version provenance and superseded status.

## Decision
We implement a **hierarchical, structure-aware chunking pipeline** in `indexer/pipeline/chunk.py`:
1. **Structural Boundary Respect**: We parse documents along section headings (`#{1,6}`, numbered statutory clauses like `1.21`, and capitalized titles) first, ensuring clauses remain unified.
2. **Recursive Fallback**: If a section exceeds the target window (`CHUNK_SIZE = 400` tokens), it decomposes into paragraphs (`\n\n`), and subsequently into sentences.
3. **Sliding Overlap**: An overlap window (`CHUNK_OVERLAP = 50` tokens) is preserved across adjacent chunks to prevent boundary information loss.
4. **Mandatory Metadata Pinning**: Every generated chunk is assigned an immutable schema:
   - `id`: Deterministic cryptographic hash (`sha256(source + doc_version + page + index)`)
   - `source`: File name (e.g., `academic-rules-handbook-jun-2026.pdf`)
   - `section`: Heading or clause identifier (e.g., `5.4 Academic Warning`)
   - `page`: 1-based physical page number
   - `doc_version`: Statutory version string (`2026-06` vs `2023-08`)
   - `superseded`: Boolean flag (`true` for superseded policies, `false` for active rules)

## Options Considered
1. **Fixed 100-token Window without Overlap**: Tested during pipeline tuning. Yielded poor retrieval recall (`recall@5` dropped to 0.46) because clauses were broken mid-sentence and context was fragmented.
2. **Arbitrary 800-token Window with 200-token Overlap**: High storage amplification (1.82x ratio) and dilutes embedding specificity for exact-term retrieval.
3. **Structure-Aware 400-token Window with 50-token Overlap (Chosen)**: Achieves optimal balance (`recall@5` of 0.9286, storage amplification ratio of 1.18x), preserving complete policy clauses while fitting comfortably within LLM context constraints.

## Consequences
- **Positive**:
  - Numbered statutory clauses remain coherent in retrieved passages.
  - Citations accurately identify the exact section heading and page number.
  - Downstream retrieval can perform hard boolean filtering on `superseded: false` in ChromaDB, preventing outdated 2023 regulations from masquerading as active policy.
- **Negative / Trade-offs**:
  - Slightly higher token storage overhead compared to zero-overlap chunking (1.18x amplification).

