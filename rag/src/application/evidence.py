from __future__ import annotations

import re


def _chunk_index(item: dict) -> int | None:
    value = (item.get("metadata") or {}).get("chunk_index")
    if value is None:
        match = re.search(r":(\d+)$", str(item.get("chunk_id", "")))
        value = match.group(1) if match else None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fingerprint(text: str) -> str:
    return " ".join(text.casefold().split())


def compact_evidence(candidates: list[dict], *, max_per_document: int = 2) -> list[dict]:
    """Remove exact duplicates and compact only clearly adjacent same-section chunks.

    Official evidence is placed before secondary historical tickets so an
    extractive answer cannot let a ticket override an available official source.
    """
    unique, seen_ids, seen_text = [], set(), set()
    per_document: dict[str, int] = {}
    for item in candidates:
        chunk_id = str(item.get("chunk_id", ""))
        fingerprint = _fingerprint(str(item.get("text", "")))
        if not chunk_id or chunk_id in seen_ids or not fingerprint or fingerprint in seen_text:
            continue
        document_id = str(item.get("document_id") or chunk_id)
        if per_document.get(document_id, 0) >= max_per_document:
            continue
        seen_ids.add(chunk_id)
        seen_text.add(fingerprint)
        per_document[document_id] = per_document.get(document_id, 0) + 1
        previous = unique[-1] if unique else None
        same_section = previous and previous.get("document_id") == document_id and previous.get("section") == item.get("section")
        previous_index, current_index = (_chunk_index(previous), _chunk_index(item)) if previous else (None, None)
        if same_section and previous_index is not None and current_index == previous_index + 1:
            previous["text"] = previous["text"].rstrip() + "\n\n" + item["text"].lstrip()
            previous["merged_chunk_ids"] = [*previous.get("merged_chunk_ids", [previous["chunk_id"]]), item["chunk_id"]]
            continue
        unique.append(dict(item))
    # Stable sort preserves retriever ranking within each authority tier. In
    # particular, BM25 and dense raw scores must never reorder one another.
    return sorted(unique, key=lambda item: item.get("authority") == "case_history")


def tagged_context(evidence: list[dict]) -> str:
    """Compact source-marked context for a future LLM generator."""
    blocks = []
    for item in evidence:
        label = "SUPPORT_TICKET" if item.get("authority") == "case_history" else "OFFICIAL"
        blocks.append(f"[{label}]\n{item.get('text', '')}")
    return "\n\n".join(blocks)
