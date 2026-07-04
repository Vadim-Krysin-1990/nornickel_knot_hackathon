"""Аудит действий: логирование запросов к API в локальный JSONL-файл.
Не должен ронять основной запрос — ошибка записи молча проглатывается.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "audit.jsonl"


def log_action(action: str, details: dict | None = None) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "action": action,
            **(details or {}),
        }
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def recent(limit: int = 50) -> list[dict]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(out))
