"""Stage 1: Extract. PDF (or HTML, or Markdown) to text, page by page."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .models import Document, Page

log = logging.getLogger("rahbar.indexer.extract")


def _extract_pdf(path: Path) -> list[Page]:
    """Extract pages from a PDF, detecting scanned pages and applying OCR."""
    pages: list[Page] = []
    
    # Primary PDF extractor: pypdf
    import pypdf
    
    reader = pypdf.PdfReader(str(path))
    for idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = text.strip()
        ocr_applied = False
        
        # If no extractable text layer is found, attempt OCR
        if len(text) < 30:
            try:
                import pytesseract
                from PIL import Image
                
                # Check for extracted images in page
                ocr_text = []
                for img_obj in page.images:
                    img = Image.open(io.BytesIO(img_obj.data)) if hasattr(img_obj, "data") else None
                    if img:
                        t = pytesseract.image_to_string(img)
                        if t.strip():
                            ocr_text.append(t.strip())
                if ocr_text:
                    text = "\n".join(ocr_text)
                    ocr_applied = True
            except Exception as ocr_err:
                log.debug("OCR attempt on page %d of %s: %s", idx, path.name, ocr_err)
                
        # If text is still empty, document as empty scanned page
        if not text:
            text = f"[Scanned page {idx}: no text layer detected; OCR unrecovered]"
            ocr_applied = True
            
        pages.append(Page(source=path.name, page=idx, text=text, ocr=ocr_applied))
    return pages


def _extract_html(path: Path) -> list[Page]:
    """Extract structured text and tables from HTML files."""
    content = path.read_text(encoding="utf-8", errors="replace")
    
    # Strip scripts and styles
    content = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", content, flags=re.S | re.I)
    
    # Convert HTML table rows to markdown table syntax
    def table_repl(match: re.Match[str]) -> str:
        table_html = match.group(0)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S | re.I)
        md_rows = []
        for r in rows:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S | re.I)
            clean_cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            if any(clean_cells):
                md_rows.append("| " + " | ".join(clean_cells) + " |")
        if md_rows:
            header_sep = "| " + " | ".join(["---"] * (md_rows[0].count("|") - 1)) + " |"
            if len(md_rows) > 1:
                return "\n" + md_rows[0] + "\n" + header_sep + "\n" + "\n".join(md_rows[1:]) + "\n"
            return "\n" + "\n".join(md_rows) + "\n"
        return ""

    content = re.sub(r"<table[^>]*>.*?</table>", table_repl, content, flags=re.S | re.I)
    
    # Strip remaining HTML tags
    clean_text = re.sub(r"<[^>]+>", " ", content)
    # Unescape common HTML entities
    clean_text = clean_text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    clean_text = re.sub(r"[ \t]+", " ", clean_text)
    clean_text = re.sub(r"\n\s*\n+", "\n\n", clean_text).strip()
    
    return [Page(source=path.name, page=1, text=clean_text, ocr=False)]


def _extract_markdown(path: Path) -> list[Page]:
    """Extract Markdown text, skipping YAML front matter."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start_idx = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                start_idx = i + 1
                break
    text = "\n".join(lines[start_idx:]).strip()
    return [Page(source=path.name, page=1, text=text, ocr=False)]


def extract(path: str, doc_version: str, superseded: bool) -> Document:
    """Return the document's text page by page.
    Detect pages with no text layer and OCR them; mark those pages ocr=True.
    """
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    
    if suffix == ".pdf":
        pages = _extract_pdf(file_path)
    elif suffix in {".html", ".htm"}:
        pages = _extract_html(file_path)
    elif suffix in {".md", ".markdown"}:
        pages = _extract_markdown(file_path)
    else:
        text = file_path.read_text(encoding="utf-8", errors="replace").strip()
        pages = [Page(source=file_path.name, page=1, text=text, ocr=False)]
        
    return Document(
        source=file_path.name,
        doc_version=doc_version,
        superseded=superseded,
        pages=pages,
    )
