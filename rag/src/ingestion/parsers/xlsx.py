from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from time import perf_counter

from .base import clean_text
from ..tickets import extract_question


def _add_timing(profile: dict[str, float] | None, name: str, started: float) -> None:
    if profile is not None:
        profile[name] = profile.get(name, 0.0) + perf_counter() - started


def _merged_cells_by_row(worksheet) -> dict[int, list[tuple[int, int, object]]]:
    """Index merged-cell values once instead of scanning all merged ranges per cell."""
    values_by_row: dict[int, list[tuple[int, int, object]]] = {}
    for merged in worksheet.merged_cells.ranges:
        value = worksheet.cell(merged.min_row, merged.min_col).value
        for row in range(merged.min_row, merged.max_row + 1):
            values_by_row.setdefault(row, []).append((merged.min_col, merged.max_col, value))
    return values_by_row


def _normalize_values(row_number: int, values: tuple[object, ...], merged_by_row: dict[int, list[tuple[int, int, object]]]) -> list[str]:
    merged_values = merged_by_row.get(row_number, [])
    normalized: list[str] = []
    for column, value in enumerate(values, start=1):
        if value is None:
            for start, end, merged_value in merged_values:
                if start <= column <= end:
                    value = merged_value
                    break
        normalized.append(clean_text(str(value)) if value is not None else "")
    return normalized


def parse_xlsx(
    path: str | Path,
    *,
    row_limit: int | None = None,
    profile: dict[str, float] | None = None,
    progress_callback: Callable[[int, int, Path], None] | None = None,
    progress_every: int = 1000,
) -> list[dict]:
    """Emit one retrieval-friendly record per meaningful spreadsheet row.

    The worksheet is traversed once. The initial non-empty rows are buffered only
    to identify a header, avoiding all-sheet materialization on ticket exports.
    """
    from openpyxl import load_workbook

    path = Path(path)
    is_ticket_export = path.name.casefold() == "выгрузка стп за 2026.xlsx"
    is_taxonomy = path.name.casefold() == "темы_подтемы_обращений.xlsx"
    started = perf_counter()
    workbook = load_workbook(path, read_only=False, data_only=True)
    _add_timing(profile, "xlsx_read_seconds", started)
    documents: list[dict] = []
    emitted_ticket_rows = 0
    try:
        for worksheet in workbook.worksheets:
            merged_by_row = _merged_cells_by_row(worksheet)
            row_iterator = enumerate(worksheet.iter_rows(values_only=True), start=1)
            initial_rows: list[tuple[int, list[str]]] = []
            for row_number, raw_values in row_iterator:
                row_started = perf_counter()
                values = _normalize_values(row_number, raw_values, merged_by_row)
                _add_timing(profile, "xlsx_row_read_seconds", row_started)
                if any(values):
                    initial_rows.append((row_number, values))
                    if len(initial_rows) == 10:
                        break
            if len(initial_rows) < 2:
                continue

            header_position = max(
                range(len(initial_rows)),
                key=lambda index: (
                    len({value for value in initial_rows[index][1] if value}),
                    sum(bool(value) for value in initial_rows[index][1]),
                ),
            )
            header_row, headers = initial_rows[header_position]
            headers = [header.rstrip(":") or f"Column {index + 1}" for index, header in enumerate(headers)]
            header_map = {header.casefold(): index for index, header in enumerate(headers)}
            current_topic = ""
            topic_index = next((index for key, index in header_map.items() if key.startswith("тема")), None)
            subtopic_index = next((index for key, index in header_map.items() if key.startswith("подтема")), None)

            def process_row(row_number: int, values: list[str]) -> bool:
                nonlocal current_topic, emitted_ticket_rows
                if is_ticket_export and row_limit is not None and emitted_ticket_rows >= row_limit:
                    return False
                normalized_started = perf_counter()
                if is_ticket_export:
                    def column(name: str) -> str:
                        index = header_map.get(name)
                        return values[index] if index is not None and index < len(values) else ""

                    description = column("описание")
                    subtopic, question = extract_question(description)
                    topic = column("тема")
                    solution = column("решение")
                    text = "\n".join(part for part in (
                        f"Тема: {topic}" if topic else "",
                        f"Подтема: {subtopic}" if subtopic else "",
                        f"Проблема: {question or description}" if (question or description) else "",
                        f"Решение: {solution}" if solution else "",
                    ) if part)
                    if text:
                        documents.append({
                            "text": text, "source": path.name, "page": None, "sheet": worksheet.title, "row": row_number,
                            "document_type": "support_ticket", "source_type": "support_ticket", "authority": "case_history",
                            "influence": column("влияние") or None, "topic": topic or None, "subtopic": subtopic,
                            "status": column("статус") or None, "description": description or None, "solution": solution or None,
                        })
                        emitted_ticket_rows += 1
                        if progress_callback and emitted_ticket_rows % progress_every == 0:
                            progress_callback(emitted_ticket_rows, max(0, worksheet.max_row - header_row), path)
                    _add_timing(profile, "row_normalization_seconds", normalized_started)
                    return True

                if is_taxonomy:
                    topic = values[topic_index] if topic_index is not None and topic_index < len(values) else ""
                    subtopic = values[subtopic_index] if subtopic_index is not None and subtopic_index < len(values) else ""
                    current_topic = topic or current_topic
                    text = "\n".join(part for part in (
                        f"Тема обращений: {current_topic}" if current_topic else "",
                        f"Подтема обращений: {subtopic}" if subtopic else "",
                    ) if part)
                    if text:
                        documents.append({
                            "text": text, "source": path.name, "page": None, "sheet": worksheet.title, "row": row_number,
                            "document_type": "support_taxonomy", "source_type": "support_taxonomy", "authority": "taxonomy",
                            "topic": current_topic or None, "subtopic": subtopic or None,
                        })
                    _add_timing(profile, "row_normalization_seconds", normalized_started)
                    return True

                fields = [f"{headers[index]}: {value}" for index, value in enumerate(values) if value]
                if fields:
                    documents.append({
                        "text": f"Sheet: {worksheet.title}\nColumns: {' | '.join(headers)}\n" + "\n".join(fields),
                        "source": path.name, "page": None, "sheet": worksheet.title, "row": row_number,
                        "document_type": "table_row", "source_type": "xlsx", "authority": "manual",
                    })
                _add_timing(profile, "row_normalization_seconds", normalized_started)
                return True

            for row_number, values in initial_rows[header_position + 1:]:
                if not process_row(row_number, values):
                    break
            else:
                for row_number, raw_values in row_iterator:
                    row_started = perf_counter()
                    values = _normalize_values(row_number, raw_values, merged_by_row)
                    _add_timing(profile, "xlsx_row_read_seconds", row_started)
                    if not any(values):
                        continue
                    if not process_row(row_number, values):
                        break
    finally:
        workbook.close()
    return documents
