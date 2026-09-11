from __future__ import annotations

from pathlib import Path

from .base import clean_text, is_toc_page


def repair_line_wraps(text: str) -> str:
    """Repair only safe hyphenated/continuation wraps; keep paragraph boundaries."""
    text = text.replace("\r\n", "\n")
    text = __import__("re").sub(r"(?<=\w)-\n(?=\w)", "", text)
    lines = text.splitlines()
    repaired: list[str] = []
    for line in lines:
        line = line.strip()
        if repaired and line and line[0].islower() and repaired[-1] and not repaired[-1].endswith((".", "!", "?", ":", ";")):
            repaired[-1] = f"{repaired[-1]} {line}"
        else:
            repaired.append(line)
    return "\n".join(repaired)


def parse_pdf(path: str | Path) -> list[dict]:
    """Parse PDF page-by-page so page metadata survives retrieval."""
    import fitz

    path = Path(path)
    documents: list[dict] = []
    with fitz.open(path) as pdf:
        for page_number, page in enumerate(pdf, start=1):
            raw_text = page.get_text("text")
            if not raw_text.strip() or is_toc_page(raw_text):
                continue
            text = clean_text(repair_line_wraps(raw_text))
            if text:
                document = {
                    "text": text, "source": path.name, "page": page_number,
                    "document_type": "manual", "source_type": "pdf", "authority": "manual",
                }
                if len(text) < 30:
                    document["likely_scanned"] = True
                documents.append(document)
    return documents
