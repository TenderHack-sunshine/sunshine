from __future__ import annotations

import uuid
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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


class HttpQdrantStore:
    """Small REST-only Qdrant adapter.

    It has the same retrieval-facing contract as :class:`QdrantStore`, but
    avoids loading the Windows gRPC/protobuf stack into a Torch process. That
    stack conflicts with local Qwen3 inference on the Intel demo laptop.
    """

    def __init__(self, host: str = "localhost", port: int = 6333, collection: str = "tender_documents", timeout: float = 10.0):
        self.collection = collection
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = Request(
            f"{self.base_url}{path}", data=data, method=method,
            headers={"Content-Type": "application/json"} if data is not None else {},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as error:
            raise ConnectionError(f"Qdrant REST {method} {path} failed: {error}") from error

    def collection_exists(self, collection: str | None = None) -> bool:
        name = collection or self.collection
        response = self._request("GET", f"/collections/{name}/exists")
        return bool(response.get("result", {}).get("exists"))

    def create_collection(self, vector_size: int, recreate: bool = False) -> None:
        if self.collection_exists():
            if recreate:
                self.clear()
            else:
                info = self._request("GET", f"/collections/{self.collection}")
                configured_size = int(info["result"]["config"]["params"]["vectors"]["size"])
                if configured_size != vector_size:
                    raise RuntimeError(
                        f"Collection {self.collection!r} has vector size {configured_size}, expected {vector_size}. "
                        "Use --recreate to replace it intentionally."
                    )
                return
        self._request("PUT", f"/collections/{self.collection}", {"vectors": {"size": vector_size, "distance": "Cosine"}})

    def clear(self) -> None:
        if self.collection_exists():
            self._request("DELETE", f"/collections/{self.collection}")

    def upsert(self, chunks: list[dict], vectors: Any, batch_size: int = 64) -> int:
        points = []
        for chunk, vector in zip(chunks, vectors):
            points.append({
                "id": point_id_for_chunk(str(chunk["chunk_id"])),
                "vector": vector.tolist() if hasattr(vector, "tolist") else list(vector),
                "payload": payload_for_chunk(chunk),
            })
        for start in range(0, len(points), batch_size):
            self._request("PUT", f"/collections/{self.collection}/points?wait=true", {"points": points[start:start + batch_size]})
        return len(points)

    @staticmethod
    def _payload_filter(filters: dict[str, str | list[str]] | None) -> dict | None:
        if not filters:
            return None
        conditions = []
        for field, value in filters.items():
            if value is None:
                continue
            match = {"any": value} if isinstance(value, list) else {"value": value}
            conditions.append({"key": field, "match": match})
        return {"must": conditions} if conditions else None

    def search(self, vector: Any, limit: int = 20, filters: dict[str, str | list[str]] | None = None) -> list[dict]:
        body = {
            "query": vector.tolist() if hasattr(vector, "tolist") else list(vector),
            "limit": limit,
            "with_payload": True,
        }
        query_filter = self._payload_filter(filters)
        if query_filter:
            body["filter"] = query_filter
        response = self._request("POST", f"/collections/{self.collection}/points/query", body)
        return [{**(point.get("payload") or {}), "score": float(point["score"])} for point in response.get("result", {}).get("points", [])]

    def count(self) -> int:
        response = self._request("POST", f"/collections/{self.collection}/points/count", {"exact": True})
        return int(response["result"]["count"])
