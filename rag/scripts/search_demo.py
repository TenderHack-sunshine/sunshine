from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import Settings
from src.generation.generator import EvidenceGenerator
from src.ingestion.tickets import load_taxonomy
from src.ingestion.tickets import tickets_to_chunks
from src.main import answer_question
from src.retrieval.search import build_retriever
from src.routing.classifier import TaxonomyRouter


def main() -> None:
    settings = Settings()
    chunks_file = settings.processed_dir / "manual_chunks.jsonl"
    if not chunks_file.exists():
        raise SystemExit("Run: python scripts/ingest_documents.py")
    chunks = [json.loads(line) for line in chunks_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    tickets_file = settings.processed_dir / "tickets.jsonl"
    if tickets_file.exists():
        tickets = [json.loads(line) for line in tickets_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        chunks.extend(tickets_to_chunks(tickets))
    retriever = build_retriever(chunks, settings, use_dense=settings.use_qdrant)
    taxonomy_files = sorted(settings.tickets_dir.glob("*темы*.*")) + sorted(settings.tickets_dir.glob("*Темы*.*"))
    router = TaxonomyRouter(load_taxonomy(taxonomy_files[0])) if taxonomy_files else None
    generator = EvidenceGenerator(settings.min_evidence_score)
    while True:
        question = input("\nEnter question (or 'exit'): ").strip()
        if question.casefold() in {"exit", "quit", "выход"}:
            return
        result = answer_question(question, retriever, router, generator)
        print("Detected topic/subtopic:", result["route"])
        print("Top evidence:")
        for index, evidence in enumerate(result["evidence"], start=1):
            print(f"{index}. {evidence['source']} | page={evidence['page']} | score={evidence['score']:.4f}")
            print(evidence["text"][:700])
        print("Final answer:", result["answer"])


if __name__ == "__main__":
    main()
