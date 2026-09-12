"""Run a real local RAG abstention and print its structured knowledge-gap signal."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.application.factory import build_rag_service
from src.core.config import Settings


def main() -> None:
    result = build_rag_service(Settings()).ask("неизвестная функция портала")
    print(json.dumps({"status": result["status"], "knowledge_gap": result["diagnostics"].get("knowledge_gap")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
