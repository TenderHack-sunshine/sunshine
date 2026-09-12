from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.core.config import Settings
from src.retrieval.embeddings.persistent_worker import PersistentEmbeddingServer, PersistentQwenEmbeddingClient


def main() -> None:
    settings = Settings()
    parser = argparse.ArgumentParser(description="Persistent local Qwen3 query-embedding worker.")
    parser.add_argument("--host", default=settings.dense_worker_host)
    parser.add_argument("--port", type=int, default=settings.dense_worker_port)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.status:
        try:
            print(json.dumps(PersistentQwenEmbeddingClient(args.host, args.port).status(), ensure_ascii=False))
        except Exception as error:
            print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
            raise SystemExit(1)
        return
    server = PersistentEmbeddingServer((args.host, args.port), str(settings.embedding_model_path))
    print(json.dumps({"status": "ready", "host": args.host, "port": args.port, "model_load_ms": server.model_load_ms,
                      "warmup_ms": server.warmup_ms, "dimension": server.dimension}, ensure_ascii=False), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
