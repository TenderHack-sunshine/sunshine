from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _path_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    return Path(value).expanduser() if value else default


@dataclass(frozen=True)
class Settings:
    """Central, local-only configuration for the MVP."""

    root_dir: Path = Path(__file__).resolve().parents[2]
    data_dir: Path | None = None
    model_dir: Path | None = None
    qdrant_host: str = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port: int = int(os.getenv("QDRANT_PORT", "6333"))
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "zakupki_knowledge")
    qdrant_official_collection: str = os.getenv("QDRANT_OFFICIAL_COLLECTION", "zakupki_official")
    dense_query_timeout_seconds: float = float(os.getenv("DENSE_QUERY_TIMEOUT_SECONDS", "12"))
    dense_worker_host: str = os.getenv("DENSE_WORKER_HOST", "127.0.0.1")
    dense_worker_port: int = int(os.getenv("DENSE_WORKER_PORT", "8765"))
    official_expected_points: int = int(os.getenv("OFFICIAL_EXPECTED_POINTS", "1073"))
    rerank_enabled: bool = os.getenv("RERANKER_ENABLED", os.getenv("RERANK_ENABLED", "0")).lower() in {"1", "true", "yes"}
    hybrid_rerank_top_n: int = int(os.getenv("HYBRID_RERANK_TOP_N", "20"))
    evidence_max_per_document: int = int(os.getenv("EVIDENCE_MAX_PER_DOCUMENT", "2"))
    confidence_min_sources: int = int(os.getenv("CONFIDENCE_MIN_SOURCES", "1"))
    confidence_min_official_score: float = float(os.getenv("CONFIDENCE_MIN_OFFICIAL_SCORE", "0.0"))
    confidence_min_agreement: float = float(os.getenv("CONFIDENCE_MIN_AGREEMENT", "0.0"))
    use_qdrant: bool = os.getenv("USE_QDRANT", "1").lower() not in {"0", "false", "no"}
    bm25_top_k: int = int(os.getenv("BM25_TOP_K", "20"))
    dense_top_k: int = int(os.getenv("DENSE_TOP_K", "20"))
    fusion_top_k: int = int(os.getenv("FUSION_TOP_K", "20"))
    final_top_k: int = int(os.getenv("FINAL_TOP_K", "5"))
    retrieval_strategy: str = os.getenv("RETRIEVAL_STRATEGY", "dense_primary").strip().lower()
    dense_primary_min_score: float = float(os.getenv("DENSE_PRIMARY_MIN_SCORE", "0.55"))
    dense_primary_min_agreement: float = float(os.getenv("DENSE_PRIMARY_MIN_AGREEMENT", "0.0"))
    dense_primary_keep_top_k: int = int(os.getenv("DENSE_PRIMARY_KEEP_TOP_K", "3"))
    bm25_rescue_top_k: int = int(os.getenv("BM25_RESCUE_TOP_K", "3"))
    rrf_k: int = int(os.getenv("RRF_K", "60"))
    dense_fusion_weight: float = float(os.getenv("DENSE_FUSION_WEIGHT", "1.0"))
    bm25_fusion_weight: float = float(os.getenv("BM25_FUSION_WEIGHT", "1.0"))
    official_rrf_weight: float = float(os.getenv("OFFICIAL_RRF_WEIGHT", "1.0"))
    ticket_rrf_weight: float = float(os.getenv("TICKET_RRF_WEIGHT", "1.0"))
    min_evidence_score: float = float(os.getenv("MIN_EVIDENCE_SCORE", "0.02"))
    semantic_chunking_enabled: bool = os.getenv("SEMANTIC_CHUNKING_ENABLED", "1").lower() not in {"0", "false", "no"}
    semantic_breakpoint_percentile: float = float(os.getenv("SEMANTIC_BREAKPOINT_PERCENTILE", "85"))
    min_chunk_tokens: int = int(os.getenv("MIN_CHUNK_TOKENS", "100"))
    target_chunk_tokens: int = int(os.getenv("TARGET_CHUNK_TOKENS", "300"))
    max_chunk_tokens: int = int(os.getenv("MAX_CHUNK_TOKENS", "500"))
    forced_split_overlap_tokens: int = int(os.getenv("FORCED_SPLIT_OVERLAP_TOKENS", "50"))
    zakupki_kb_api_url: str | None = os.getenv("ZAKUPKI_KB_API_URL")
    zakupki_kb_base_url: str = os.getenv("ZAKUPKI_KB_BASE_URL", "https://zakupki.mos.ru")
    zakupki_kb_section_types: tuple[str, ...] = tuple(
        item.strip() for item in os.getenv("ZAKUPKI_KB_SECTION_TYPES", "supplier").split(",") if item.strip()
    )
    zakupki_kb_timeout_seconds: float = float(os.getenv("ZAKUPKI_KB_TIMEOUT_SECONDS", "20"))
    zakupki_kb_max_retries: int = int(os.getenv("ZAKUPKI_KB_MAX_RETRIES", "3"))
    zakupki_kb_max_chunk_tokens: int = int(os.getenv("ZAKUPKI_KB_MAX_CHUNK_TOKENS", "700"))

    def __post_init__(self) -> None:
        if self.rrf_k <= 0:
            raise ValueError("RRF_K must be a positive integer")
        if self.dense_fusion_weight < 0 or self.bm25_fusion_weight < 0:
            raise ValueError("DENSE_FUSION_WEIGHT and BM25_FUSION_WEIGHT must be non-negative")
        if self.dense_fusion_weight == 0 and self.bm25_fusion_weight == 0:
            raise ValueError("At least one fusion weight must be positive")
        if self.retrieval_strategy not in {"dense_primary", "hybrid_rrf", "bm25_only"}:
            raise ValueError("RETRIEVAL_STRATEGY must be dense_primary, hybrid_rrf, or bm25_only")
        if self.dense_primary_min_score < 0:
            raise ValueError("DENSE_PRIMARY_MIN_SCORE must be non-negative")
        if self.dense_primary_min_agreement < 0 or self.dense_primary_min_agreement > 1:
            raise ValueError("DENSE_PRIMARY_MIN_AGREEMENT must be between 0 and 1")
        if self.dense_primary_keep_top_k < 1 or self.bm25_rescue_top_k < 1:
            raise ValueError("Dense-primary keep/rescue top-k values must be positive")
        object.__setattr__(self, "data_dir", _path_env("DATA_DIR", self.root_dir / "data") if self.data_dir is None else Path(self.data_dir))
        object.__setattr__(self, "model_dir", _path_env("MODEL_DIR", self.root_dir / "models") if self.model_dir is None else Path(self.model_dir))

    @property
    def manuals_dir(self) -> Path:
        return self.data_dir / "raw" / "manuals"

    @property
    def tickets_dir(self) -> Path:
        return self.data_dir / "raw" / "tickets"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def embedding_model_path(self) -> Path:
        return self.model_dir / "qwen3-embedding-0.6b"

    @property
    def reranker_model_path(self) -> Path:
        return self.model_dir / "qwen3-reranker-0.6b"
