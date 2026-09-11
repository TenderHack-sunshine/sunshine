from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Callable, Iterable
from typing import Any


def approximate_token_count(text: str) -> int:
    """Offline token estimate used when a local tokenizer is unavailable."""
    return len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE))


def _is_heading(text: str) -> bool:
    short = len(text) <= 140
    numbered = bool(re.match(r"^(?:\d+(?:\.\d+)*[.)]?|[IVXLC]+[.)])\s+", text, flags=re.I))
    caps = text.isupper() and len(text.split()) <= 12
    return short and (numbered or caps or text.endswith(":"))


def _is_list_item(text: str) -> bool:
    return bool(re.match(r"^(?:[-•*]|\d+[.)])\s+", text))


def _page_paragraphs(text: str) -> list[str]:
    """Merge PDF line wraps while retaining headings and list items as boundaries."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if _is_heading(line) or _is_list_item(line):
            if current:
                paragraphs.append(" ".join(current))
                current = []
            paragraphs.append(line)
            continue
        current.append(line)
        if re.search(r"[.!?;:]$", line):
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return paragraphs


def _split_large_text(text: str, limit: int, count_tokens: Callable[[str], int]) -> list[str]:
    """Prefer sentence boundaries; words are an absolute last-resort constraint."""
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()] or [text]
    parts: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        candidate = " ".join(current + [sentence])
        if current and count_tokens(candidate) > limit:
            parts.append(" ".join(current))
            current = [sentence]
        else:
            current.append(sentence)
    if current:
        parts.append(" ".join(current))
    constrained: list[str] = []
    for part in parts:
        if count_tokens(part) <= limit:
            constrained.append(part)
            continue
        words, word_part = part.split(), []
        for word in words:
            candidate = " ".join(word_part + [word])
            if word_part and count_tokens(candidate) > limit:
                constrained.append(" ".join(word_part))
                word_part = [word]
            else:
                word_part.append(word)
        if word_part:
            constrained.append(" ".join(word_part))
    return constrained


def group_page_documents(documents: list[dict]) -> list[dict]:
    """Turn page-level parser output into logical documents without losing page IDs."""
    grouped: dict[tuple[str, str], dict] = {}
    for document in documents:
        source = document.get("source", "unknown")
        key = (source, document.get("document_type", document.get("source_type", "manual")))
        item = grouped.setdefault(key, {"source": source, "pages": [], "document_type": key[1], "authority": document.get("authority", "manual")})
        if "pages" in document:
            item["pages"].extend(document["pages"])
        else:
            item["pages"].append({"page": document.get("page"), "text": document.get("text", "")})
    for item in grouped.values():
        item["pages"].sort(key=lambda page: page.get("page") if page.get("page") is not None else -1)
    return list(grouped.values())


def extract_atomic_units(document: dict, max_tokens: int = 500, token_counter: Callable[[str], int] = approximate_token_count) -> list[dict]:
    """Create paragraph/sentence units and carry section state across every page."""
    pages = document.get("pages") or [{"page": document.get("page"), "text": document.get("text", "")}]
    section = document.get("section")
    units: list[dict] = []
    for page in pages:
        for paragraph in _page_paragraphs(page.get("text", "")):
            heading = _is_heading(paragraph)
            if heading:
                section = paragraph.rstrip(":")
            for text in _split_large_text(paragraph, max_tokens, token_counter):
                units.append({"text": text, "page": page.get("page"), "section": section, "is_heading": heading})
    return units


def _cosine(left: Iterable[float], right: Iterable[float]) -> float:
    left_values, right_values = list(left), list(right)
    denominator = math.sqrt(sum(value * value for value in left_values)) * math.sqrt(sum(value * value for value in right_values))
    return sum(a * b for a, b in zip(left_values, right_values)) / denominator if denominator else 0.0


def compute_semantic_distances(embeddings: Iterable[Iterable[float]]) -> list[float]:
    vectors = list(embeddings)
    return [1.0 - _cosine(vectors[index], vectors[index + 1]) for index in range(len(vectors) - 1)]


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return float("inf")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile / 100
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] if lower == upper else ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def detect_breakpoints(units: list[dict], distances: list[float], percentile: float = 85.0) -> dict[int, float]:
    """Return indexes that begin new chunks. Heading starts are strong boundaries."""
    if not 0 <= percentile <= 100:
        raise ValueError("breakpoint percentile must be in [0, 100]")
    threshold = _percentile(distances, percentile)
    has_semantic_variation = bool(distances) and max(distances) > min(distances)
    breaks: dict[int, float] = {}
    for index in range(1, len(units)):
        if units[index]["is_heading"]:
            breaks[index] = 1.0
        elif (has_semantic_variation and not units[index - 1]["is_heading"]
              and distances[index - 1] >= threshold):
            breaks[index] = distances[index - 1]
    return breaks


def _overlap_units(units: list[dict], token_limit: int, token_counter: Callable[[str], int]) -> list[dict]:
    if token_limit <= 0:
        return []
    selected: list[dict] = []
    for unit in reversed(units):
        candidate = [unit] + selected
        if selected and token_counter("\n".join(item["text"] for item in candidate)) > token_limit:
            break
        selected = candidate
    return selected


def _chunk_payload(units: list[dict], document: dict, chunk_index: int, strategy: str, token_counter: Callable[[str], int], break_score: float | None = None) -> dict:
    text = "\n".join(unit["text"] for unit in units)
    pages = [unit["page"] for unit in units if unit.get("page") is not None]
    page_start, page_end = (min(pages), max(pages)) if pages else (None, None)
    identity = f"{document.get('source', '')}:{page_start}:{page_end}:{chunk_index}:{text}"
    return {
        "chunk_id": hashlib.sha1(identity.encode("utf-8")).hexdigest(), "text": text, "source": document.get("source"),
        "page_start": page_start, "page_end": page_end, "page": page_start, "section": units[0].get("section") if units else None,
        "chunk_index": chunk_index, "token_count": token_counter(text), "authority": document.get("authority", "manual"),
        "document_type": document.get("document_type", "manual"), "chunking_strategy": strategy,
        "unit_count": len(units), "semantic_break_score": break_score,
    }


def build_semantic_chunks(units: list[dict], document: dict, breakpoints: dict[int, float], min_tokens: int = 100,
                          target_tokens: int = 300, max_tokens: int = 500, forced_split_overlap_tokens: int = 50,
                          token_counter: Callable[[str], int] = approximate_token_count) -> list[dict]:
    """Build chunks on semantic boundaries, using size only as a safety constraint."""
    if not (0 < min_tokens <= target_tokens <= max_tokens):
        raise ValueError("Expected min_tokens <= target_tokens <= max_tokens")
    chunks: list[dict] = []
    current: list[dict] = []
    current_break_score: float | None = None

    def emit(force_small: bool = False, strategy: str = "semantic") -> None:
        if not current:
            return
        token_count = token_counter("\n".join(unit["text"] for unit in current))
        if token_count >= min_tokens or force_small:
            chunks.append(_chunk_payload(current, document, len(chunks), strategy, token_counter, current_break_score))

    for index, unit in enumerate(units):
        boundary_score = breakpoints.get(index)
        if current and boundary_score is not None:
            # A heading must not relabel preceding content; other breaks wait for a viable chunk.
            before_size = token_counter("\n".join(item["text"] for item in current))
            if unit["is_heading"] or before_size >= min_tokens:
                emit(force_small=unit["is_heading"])
                current = []
                current_break_score = boundary_score
        candidate = current + [unit]
        if current and token_counter("\n".join(item["text"] for item in candidate)) > max_tokens:
            emit(force_small=True, strategy="semantic_forced_split")
            current = _overlap_units(current, forced_split_overlap_tokens, token_counter)
            current_break_score = None
        current.append(unit)
    emit(force_small=True)
    return chunks


def chunk_semantic_document(document: dict, embedder: Any, breakpoint_percentile: float = 85.0, min_tokens: int = 100,
                            target_tokens: int = 300, max_tokens: int = 500, forced_split_overlap_tokens: int = 50,
                            token_counter: Callable[[str], int] | None = None) -> list[dict]:
    counter = token_counter or getattr(embedder, "count_tokens", approximate_token_count)
    units = extract_atomic_units(document, max_tokens=max_tokens, token_counter=counter)
    if not units:
        return []
    distances = compute_semantic_distances(embedder.embed_documents([unit["text"] for unit in units]))
    breaks = detect_breakpoints(units, distances, breakpoint_percentile)
    return build_semantic_chunks(units, document, breaks, min_tokens, target_tokens, max_tokens, forced_split_overlap_tokens, counter)


def chunk_document(document: dict, chunk_size: int = 512, overlap_paragraphs: int = 1,
                   min_chunk_tokens: int = 20, token_counter: Callable[[str], int] = approximate_token_count) -> list[dict]:
    """Legacy recursive, page-local chunking retained as an explicit fallback."""
    pages = document.get("pages") or [{"page": document.get("page"), "text": document.get("text", "")}]
    chunks: list[dict] = []
    for page in pages:
        page_document = {key: value for key, value in document.items() if key != "pages"}
        page_document.update({"page": page.get("page"), "text": page.get("text", "")})
        units = extract_atomic_units(page_document, max_tokens=chunk_size, token_counter=token_counter)
        current: list[dict] = []
        for unit in units:
            if current and token_counter("\n".join(item["text"] for item in current + [unit])) > chunk_size:
                if token_counter("\n".join(item["text"] for item in current)) >= min_chunk_tokens:
                    chunks.append(_chunk_payload(current, page_document, len(chunks), "recursive", token_counter))
                current = current[-overlap_paragraphs:] if overlap_paragraphs else []
            current.append(unit)
        if current and token_counter("\n".join(item["text"] for item in current)) >= min_chunk_tokens:
            chunks.append(_chunk_payload(current, page_document, len(chunks), "recursive", token_counter))
    return chunks


def chunk_documents(documents: list[dict], strategy: str = "semantic", embedder: Any | None = None, **kwargs: object) -> list[dict]:
    if strategy not in {"semantic", "recursive"}:
        raise ValueError("strategy must be 'semantic' or 'recursive'")
    if strategy == "recursive":
        return [chunk for document in documents for chunk in chunk_document(document, **kwargs)]
    if embedder is None:
        raise RuntimeError("Semantic chunking needs a local embedder; use strategy='recursive' for explicit fallback")
    return [chunk for document in group_page_documents(documents) for chunk in chunk_semantic_document(document, embedder, **kwargs)]
