from __future__ import annotations

import csv
from pathlib import Path

from .base import clean_text, read_text_with_fallback


def parse_csv(path: str | Path) -> list[dict]:
    path = Path(path)
    text = read_text_with_fallback(path)
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(text.splitlines(), dialect))
    rows = [row for row in rows if any(clean_text(value) for value in row)]
    if len(rows) < 2:
        return []
    headers = [clean_text(value) or f"Column {index + 1}" for index, value in enumerate(rows[0])]
    documents = []
    for row_number, row in enumerate(rows[1:], start=2):
        fields = [f"{headers[index]}: {clean_text(value)}" for index, value in enumerate(row) if clean_text(value)]
        if fields:
            documents.append({
                "text": f"Columns: {' | '.join(headers)}\n" + "\n".join(fields), "source": path.name,
                "page": None, "row": row_number, "document_type": "table_row", "source_type": "csv", "authority": "manual",
            })
    return documents
