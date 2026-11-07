# RAG Pipeline Failure Analysis: Deliberate Stage Breakage and Diagnoses

To demonstrate end-to-end observability and validate that our metrics, logs, and evaluation gates catch real-world degradation, we intentionally broke four stages of the RAG pipeline one at a time. This document records the symptoms, diagnosis, and remedy for each.

---

## 1. Stage A · Extraction (Scanned PDF Ingestion Without OCR)

- **What We Broke**: In `indexer/pipeline/extract.py`, we disabled the OCR branch and forced image-only PDFs to return empty text strings (`text = ""`) when no embedded PDF font text layer was detected.
- **Symptom**: When querying the Entrepreneurship and Technical Start-ups Policy (`"What percentage of equity may faculty hold in university spin-offs?"`), the API returned `answered_from_context: false` with zero citations, even though the document was present in the corpus. In `eval/run_eval.py`, `recall@5` dropped significantly.
- **Diagnosis (as if not caused on purpose)**:
  1. Inspected application logs: `api` log showed:
     ```json
     {"logger": "rahbar.answer", "msg": "abstaining: top score 0.2814 below relevance floor 0.65", "chunk_ids": []}
     ```
  2. Inspected the Chroma vector collection via python:
     ```python
     chunks = collection.get(where={"source": "faculty-entrepreneurship-and-technical-start-ups-policy.pdf"})
     print(len(chunks["documents"]), [len(d) for d in chunks["documents"]])
     ```
     Observed 6 chunks all with length 0 characters.
  3. Ran `pdffonts corpus/raw/faculty-entrepreneurship-and-technical-start-ups-policy.pdf`: the font list was empty. The diagnosis was immediate: the PDF is a pure raster scan with no text stream.
- **Remedy**: Re-enabled `pytesseract` OCR extraction in `_extract_pdf()`, ensuring system packages `tesseract-ocr` and `poppler-utils` are installed in the indexer Dockerfile. Chunks from scanned pages are tagged `ocr=True` and properly embedded.

---

## 2. Stage B · Chunking (Fixed-Size 100-Token Windows with Zero Overlap)

- **What We Broke**: Modified `indexer/pipeline/chunk.py` to use a naive fixed-size window of 100 tokens with zero token overlap (`CHUNK_SIZE = 100`, `CHUNK_OVERLAP = 0`), discarding section boundary awareness.
- **Symptom**: On golden questions involving compound policies (e.g. `q01` Academic Warning and `q10` Generative AI Policy), retrieval returned fragmented sentences. The LLM produced low-confidence answers or hallucinated conditional qualifications because the antecedent conditions and punitive clauses were stored in different chunks. `recall@5` on our golden evaluation gate plummeted from `0.9286` to `0.4667`, causing CI to fail immediately with exit code 1.
- **Diagnosis (as if not caused on purpose)**:
  1. The CI e2e-eval job failed with:
     ```text
     GATE FAILED:
     - recall@5 dropped by 0.4619 (allowed max: 0.0500): 0.4667 vs baseline 0.9286
     ```
  2. Inspected retrieved chunk logs for `q01`:
     ```json
     {"msg": "answered", "chunk_ids": ["chk-a1b2", "chk-c3d4"], "scores": [0.71, 0.68]}
     ```
     Viewing chunk `chk-a1b2` revealed only: `"...is placed on academic warning if the SGPA falls below"`. The critical threshold (`2.00`) was cut off and placed in chunk `chk-c3d4`, which was ranked outside top-k.
- **Remedy**: Restored structure-aware chunking with `CHUNK_SIZE = 400` and `CHUNK_OVERLAP = 50`, grouping sentences under their parent statutory heading (`[5.4 Academic Warning]`).

---

## 3. Stage C · Retrieval (Embedding Model Pin Desynchronization)

- **What We Broke**: Left the vector collection indexed with `nomic-embed-text` (768 dimensions), but changed the API's `EMBED_MODEL` in `k8s/base/configmap.yaml` to `all-minilm` (384 dimensions) and restarted only the API deployment.
- **Symptom**: The API pods failed to become ready: `kubectl get pods -n rahbar` reported `0/1 READY` with status `Running`. All user traffic was safely shielded because the endpoints were withheld from the Kubernetes Service.
- **Diagnosis (as if not caused on purpose)**:
  1. Checked pod status:
     ```bash
     kubectl describe pod api-79b88cfbb8-4f8x2 -n rahbar
     ```
     Events showed readiness probe failed:
     ```text
     Warning  Unhealthy  10s  kubelet  Readiness probe failed: HTTP probe failed with statuscode: 503
     ```
  2. Inspected API container logs:
     ```bash
     kubectl logs -l app.kubernetes.io/name=api -n rahbar --tail=20
     ```
     Output showed the exact embedding pin guardrail log line:
     ```json
     {"logger": "rahbar.health", "level": "ERROR", "msg": "Embedding pin guardrail conflict - mismatch: collection was indexed with nomic-embed-text but runtime EMBED_MODEL is all-minilm"}
     ```
- **Remedy**: Without the guardrail in `api/app/routes/health.py`, the API would have silently compared 384-dimensional query vectors against 768-dimensional document vectors, returning complete garbage without throwing an exception. The remedy was restoring `EMBED_MODEL: "nomic-embed-text"` in `configmap.yaml` and restarting the API deployment.

---

## 4. Stage E · Source Governance (Superseded Policy Filter Removal)

- **What We Broke**: In `api/app/retrieval/chroma.py`, we removed the `where={"superseded": False}` filter, allowing the retriever to search both the 2023 undergraduate rules and the 2026 handbook without version discrimination.
- **Symptom**: On version-sensitive golden question `q06` (*"Under current regulations, if an undergraduate repeats a course, which grade replaces the previous attempt?"*), the system cited the repealed 2023 policy and declared that repeated course grades are capped at a 'C' grade. The 2026 policy, which permits uncapped replacement with the most recent grade, was superseded by the older document due to dense semantic text clustering.
- **Diagnosis (as if not caused on purpose)**:
  1. Ran `eval/run_eval.py`:
     ```text
     q06  FAILED  expect: 'most recent', got citations: [{'source': 'undergraduate-academic-rules-aug-2023.pdf', 'section': '3.2'}]
     ```
  2. Inspected retrieved chunks: the top hit had `doc_version: "2023-08"` and `superseded: true`. Cosine similarity for the 2023 text was 0.89 vs 0.84 for the 2026 text because of vocabulary match.
- **Remedy**: Re-applied the metadata filter in `ChromaRetriever.retrieve()`:
  ```python
  metadata_filter = None if asks_older else {"superseded": False}
  ```
  This guarantees that repealed documents are strictly excluded unless the user explicitly requests historical/superseded regulations.
