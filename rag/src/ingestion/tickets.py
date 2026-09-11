from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def _normalized_key(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().casefold())


def _find_column(columns: list[str], *candidates: str) -> str | None:
    normalized = {_normalized_key(column): column for column in columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    for key, original in normalized.items():
        if any(key.startswith(candidate) for candidate in candidates):
            return original
    return None


def load_taxonomy(path: str | Path) -> list[dict[str, str | None]]:
    """Load the official topic/subtopic workbook without guessing missing labels."""
    import pandas as pd

    # The supplied official workbook has a title row above its actual headers.
    raw = pd.read_excel(path, header=None, dtype=str).fillna("")
    header_index = next((index for index, row in raw.iterrows()
                         if any(_normalized_key(value).startswith("тема") for value in row)
                         and any(_normalized_key(value).startswith("подтема") for value in row)), None)
    if header_index is None:
        frame = pd.read_excel(path, dtype=str).fillna("")
    else:
        frame = raw.iloc[header_index + 1:].copy()
        frame.columns = [str(value) for value in raw.iloc[header_index]]
    columns = [str(column) for column in frame.columns]
    topic_col = _find_column(columns, "тема", "topic")
    subtopic_col = _find_column(columns, "подтема", "подтема обращения", "subtopic")
    if topic_col is None and subtopic_col is None:
        raise ValueError("Taxonomy file must contain a topic or subtopic column")
    taxonomy: list[dict[str, str | None]] = []
    current_topic: str | None = None
    for _, row in frame.iterrows():
        topic = normalize_text(row.get(topic_col, "")) if topic_col else None
        subtopic = normalize_text(row.get(subtopic_col, "")) if subtopic_col else None
        if topic:
            current_topic = topic
        else:
            topic = current_topic
        if topic or subtopic:
            taxonomy.append({"topic": topic, "subtopic": subtopic})
    return taxonomy


def extract_question(description: Any) -> tuple[str | None, str | None]:
    """Extract 'Подтема запроса: label/question' while preserving unstructured text."""
    text = normalize_text(description)
    if not text:
        return None, None
    match = re.match(r"^подтема\s+запроса\s*:\s*(.*)$", text, flags=re.IGNORECASE)
    if not match:
        return None, text
    value = match.group(1).strip()
    if "/" not in value:
        return normalize_text(value), None
    subtopic, question = value.split("/", 1)
    return normalize_text(subtopic), normalize_text(question)


def _taxonomy_match(topic: str | None, subtopic: str | None, taxonomy: list[dict[str, str | None]]) -> bool:
    topic_key, subtopic_key = _normalized_key(topic), _normalized_key(subtopic)
    for item in taxonomy:
        same_topic = not topic_key or _normalized_key(item["topic"]) == topic_key
        same_subtopic = not subtopic_key or _normalized_key(item["subtopic"]) == subtopic_key
        if same_topic and same_subtopic:
            return True
    return False


LOW_QUALITY_SOLUTIONS = {
    "исправлено", "проблема устранена", "на момент проверки проблема отсутствует",
}


def preprocess_tickets(path: str | Path, taxonomy: list[dict[str, str | None]] | None = None) -> list[dict]:
    """Convert historical tickets into normalized, explicitly lower-authority records."""
    import pandas as pd

    frame = pd.read_excel(path, dtype=str).fillna("")
    columns = [str(column) for column in frame.columns]
    topic_col = _find_column(columns, "тема", "topic")
    description_col = _find_column(columns, "описание", "description")
    solution_col = _find_column(columns, "решение", "solution")
    status_col = _find_column(columns, "статус", "status")
    id_col = _find_column(columns, "id", "номер", "номер обращения")
    if description_col is None and solution_col is None:
        raise ValueError("Ticket export must contain description or solution column")

    result: list[dict] = []
    for row_index, (_, row) in enumerate(frame.iterrows(), start=1):
        topic = normalize_text(row.get(topic_col, "")) if topic_col else None
        embedded_subtopic, question = extract_question(row.get(description_col, "")) if description_col else (None, None)
        solution = normalize_text(row.get(solution_col, "")) if solution_col else None
        if not any((topic, embedded_subtopic, question, solution)):
            continue
        source_id = normalize_text(row.get(id_col, "")) if id_col else None
        recognized = _taxonomy_match(topic, embedded_subtopic, taxonomy or []) if taxonomy else None
        quality = "low" if _normalized_key(solution) in LOW_QUALITY_SOLUTIONS else "normal"
        result.append({
            "id": source_id or f"ticket-{row_index}", "topic": topic, "subtopic": embedded_subtopic,
            "question": question, "solution": solution,
            "status": normalize_text(row.get(status_col, "")) if status_col else None,
            "source": "support_ticket", "authority": "historical_ticket",
            "taxonomy_recognized": recognized, "answer_quality": quality,
        })
    return result


def tickets_to_chunks(tickets: list[dict]) -> list[dict]:
    """Turn useful ticket wording into retrievable examples, not primary authority."""
    chunks: list[dict] = []
    for ticket in tickets:
        pieces = [value for value in (ticket.get("question"), ticket.get("solution")) if value]
        if not pieces:
            continue
        chunks.append({
            "chunk_id": f"ticket:{ticket['id']}", "text": "\n".join(pieces), "source": "support_ticket",
            "page": None, "page_start": None, "page_end": None, "section": ticket.get("subtopic"),
            "authority": "historical_ticket", "document_type": "ticket", "topic": ticket.get("topic"),
            "subtopic": ticket.get("subtopic"), "answer_quality": ticket.get("answer_quality", "normal"),
        })
    return chunks
