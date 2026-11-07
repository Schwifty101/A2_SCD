# Corpus Documentation: FAST-NUCES Policies and Institutional Data

Source: FAST-NUCES public website (`https://nu.edu.pk`)  
Documents: 9 listed (6 committed/manifested, >150 pages total)  
Total Pages: ~170 pages across handbooks, policies, reports, and statutory regulatory documents.

---

## 1. Overview and Rationale

The RAHBAR question-answering corpus is selected specifically to expose the fundamental failure modes of Retrieval-Augmented Generation (RAG) systems in academic governance. Rather than using an idealized, synthetically cleaned toy corpus, we selected real-world public governance, academic policy, and institutional reporting documents from FAST-NUCES.

The corpus forces the retrieval and generation pipeline to solve:
1. Version conflict (superseded policies vs. active regulations)
2. Unstructured layout degradation (scanned image-only PDFs with no text layer requiring OCR)
3. Structural data mangling (multi-column fee tables, grading scales, and tabular financial reports)
4. Chunk fragmentation (long nested legal definitions and multi-clause Generative AI policies)
5. Out-of-distribution / absent knowledge (honest abstention rather than hallucination on unindexed topics)
6. Precision terminology (exact course codes, clause numbers, and CGPA thresholds that embedding models blur)

---

## 2. Seven Required Properties Mapping

| # | Required Property | Document(s) Providing It | Failure Mode Exposed | Detailed Evidence & Notes |
|---|---|---|---|---|
| **1** | **Scale**: At least 6 documents, >40 pages in total | • `Academic_Rules_Handbook_2026.pdf` (~53 pages)<br>• `Student_Handbook_2026.pdf` (~60 pages)<br>• `Prospectus_2026_Academic_Rules.pdf` (~5 pages)<br>• `Annual_Report_2019-20.pdf` (~40 pages)<br>• `Annual_Report_2023-24.pdf` (~42 pages)<br>• `FeeStructure.html` (~3 pages)<br>• `Grading.html` (~2 pages)<br>• `27.pdf?20220530` (Faculty Start-ups, ~6 pages) | Scale & memory footprint (OOMKill on indexer; latency degradation) | Well exceeds requirements: >170 pages total across statutory handbooks, annual reports, and regulatory policies. |
| **2** | **Two Versions of One Policy** | • `Undergraduate Academic Rules (Aug 2023)` (`doc_version: "2023-08"`, `superseded: true`)<br>• `Academic Rules Handbook (Jun 2026)` (`doc_version: "2026-06"`, `superseded: false`) | **Failure Mode E (Outdated Source)**: The retriever quotes repealed policy rules if filtering is absent. | In the 2023 rules, attendance requirement penalties and grade replacement caps follow the old regulatory scheme; in the 2026 revision, clause 1.21 mandates an 80% attendance threshold and clause 3.2 removes the cap on repeated courses (taking the most recent grade). Metadata filtering on `superseded: false` in Chroma is strictly required to prevent serving revoked policies. |
| **3** | **Scanned, Image-Only PDF** | • `Faculty Entrepreneurship and Technical Start-ups Policy` (`27.pdf?20220530`, `doc_version: "2022-05"`) | **Failure Mode A (Bad Extraction)**: Zero text extracted by standard PDF text layer extractors. | Running `pdffonts corpus/raw/faculty-entrepreneurship-and-technical-start-ups-policy.pdf` returns an empty font list (`name`, `type`, `encoding` all empty), verifying that no text stream or font dictionary exists in the PDF. The indexer applies OCR via Tesseract (`pytesseract` / `tesseract-ocr`) with image binarization; pages extracted through this route are flagged with `ocr: true`. |
| **4** | **Tables with Real Information** | • `Fee Structure page` (`https://www.nu.edu.pk/Admissions/FeeStructure`)<br>• `Grading page` (`https://www.nu.edu.pk/Student/Grading`)<br>• `Annual Report 2019-20` and `2023-24` | **Failure Mode A (Bad Extraction)**: Multi-column tabular data extracted as flattened, jumbled text strings. | The fee structure specifies tuition fee per credit hour (Rs. 10,000 for regular courses), admission fees, security deposit (refundable), and refund schedules by calendar week (100% in week 1, 50% in week 2, 0% thereafter). The grading table maps letter grades to grade points (A=4.00, B+=3.33, B=3.00, etc.). Extraction preserves table row-column semantics using Markdown table syntax to ensure the embedding and generation stages do not detach figures from column headers. |
| **5** | **Long Definitions & Structured Policies** | • `Student Handbook (Jun 2026)` (`Student_Handbook_2026.pdf`, ~60 pages) | **Failure Mode B (Poor Chunking)**: Fixed-size chunking cuts legal clauses and definitions in half. | Contains extended clauses on the Code of Conduct, Disciplinary Proceedings, and a 6-page comprehensive Generative AI Policy with deeply nested subsections (clause 4.1.1 through 4.1.8) covering authorized assistance, prohibited direct output submission, attribution rules, and investigation protocols. A naive 200-word fixed-size chunker splits definitions between antecedent conditions and punitive outcomes, causing retrieval of incomplete rules. We use structure-aware recursive splitting that respects section boundaries and Markdown headings. |
| **6** | **Deliberately Absent Topic** | • Excluded: `Prospectus - Transport and Hostel Facilities` (`https://nu.edu.pk/Admissions/ProspectusUpload/Transport and Hostel Facilities.pdf`) | **Abstention & Grounding (Section 3.4)**: Model hallucinates policies when information is not in corpus. | The student handbook mentions that hostels and university transport buses exist, but all detailed operational rules (hostel allocation criteria, room fees, curfew timings, transport route schedules, and fee concessions) are intentionally omitted from `corpus/sources.yaml`. When a user asks: *"How do I apply for a hostel room?"* or *"What is the monthly bus fee for Route 4?"*, retrieval relevance scores fail to clear the `relevance_floor` (0.65), triggering honest abstention: `answered_from_context: false`. |
| **7** | **Exact-Term Content** | • `Academic Rules Handbook (Jun 2026)`<br>• `Prospectus 2026 - Academic Rules and Regulations`<br>• `Fee Structure page` | **Retrieval Precision Loss**: Dense embeddings blur exact clause numbers, course codes, and thresholds. | The documents specify precise statutory markers: clause `1.21` (Attendance requirement: minimum 80%), clause `5.4` (Academic warning: semester GPA < 2.00), clause `5.5` (Academic probation: CGPA < 2.00 for two consecutive semesters), BS tuition rate (`Rs. 10,000` per credit hour), and course prerequisites (e.g., `CS2001` Data Structures before `CS3001` Algorithms). Dense semantic embeddings tend to cluster all "academic status" queries together; exact-term questions test whether chunks retain clause identifiers and whether the retrieval configuration (or top_k tuning) surfaces the specific clause. |

---

## 3. Real-World Traps in the Selected Documents

Beyond the core rubric properties, the FAST-NUCES website manifests several genuine institutional data traps:
- **Discrepant Clause Numbering**: In `Academic_Rules_Handbook_2026.pdf`, the attendance regulation is numbered Clause `1.21`. In the shorter 5-page summary published in `Prospectus 2026 - Academic Rules and Regulations`, the exact same attendance policy is listed under Section `1`. This tests whether citations point to the definitive handbook or the summary prospectus.
- **Conflicting Terminology**: Academic probation vs. academic warning have identical CGPA thresholds (2.00) but distinct triggers: warning is based on single-semester GPA, whereas probation is based on cumulative GPA (CGPA) over consecutive semesters.
- **Calendar & Year Desynchronization**: The university website links an archived 2023 version of rules directly adjacent to the active 2026 rules. Without metadata partitioning (`superseded: true`), a standard cosine similarity search frequently ranks the older 2023 text higher because of wording proximity.

---

## 4. Manifest and Ingestion Integrity

All documents are declared in `corpus/sources.yaml` with explicit `doc_version` and `superseded` flags. The fetch script (`corpus/fetch.py`) downloads the documents into `corpus/raw/` (gitignored), computes cryptographic SHA-256 digests, and generates `corpus/MANIFEST.md`. The indexer reads `corpus/raw/_index.json` to attach version metadata to every indexed passage.
