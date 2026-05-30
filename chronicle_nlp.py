from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from intent_processor import (
    build_english_prompt as _build_english_prompt,
    build_final_prompt_for_llm as _build_final_prompt_for_llm,
    interpret_with_azure_language as _interpret_with_azure_language,
    interpret_with_heuristics as _interpret_with_heuristics,
)


def _debug_enabled() -> bool:
    v = (os.getenv("CHRONICLE_DEBUG_NLP") or "").strip().lower()
    return v in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class NlpResult:
    intent: str
    entities: dict[str, Any]
    provider: str
    error: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "intent": self.intent,
            "entities": self.entities,
            "provider": self.provider,
        }
        if self.error:
            payload["error"] = self.error
        return payload


def analyze_command(text: str) -> NlpResult:
    """Analyze a Japanese command.

    Uses Azure AI Language if configured; otherwise falls back to heuristics.

    If `CHRONICLE_DEBUG_NLP=1`, includes the Azure failure reason in the payload
    (useful for debugging misconfigurations).
    """

    debug = _debug_enabled()

    try:
        result = _interpret_with_azure_language(text)
        return NlpResult(intent=result.intent, entities=result.entities, provider=result.provider)
    except Exception as e:
        result = _interpret_with_heuristics(text)
        err = str(e)
        if debug:
            # Keep it short to avoid noisy responses.
            err = (err[:500] + "…") if len(err) > 500 else err
        else:
            err = None
        return NlpResult(intent=result.intent, entities=result.entities, provider=result.provider, error=err)


def build_english_prompt(intent: str, entities: dict[str, Any]) -> str:
    return _build_english_prompt(type("_IR", (), {"intent": intent, "entities": entities})())


def build_final_prompt(english_prompt: str) -> str:
    return _build_final_prompt_for_llm(english_prompt)
