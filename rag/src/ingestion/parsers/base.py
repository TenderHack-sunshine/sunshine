from __future__ import annotations

import re
import hashlib
from pathlib import Path
from typing import Callable


def clean_text(text: str) -> str:
    """Keep logical lines, discard obvious table-of-contents noise."""
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw_line.strip())
        if not line or re.fullmatch(r"[.\s\d]+", line):
            continue
        if re.search(r"(?:\.\s*){3,}\s*\d*\s*$", line):
            continue
        lines.append(line)
    return "\n".join(lines)


def read_text_with_fallback(path: str | Path) -> str:
    """Read common local text files without turning Cyrillic into mojibake."""
    file_path = Path(path)
    raw = file_path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def stable_local_document_id(path: str | Path, part: str | int | None = None) -> str:
    identity = f"{Path(path).as_posix()}:{part if part is not None else ''}"
    return f"local:{hashlib.sha1(identity.encode('utf-8')).hexdigest()}"


def is_toc_page(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    leaders = sum(bool(re.search(r"(?:\.\s*){3,}\s*\d+\s*$", line)) for line in lines)
    return bool(lines) and leaders >= 3 and leaders / len(lines) >= 0.2


def parse_file(path: str | Path) -> list[dict]:
    from .csv import parse_csv
    from .docx import parse_docx
    from .html import parse_html
    from .json import parse_json
    from .markdown import parse_markdown
    from .pdf import parse_pdf
    from .text import parse_text
    from .xlsx import parse_xlsx

    parsers: dict[str, Callable[[str | Path], list[dict]]] = {
        ".pdf": parse_pdf, ".docx": parse_docx, ".html": parse_html, ".htm": parse_html,
        ".xlsx": parse_xlsx, ".csv": parse_csv, ".txt": parse_text, ".md": parse_markdown,
        ".markdown": parse_markdown, ".json": parse_json,
    }
    file_path = Path(path)
    parser = parsers.get(file_path.suffix.lower())
    if parser is None:
        raise ValueError(f"Unsupported file type: {file_path.suffix}")
    return parser(file_path)


def parse_directory(directory: str | Path) -> list[dict]:
    directory = Path(directory)
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")
    documents: list[dict] = []
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if "zakupki_kb" in relative.parts:
            continue
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            documents.extend(parse_file(path))
    return documents


SUPPORTED_SUFFIXES = frozenset({".pdf", ".docx", ".html", ".htm", ".xlsx", ".csv", ".txt", ".md", ".markdown", ".json"})
