"""Единый LLM-клиент. Два протокола, автодетект по LLM_BASE_URL:
- openai: OpenAI-совместимые endpoints — Yandex AI Studio
  (https://llm.api.cloud.yandex.net/v1), OpenRouter, vLLM, локальный Ollama (/v1)
- ollama: нативный /api/chat — облачный api.ollama.com (на /v1 отдаёт 405)
Переопределить вручную: LLM_PROVIDER=openai|ollama в .env.
"""
from __future__ import annotations

import json
import re

import requests

from .config import settings


def _provider() -> str:
    if settings.llm_provider:
        return settings.llm_provider
    return "ollama" if "api.ollama.com" in settings.llm_base_url else "openai"


def has_llm() -> bool:
    return bool(settings.llm_api_key) or "localhost" in settings.llm_base_url or "11434" in settings.llm_base_url


def chat(messages: list[dict], temperature: float = 0.0, json_mode: bool = False, max_tokens: int = 4000) -> str:
    if _provider() == "ollama":
        return _chat_ollama(messages, temperature, json_mode, max_tokens)
    return _chat_openai(messages, temperature, json_mode, max_tokens)


_openai_client = None


def _chat_openai(messages, temperature, json_mode, max_tokens) -> str:
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI

        _openai_client = OpenAI(
            base_url=settings.llm_base_url, api_key=settings.llm_api_key or "local"
        )
    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    try:
        resp = _openai_client.chat.completions.create(
            model=settings.llm_model, messages=messages,
            temperature=temperature, max_tokens=max_tokens, **kwargs,
        )
    except Exception:
        if not json_mode:
            raise
        # endpoint не поддерживает response_format — повтор без него,
        # JSON вытащит parse_json (промпт и так требует строгий JSON)
        resp = _openai_client.chat.completions.create(
            model=settings.llm_model, messages=messages,
            temperature=temperature, max_tokens=max_tokens,
        )
    return resp.choices[0].message.content or ""


def _chat_ollama(messages, temperature, json_mode, max_tokens) -> str:
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if json_mode:
        payload["format"] = "json"

    resp = requests.post(
        f"{settings.llm_base_url.rstrip('/v1').rstrip('/')}/api/chat",
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def chat_json(messages: list[dict], temperature: float = 0.0, max_tokens: int = 4000) -> dict:
    raw = chat(messages, temperature=temperature, json_mode=True, max_tokens=max_tokens)
    return parse_json(raw)


def parse_json(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise
