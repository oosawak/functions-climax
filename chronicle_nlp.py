from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from intent_processor import (
    build_english_prompt as _build_english_prompt,
    build_final_prompt_for_llm as _build_final_prompt_for_llm,
    interpret_with_azure_language as _interpret_with_azure_language,
    interpret_with_heuristics as _interpret_with_heuristics,
)


@dataclass(frozen=True)
class NlpResult:
    intent: str
    entities: dict[str, Any]
    provider: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "entities": self.entities,
            "provider": self.provider,
        }


def analyze_command(text: str) -> NlpResult:
    """Analyze a Japanese command.

    Uses Azure AI Language if configured; otherwise falls back to heuristics.
    """

    try:
        result = _interpret_with_azure_language(text)
    except Exception:
        result = _interpret_with_heuristics(text)

    return NlpResult(intent=result.intent, entities=result.entities, provider=result.provider)


def build_english_prompt(intent: str, entities: dict[str, Any]) -> str:
    return _build_english_prompt(type("_IR", (), {"intent": intent, "entities": entities})())


def build_final_prompt(english_prompt: str) -> str:
    return _build_final_prompt_for_llm(english_prompt)
