"""Stage 2: Clean. Remove artefacts without destroying structure."""

from __future__ import annotations

import re
from .models import Document, Page


def _clean_page_text(text: str) -> str:
    """Clean repeating headers, footers, and noise while preserving headings and sections."""
    lines = text.splitlines()
    cleaned_lines: list[str] = []

    # Common repeating header/footer patterns
    header_footer_patterns = [
        re.compile(r"^\s*page\s+\d+(\s+of\s+\d+)?\s*$", re.I),
        re.compile(r"^\s*\d+\s*/\s*\d+\s*$"),
        re.compile(r"^\s*fast-nuces\s*[-–]\s*academic\s+rules\s*$", re.I),
        re.compile(r"^\s*national\s+university\s+of\s+computer\s+and\s+emerging\s+sciences\s*$", re.I),
        re.compile(r"^\s*student\s+handbook\s+2026\s*$", re.I),
    ]

    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue

        # Check if line matches a known repeating header/footer pattern
        if any(pat.match(stripped) for pat in header_footer_patterns):
            continue

        # Preserve structural headings (e.g., "1.21 Attendance", "Section 5", "## Header")
        # Do not strip numbered clauses or section titles
        cleaned_lines.append(line)

    result = "\n".join(cleaned_lines)
    # Normalize excessive blank lines while preserving paragraph boundaries
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result


def clean(doc: Document) -> Document:
    """Strip repeating headers and footers; keep headings and section boundaries."""
    cleaned_pages: list[Page] = []
    for page in doc.pages:
        cleaned_text = _clean_page_text(page.text)
        cleaned_pages.append(
            Page(
                source=page.source,
                page=page.page,
                text=cleaned_text,
                ocr=page.ocr,
            )
        )
    return Document(
        source=doc.source,
        doc_version=doc.doc_version,
        superseded=doc.superseded,
        pages=cleaned_pages,
    )
