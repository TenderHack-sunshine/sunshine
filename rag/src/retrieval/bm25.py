from __future__ import annotations

import math
import re
from collections import Counter


def tokenize(text: str) -> list[str]:
    return re.findall(r"[\w-]+", text.casefold(), flags=re.UNICODE)


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
