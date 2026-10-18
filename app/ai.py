from __future__ import annotations

from dataclasses import dataclass
import logging

import httpx

from .config import get_settings


logger = logging.getLogger(__name__)


@dataclass
class AIResponse:
    text: str
    provider: str
    model: str
    units: float = 0
    estimated_cost: float = 0


class AIProvider:
    def generate(self, system: str, user: str, fallback: str) -> AIResponse:
        raise NotImplementedError


class LocalProvider(AIProvider):
    def generate(self, system: str, user: str, fallback: str) -> AIResponse:
        return AIResponse(text=fallback, provider="local", model="deterministic")


class OpenAICompatibleProvider(AIProvider):
    def __init__(self) -> None:
        self.settings = get_settings()

    def generate(self, system: str, user: str, fallback: str) -> AIResponse:
        try:
            payload = {
                "model": self.settings.ai_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
            }
            headers = {"Authorization": "Bearer " + self.settings.ai_api_key}
            with httpx.Client(timeout=15) as client:
                response = client.post(
                    self.settings.ai_base_url.rstrip("/") + "/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                text = data["choices"][0]["message"]["content"].strip()
                usage = data.get("usage") or {}
                units = float(usage.get("total_tokens") or 0)
                return AIResponse(
                    text=text,
                    provider="openai_compatible",
                    model=self.settings.ai_model,
                    units=units,
                    estimated_cost=0,
                )
        except Exception:
            logger.warning(
                "LLM provider request failed; using deterministic fallback", exc_info=True
            )
            return AIResponse(text=fallback, provider="fallback", model="deterministic")


def get_ai_provider() -> AIProvider:
    settings = get_settings()
    if settings.ai_provider == "openai_compatible":
        return OpenAICompatibleProvider()
    return LocalProvider()
