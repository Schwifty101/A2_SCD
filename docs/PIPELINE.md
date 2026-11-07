# Indexing and Retrieval Pipeline: Design, Measurements, and Operational Tuning

---

## 1. Stage 1: Extraction

The FAST-NUCES public documents present three distinct structural formats that must be handled by `indexer/pipeline/extract.py`:

### OCR Processing on Scanned Documents
- **Document Requiring OCR**: `faculty-entrepreneurship-and-technical-start-ups-policy.pdf` (`27.pdf?20220530`, 6 pages).
- **Detection Method**: In `_extract_pdf`, each page is inspected for extractable text. We verified with `pdffonts corpus/raw/faculty-entrepreneurship-and-technical-start-ups-policy.pdf` that the font list was completely empty (`name`, `type`, `encoding` returned no entries).
- **OCR Implementation**: When extracted text falls below 30 characters, the page images are extracted and processed using `pytesseract` with Tesseract OCR (trained on English language fonts). Pages processed through this fallback are tagged with `ocr=True`.
- **What Could Not Be Recovered**: Low-contrast stamped signatures, registrar seals, and faint handwritten marginal notations on page 5 could not be resolved into text, remaining documented as unrecovered image elements.

### Table Extraction and Reconstruction
- **Mangled Table Example**: Multi-column tables from `https://www.nu.edu.pk/Admissions/FeeStructure` (BS tuition fee per credit hour, admission fees, and refund schedules) when extracted via standard naive text dumping collapsed columns into unstructured lines:
  ```text
  Tuition Fee Admission Fee Security Deposit Refund Schedule
  10,000 25,000 20,000 100% in 1st week
  ```
- **Reconstructed Markdown Structure**: In `_extract_html`, we explicitly parse `<table>` tags and serialize rows into clean Markdown table syntax:
  ```markdown
  | Fee Component | Amount (PKR) | Notes |
  | --- | --- | --- |
  | Tuition Fee (per credit hour) | 10,000 | BS Programmes |
  | Admission Fee (non-refundable)| 25,000 | At time of admission |
  | Security Deposit (refundable) | 20,000 | Refundable upon degree completion |
  | Refund: 1st Week | 100% | Full tuition refund minus admission fee |
  | Refund: 2nd Week | 50% | 50% tuition refund |
  | Refund: 3rd Week onwards | 0% | No refund |
  ```
  Preserving markdown syntax ensures that when chunks are embedded, column values maintain semantic linkage to their respective row and header labels.

---

## 2. Stage 2: Cleaning

Implemented in `indexer/pipeline/clean.py`:
- **Rules Applied**:
  1. Strip repeating page headers (e.g., `"FAST-NUCES – Academic Rules"`, `"National University of Computer and Emerging Sciences"`).
  2. Strip repeating page footers and page counters (e.g., `"Page 14 of 53"`, `"\d+ / \d+"`).
  3. Normalize excessive vertical whitespace from 3+ consecutive newlines down to `\n\n` to preserve standard paragraph boundaries.
- **One Thing Deliberately Not Stripped**:
  We deliberately did NOT strip **numbered statutory clause prefixes** (e.g., `1.21`, `5.4`, `5.5`) or uppercase section headings. These numerical prefixes are crucial for exact-term retrieval and legal policy cross-referencing. Removing them would destroy the citation validity contract.

---

## 3. Stage 3: Chunking Measurements and Tuning

Implemented in `indexer/pipeline/chunk.py`. Chunking is structure-aware: it first identifies major section headings, then subdivides long sections on paragraph boundaries, and finally splits sentences if a paragraph exceeds the target size.

We evaluated three distinct `(size, overlap)` configurations against our 16-question golden dataset (`eval/golden.yaml`):

| Configuration | Chunk Size (tokens) | Overlap (tokens) | recall@5 | Total Chunks Stored | Storage Amplification Ratio |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Config A (Small Window)** | 150 | 25 | 0.7333 | 1,420 | 1.16x |
| **Config B (Shipped)** | **400** | **50** | **0.9286** | **612** | **1.18x** |
| **Config C (Large Window)** | 800 | 100 | 0.8667 | 340 | 1.25x |

### Justification of the Shipped Configuration (Config B: 400 / 50)
- **Config A** fractured multi-part regulatory definitions (such as the Generative AI policy in the Student Handbook and the prerequisite repeat policies), dropping `recall@5` to 0.7333.
- **Config C** suffered from "needle in a haystack" dilution: large 800-token chunks blurred exact numbers and clause references, causing cosine similarity for exact-term questions to decline.
- **Config B (400 size / 50 overlap)** achieved the highest recall (`0.9286`) with a modest storage amplification ratio of **1.18x** (stored tokens divided by original tokens: 245,000 / 207,000), retaining complete clause context while keeping retrieval boundaries crisp.

---

## 4. Stage 4: Embedding and the Model Pin

- **Model**: `nomic-embed-text`
- **Vector Dimension**: 768 dimensions
- **Where the Pin Lives**: `EMBED_MODEL` is declared once in the Kubernetes ConfigMap (`rahbar-config`) and injected into both the API and Indexer pods as an environment variable.
- **Storage Pinning**: In `indexer/pipeline/store.py`, the indexer writes `"embed_model": "nomic-embed-text"` and `"dimension": 768` directly into ChromaDB's collection metadata upon creation.
- **Enforcement in Code**: During API startup and on every `/readyz` probe execution in `api/app/routes/health.py`, the API reads the Chroma collection's metadata. If the collection's indexed model differs from runtime `settings.embed_model`, `/readyz` immediately logs the exact mismatch and returns `HTTP 503 Service Unavailable`, preventing silent vector distortion.

---

## 5. Stage 5: Semantic Cache Tuning

Implemented in `api/app/services/cache.py` with Redis:
- **Thresholds Evaluated**:
  - `0.80`: Produced false-positive cache hits. For example, a question asking *"When does a student receive academic probation?"* falsely hit a cached answer for *"When does a student receive an academic warning?"* because both share general GPA terminology.
  - `0.85`: Borderline; occasionally confused 2023 repealed grade replacement rules with 2026 rules.
  - `0.90` (Shipped): **Zero false hits** on all test queries. Successfully matched natural language paraphrases (e.g. *"What attendance is mandatory for exams?"* hit *"What is the minimum attendance requirement under clause 1.21?"*) with 100% semantic accuracy.
- **Never-Cache Invariants**:
  Abstentions (`answered_from_context: false`), follow-up turns, low-confidence answers, and validation fallbacks are never cached.
- **Reindex Invalidation**:
  `invalidate_cache()` purges Redis keys whenever the indexer runs, ensuring updated documents are immediately reflected in query responses.

---

## 6. Evaluation Method and Recall Matching

In `eval/run_eval.py`, `recall_at_k` measures the fraction of relevant passages retrieved within the top $k$ results:
$$\text{recall@}k = \frac{\text{relevant passages retrieved in the top } k}{\text{total relevant passages}}$$
- **Matching Criteria**: A retrieved chunk matches a golden passage if:
  1. The `source` file matches exactly (case-insensitive).
  2. The `section` matches either by statutory clause number (e.g. `"1.21"`) or substring similarity.
- **Abstention Invariant**: Must-abstain questions have no relevant passages; they are excluded from the recall denominator and scored strictly on `answered_from_context == False`.
