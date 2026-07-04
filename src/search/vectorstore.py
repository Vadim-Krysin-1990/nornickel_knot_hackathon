"""Qdrant: коллекция чанков с payload {doc_id, source_path, text}."""
from __future__ import annotations

import uuid

from ..config import settings
from . import embedder

_client = None


def client():
    global _client
    if _client is None:
        from qdrant_client import QdrantClient

        _client = QdrantClient(url=settings.qdrant_url)
    return _client


def ensure_collection():
    from qdrant_client.models import Distance, VectorParams

    c = client()
    if not c.collection_exists(settings.qdrant_collection):
        c.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=embedder.dim(), distance=Distance.COSINE),
        )


def upsert_chunks(doc_id: str, source_path: str, chunks: list[str]):
    from qdrant_client.models import PointStruct

    if not chunks:
        return
    vectors = embedder.embed_passages(chunks)
    points = [
        PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_id}/{i}")),
            vector=v,
            payload={"doc_id": doc_id, "source_path": source_path, "chunk": i, "text": t},
        )
        for i, (t, v) in enumerate(zip(chunks, vectors))
    ]
    client().upsert(collection_name=settings.qdrant_collection, points=points)


def search(query: str, k: int = 5) -> list[dict]:
    vec = embedder.embed_query(query)
    hits = client().query_points(
        collection_name=settings.qdrant_collection, query=vec, limit=k
    ).points
    return [
        {"score": h.score, **(h.payload or {})}
        for h in hits
    ]
