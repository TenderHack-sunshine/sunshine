from __future__ import annotations

from pathlib import Path

from .base import clean_text


def parse_docx(path: str | Path) -> list[dict]:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    path = Path(path)
    document = Document(path)
    parts: list[str] = []
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            paragraph = Paragraph(child, document)
            value = paragraph.text.strip()
            if not value:
                continue
            style = paragraph.style.name.casefold() if paragraph.style else ""
            if "heading" in style or "заголов" in style:
                parts.append(f"# {value}")
            elif "list" in style or "спис" in style:
                parts.append(f"- {value}")
            else:
                parts.append(value)
        elif child.tag.endswith("}tbl"):
            table = Table(child, document)
            rows = [[clean_text(cell.text).replace("\n", " ") for cell in row.cells] for row in table.rows]
            rows = [row for row in rows if any(row)]
            if not rows:
                continue
            headers = rows[0]
            for row in rows[1:] or rows:
                parts.append(" | ".join(f"{headers[index] or f'Column {index + 1}'}: {value}" for index, value in enumerate(row) if value))
    text = clean_text("\n".join(parts))
    return [] if not text else [{
        "text": text, "source": path.name, "page": None, "document_type": "manual",
        "source_type": "docx", "authority": "manual",
    }]
