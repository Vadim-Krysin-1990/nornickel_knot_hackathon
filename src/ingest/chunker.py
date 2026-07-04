"""Чанкинг по абзацам с целевым размером и перехлёстом."""
from __future__ import annotations


def chunk_text(text: str, target: int = 800, overlap: int = 120) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        if len(buf) + len(p) + 2 <= target or not buf:
            buf = f"{buf}\n\n{p}".strip()
        else:
            chunks.append(buf)
            tail = buf[-overlap:] if overlap else ""
            buf = f"{tail}\n\n{p}".strip()
    if buf:
        chunks.append(buf)
    return chunks
