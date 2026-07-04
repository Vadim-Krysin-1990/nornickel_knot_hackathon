"""Эмбеддинги: ленивая загрузка sentence-transformers.
e5-модели требуют префиксов query:/passage:, BGE-M3 — нет.
"""
from __future__ import annotations

from ..config import settings

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(settings.embed_model)
    return _model


def _is_e5() -> bool:
    return "e5" in settings.embed_model.lower()


def embed_passages(texts: list[str]) -> list[list[float]]:
    if _is_e5():
        texts = [f"passage: {t}" for t in texts]
    return _get_model().encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()


def embed_query(text: str) -> list[float]:
    if _is_e5():
        text = f"query: {text}"
    return _get_model().encode([text], normalize_embeddings=True, show_progress_bar=False)[0].tolist()


def dim() -> int:
    return _get_model().get_sentence_embedding_dimension()
