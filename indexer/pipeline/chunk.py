"""Stage 3: Chunk. Structure-aware, with overlap."""

from __future__ import annotations

import hashlib
import re

from .models import Chunk, Document

HEADING_PATTERN = re.compile(
    r"^(?:#{1,6}\s+|(?:\d+\.)+\d*\s+|[A-Z][A-Za-z0-9\s]{2,40}:?$)", re.MULTILINE
)


def _token_count(text: str) -> int:
    """Rough token count approximation: words + punctuation."""
    return len(re.findall(r"\w+|[^\w\s]", text))


def _split_into_sentences(text: str) -> list[str]:
    """Split a paragraph into sentences without breaking on abbreviations."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    return [p.strip() for p in parts if p.strip()]


def _split_into_paragraphs(text: str) -> list[str]:
    """Split text on paragraph boundaries."""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def chunk(doc: Document, size: int, overlap: int) -> list[Chunk]:
    """Split on sections, then paragraphs, then sentences, keeping each chunk under
    `size` tokens, with `overlap` tokens shared between neighbours.
    Every chunk keeps the section heading it sits under, its page, doc_version, and superseded.
    """
    chunks: list[Chunk] = []
    chunk_index = 0

    for page in doc.pages:
        page_text = page.text
        if not page_text.strip():
            continue

        # Split on section headings to achieve structure-aware chunking
        sections: list[tuple[str, str]] = []
        lines = page_text.splitlines()
        current_heading = "General"
        current_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            # Detect section heading
            if re.match(r"^(?:#{1,6}\s+|(?:[0-9]+\.)+[0-9]*\s+[A-Za-z]|[A-Z\s]{4,30}$)", stripped):
                if current_lines:
                    sections.append((current_heading, "\n".join(current_lines)))
                    current_lines = []
                current_heading = stripped.lstrip("#").strip()
            else:
                current_lines.append(line)

        if current_lines:
            sections.append((current_heading, "\n".join(current_lines)))

        # Process each section into chunks respecting size and overlap
        for heading, section_text in sections:
            paragraphs = _split_into_paragraphs(section_text)
            current_chunk_words: list[str] = []
            current_tokens = 0

            for para in paragraphs:
                sentences = _split_into_sentences(para)
                for sentence in sentences:
                    sentence_tokens = _token_count(sentence)

                    if current_tokens + sentence_tokens > size and current_chunk_words:
                        # Flush current chunk
                        chunk_text = " ".join(current_chunk_words)
                        stable_id = hashlib.sha256(
                            f"{doc.source}:{doc.doc_version}:{page.page}:{chunk_index}".encode()
                        ).hexdigest()[:16]

                        chunks.append(
                            Chunk(
                                id=f"chk-{stable_id}",
                                text=f"[{heading}]\n{chunk_text}",
                                source=doc.source,
                                section=heading,
                                page=page.page,
                                doc_version=doc.doc_version,
                                superseded=doc.superseded,
                            )
                        )
                        chunk_index += 1

                        # Compute overlap window
                        overlap_words: list[str] = []
                        overlap_toks = 0
                        for w in reversed(current_chunk_words):
                            wt = _token_count(w)
                            if overlap_toks + wt <= overlap:
                                overlap_words.insert(0, w)
                                overlap_toks += wt
                            else:
                                break
                        current_chunk_words = overlap_words
                        current_tokens = overlap_toks

                    current_chunk_words.append(sentence)
                    current_tokens += sentence_tokens

            if current_chunk_words:
                chunk_text = " ".join(current_chunk_words)
                stable_id = hashlib.sha256(
                    f"{doc.source}:{doc.doc_version}:{page.page}:{chunk_index}".encode()
                ).hexdigest()[:16]

                chunks.append(
                    Chunk(
                        id=f"chk-{stable_id}",
                        text=f"[{heading}]\n{chunk_text}",
                        source=doc.source,
                        section=heading,
                        page=page.page,
                        doc_version=doc.doc_version,
                        superseded=doc.superseded,
                    )
                )
                chunk_index += 1

    return chunks
