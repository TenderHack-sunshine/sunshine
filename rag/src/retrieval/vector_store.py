from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any


def point_id_for_chunk(chunk_id: str) -> str:
    """Stable Qdrant UUID: repeated indexing updates the same point."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def payload_for_chunk(chunk: dict) -> dict:
    """Keep canonical fields and nested source-specific metadata in Qdrant."""
    payload = dict(chunk)
    payload.setdefault("page", payload.get("page_start"))
    payload["metadata"] = dict(payload.get("metadata") or {})
    return payload


class QdrantStore:
    """Thin wrapper around a team-controlled local Qdrant instance."""

    def __init__(self, host: str = "localhost", port: int = 6333, collection: str = "tender_documents",
                 local_path: str | Path | None = None):
        from qdrant_client import QdrantClient

        self.collection = collection
        self.client = QdrantClient(path=str(local_path)) if local_path else QdrantClient(host=host, port=port)

    def create_collection(self, vector_size: int, recreate: bool = False) -> None:
        from qdrant_client.models import Distance, VectorParams

        exists = self.client.collection_exists(self.collection)
        if exists and recreate:
            self.client.delete_collection(self.collection)
            exists = False
        if not exists:
            self.client.create_collection(self.collection, vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE))
        else:
            info = self.client.get_collection(self.collection)
            configured_size = info.config.params.vectors.size
            if configured_size != vector_size:
                raise RuntimeError(
                    f"Collection {self.collection!r} has vector size {configured_size}, expected {vector_size}. "
                    "Use --recreate to replace it intentionally."
                )

    def clear(self) -> None:
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)

    def upsert(self, chunks: list[dict], vectors: Any, batch_size: int = 64) -> int:
        from qdrant_client.models import PointStruct

        points = []
        for chunk, vector in zip(chunks, vectors):
            payload = payload_for_chunk(chunk)
            point_id = point_id_for_chunk(str(chunk["chunk_id"]))
            points.append(PointStruct(id=point_id, vector=vector.tolist() if hasattr(vector, "tolist") else list(vector), payload=payload))
        for start in range(0, len(points), batch_size):
            self.client.upsert(collection_name=self.collection, points=points[start:start + batch_size])
        return len(points)

    @staticmethod
    def _payload_filter(filters: dict[str, str | list[str]] | None):
        if not filters:
            return None
        from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

        conditions = []
        for field, value in filters.items():
            if value is None:
                continue
            match = MatchAny(any=value) if isinstance(value, list) else MatchValue(value=value)
            conditions.append(FieldCondition(key=field, match=match))
        return Filter(must=conditions) if conditions else None

    def search(self, vector: Any, limit: int = 20, filters: dict[str, str | list[str]] | None = None) -> list[dict]:
        points = self.client.query_points(
            collection_name=self.collection,
            query=vector.tolist() if hasattr(vector, "tolist") else list(vector), limit=limit, with_payload=True,
            query_filter=self._payload_filter(filters),
        ).points
        return [{**(point.payload or {}), "score": float(point.score)} for point in points]

    def count(self) -> int:
        return int(self.client.count(collection_name=self.collection, exact=True).count)
