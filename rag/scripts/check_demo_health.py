"""Small pre-demo dependency check; it does not start, stop, or index services."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.config import Settings
from src.generation.qwen import QwenGenerationClient
from src.retrieval.embeddings.persistent_worker import PersistentQwenEmbeddingClient
from src.retrieval.vector_store import HttpQdrantStore
from src.safety.profanity import build_profanity_detector


def check(name: str, callable_) -> dict:
    try:
        detail = callable_()
        return {"name": name, "ok": True, "detail": detail}
    except Exception as error:
        return {"name": name, "ok": False, "detail": str(error)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Check local Tender Hack demo dependencies before presenting.")
    parser.add_argument("--profanity-backend", choices=("rule", "deterministic"), help="Explicit backend override for this check.")
    parser.add_argument("--load-profanity", action="store_true", help="Run deterministic profanity smoke cases.")
    parser.add_argument("--docker", action="store_true", help="Also validate the running Docker RAG service and its non-secret runtime diagnostics.")
    args = parser.parse_args()
    settings = Settings(**({"profanity_backend": args.profanity_backend} if args.profanity_backend else {}))
    canonical = settings.processed_dir / "index" / "all_chunks.jsonl"
    bm25 = settings.data_dir / "indexes" / "support_tickets_bm25.pkl"

    def profanity():
        if args.load_profanity:
            detector = build_profanity_detector(settings.profanity_backend)
            if not detector.detect("\u044d\u0442\u043e \u0445\u0443\u0439\u043d\u044f").detected or detector.detect("\u043a\u0430\u043a \u0434\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u043c\u0447\u0434").detected:
                raise RuntimeError("deterministic profanity smoke cases failed")
            return "deterministic lexicon and regex smoke cases passed"
        return "deterministic rule backend (use --load-profanity for smoke cases)"

    def worker():
        response = PersistentQwenEmbeddingClient(settings.dense_worker_host, settings.dense_worker_port).status()
        return {key: response.get(key) for key in ("dimension", "device", "dtype")}

    def qdrant():
        store = HttpQdrantStore(settings.qdrant_host, settings.qdrant_port, settings.qdrant_official_collection)
        if not store.collection_exists():
            raise RuntimeError(f"collection missing: {settings.qdrant_official_collection}")
        count = store.count()
        if count != settings.official_expected_points:
            raise RuntimeError(f"expected {settings.official_expected_points} official points, found {count}")
        return {"collection": settings.qdrant_official_collection, "points": count}

    def generation():
        if settings.generator_backend != "qwen":
            return {"backend": "extractive", "note": "Qwen generation not selected"}
        client = QwenGenerationClient(settings.generation_worker_host, settings.generation_worker_port,
                                      settings.generation_timeout_seconds)
        status = client.status()
        smoke = client.generate("Контекст: Максимальный срок действия оферты — 3 месяца.\n"
                                "Вопрос: Какой максимальный срок действия оферты?", 32)
        if "3" not in smoke.text or "месяц" not in smoke.text.casefold():
            raise RuntimeError("generation smoke answer did not preserve the supported term")
        return {"model": status.get("model"), "device": status.get("device"),
                "model_load_ms": status.get("model_load_ms"), "smoke_generation": "OK", "latency_ms": smoke.latency_ms}

    checks = [
        check("config", lambda: {"retrieval_strategy": settings.retrieval_strategy, "reranker_enabled": settings.rerank_enabled,
                                   "confidence_min_official_score": settings.confidence_min_official_score,
                                   "clarification_policy_enabled": settings.clarification_policy_enabled}),
        check("profanity", profanity), check("canonical_chunks", lambda: str(canonical) if canonical.is_file() else (_ for _ in ()).throw(FileNotFoundError(canonical))),
        check("ticket_bm25", lambda: str(bm25) if bm25.is_file() else (_ for _ in ()).throw(FileNotFoundError(bm25))),
        check("embedding_worker", worker), check("qdrant", qdrant), check("qwen_generation_worker", generation),
    ]
    if args.docker:
        compose_root = ROOT.parent

        def docker_health():
            command = ["docker", "compose", "-f", str(compose_root / "docker-compose.yml"), "exec", "-T", "rag", "python", "-c",
                       "import json,urllib.request; print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3))))"]
            response = subprocess.run(command, cwd=compose_root, capture_output=True, text=True, timeout=15)
            if response.returncode:
                raise RuntimeError(response.stderr.strip() or "RAG container is not running")
            payload = json.loads(response.stdout)
            runtime = payload.get("runtime", {})
            if payload.get("status") != "ok":
                raise RuntimeError("RAG health endpoint did not return ok")
            required = ("evidence_sufficiency_enabled", "clarification_policy_enabled", "bm25_loaded", "generator_available")
            failed = [name for name in required if not runtime.get(name)]
            if failed:
                raise RuntimeError("runtime safety/dependency checks failed: " + ", ".join(failed))
            return runtime

        checks.append(check("docker_rag_runtime", docker_health))
    payload = {"ready": all(item["ok"] for item in checks), "checks": checks}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0 if payload["ready"] else 1)


if __name__ == "__main__":
    main()
