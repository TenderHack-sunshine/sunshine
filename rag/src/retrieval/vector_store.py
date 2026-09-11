from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any


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

    def clear(self) -> None:
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)

    def upsert(self, chunks: list[dict], vectors: Any, batch_size: int = 64) -> None:
        from qdrant_client.models import PointStruct

        points = []
        for chunk, vector in zip(chunks, vectors):
            payload = dict(chunk)
            payload.setdefault("page", payload.get("page_start"))
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(chunk["chunk_id"])))
            points.append(PointStruct(id=point_id, vector=vector.tolist() if hasattr(vector, "tolist") else list(vector), payload=payload))
        for start in range(0, len(points), batch_size):
            self.client.upsert(collection_name=self.collection, points=points[start:start + batch_size])

    def search(self, vector: Any, limit: int = 20) -> list[dict]:
        points = self.client.query_points(
            collection_name=self.collection,
            query=vector.tolist() if hasattr(vector, "tolist") else list(vector), limit=limit, with_payload=True,
        ).points
        return [{**(point.payload or {}), "score": float(point.score)} for point in points]
