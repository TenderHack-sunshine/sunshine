from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from pathlib import Path
import pickle
from time import perf_counter
from typing import Iterable


def tokenize(text: str) -> list[str]:
    return [_stem(token) for token in re.findall(r"[\w-]+", text.casefold().replace("ё", "е"), flags=re.UNICODE) if token]


_RUSSIAN_SUFFIXES = (
    "иями", "ями", "ами", "ого", "ему", "ыми", "ими", "иях", "иях", "ать", "ять", "ить", "ешь", "ете",
    "ов", "ев", "ам", "ям", "ах", "ях", "ой", "ей", "ий", "ый", "ая", "яя", "ое", "ее", "ом", "ем",
    "ую", "юю", "ия", "ие", "иям", "ием", "ия", "ия", "а", "ы", "и", "я", "е", "о", "у", "ю",
)


def _stem(token: str) -> str:
    """Small deterministic Russian suffix normalizer; no external morphology service."""
    if len(token) < 5 or not re.search(r"[а-я]", token):
        return token
    for suffix in _RUSSIAN_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[:-len(suffix)]
    return token


class BM25Index:
    """Small dependency-free BM25 index, sufficient for the hackathon corpus."""

    def __init__(self, documents: list[dict] | None = None, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.documents: list[dict] = []
        self.term_frequencies: list[Counter[str]] = []
        self.document_frequencies: Counter[str] = Counter()
        self.average_length = 0.0
        if documents:
            self.build(documents)

    def build(self, documents: list[dict]) -> None:
        self.documents = list(documents)
        self.term_frequencies = [Counter(tokenize(document.get("text", ""))) for document in self.documents]
        self.document_frequencies = Counter(term for frequencies in self.term_frequencies for term in frequencies)
        self.average_length = sum(sum(f.values()) for f in self.term_frequencies) / max(len(self.documents), 1)

    def score(self, query: str) -> list[float]:
        query_terms = tokenize(query)
        total = len(self.documents)
        scores: list[float] = []
        for frequencies in self.term_frequencies:
            length = sum(frequencies.values())
            score = 0.0
            for term in query_terms:
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                idf = math.log(1 + (total - self.document_frequencies[term] + 0.5) / (self.document_frequencies[term] + 0.5))
                denominator = frequency + self.k1 * (1 - self.b + self.b * length / max(self.average_length, 1))
                score += idf * (frequency * (self.k1 + 1)) / denominator
            scores.append(score)
        return scores

    def search(self, query: str, top_k: int = 20) -> list[dict]:
        ranked = sorted(enumerate(self.score(query)), key=lambda item: item[1], reverse=True)[:top_k]
        return [{**self.documents[index], "score": score} for index, score in ranked if score > 0]


class RussianBM25Retriever:
    """Inverted-index BM25 for local Russian support-ticket retrieval."""

    def __init__(self, documents: Iterable[dict] | None = None, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.documents: list[dict] = []
        self.postings: dict[str, dict[int, int]] = {}
        self.document_lengths: list[int] = []
        self.average_length = 0.0
        if documents is not None:
            self.build(documents)

    @staticmethod
    def _index_text(document: dict) -> str:
        metadata = document.get("metadata") or {}
        labels = " ".join(str(value) for value in (metadata.get("topic"), metadata.get("subtopic")) if value)
        return f"{labels}\n{document.get('text', '')}"

    def build(self, documents: Iterable[dict]) -> float:
        started = perf_counter()
        self.documents = [dict(document) for document in documents]
        postings: defaultdict[str, dict[int, int]] = defaultdict(dict)
        self.document_lengths = []
        for index, document in enumerate(self.documents):
            frequencies = Counter(tokenize(self._index_text(document)))
            self.document_lengths.append(sum(frequencies.values()))
            for term, frequency in frequencies.items():
                postings[term][index] = frequency
        self.postings = dict(postings)
        self.average_length = sum(self.document_lengths) / max(len(self.document_lengths), 1)
        return perf_counter() - started

    def _score(self, query: str) -> dict[int, float]:
        terms = tokenize(query)
        total = len(self.documents)
        scores: defaultdict[int, float] = defaultdict(float)
        for term in terms:
            posting = self.postings.get(term)
            if not posting:
                continue
            document_frequency = len(posting)
            idf = math.log(1 + (total - document_frequency + .5) / (document_frequency + .5))
            for index, frequency in posting.items():
                length = self.document_lengths[index]
                denominator = frequency + self.k1 * (1 - self.b + self.b * length / max(self.average_length, 1))
                scores[index] += idf * frequency * (self.k1 + 1) / denominator
        return dict(scores)

    def search(self, query: str, top_k: int = 20, filters: dict[str, str | list[str]] | None = None) -> list[dict]:
        ranked = sorted(self._score(query).items(), key=lambda item: item[1], reverse=True)
        results = []
        for rank, (index, score) in enumerate(ranked, start=1):
            document = self.documents[index]
            if filters and any(
                document.get(field) not in (value if isinstance(value, list) else [value]) for field, value in filters.items()
            ):
                continue
            results.append({
                "chunk_id": document.get("chunk_id"), "document_id": document.get("document_id"), "text": document.get("text", ""),
                "source_type": document.get("source_type"), "authority": document.get("authority"),
                "score": float(score), "raw_score": float(score), "rank": rank, "retrieval_method": "bm25",
                "metadata": dict(document.get("metadata") or {}),
                "source_path": document.get("source_path"), "title": document.get("title"), "section": document.get("section"),
                "page_start": document.get("page_start"), "page_end": document.get("page_end"),
            })
            if len(results) >= top_k:
                break
        return results

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as file:
            pickle.dump(self, file, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path: str | Path) -> "RussianBM25Retriever":
        with Path(path).open("rb") as file:
            value = pickle.load(file)
        if not isinstance(value, cls):
            raise ValueError(f"Unexpected BM25 index type in {path}")
        return value

    @property
    def approximate_size_bytes(self) -> int:
        return sum(len(term.encode("utf-8")) + len(posting) * 12 for term, posting in self.postings.items())
