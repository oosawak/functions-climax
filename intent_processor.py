from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional


def _env_any(*names: str) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        value = value.strip()
        if value:
            return value
    return None


@dataclass(frozen=True)
class IntentResult:
    intent: str
    entities: dict[str, Any]
    provider: str = "azure-ai-language"


def interpret_with_azure_language(text: str) -> IntentResult:
    """Interpret Japanese text with Azure AI Language (Conversation / CLU).

    Env vars (either naming works):
    - Endpoint: `LANGUAGE_ENDPOINT` or `AZURE_LANGUAGE_ENDPOINT`
    - Key: `LANGUAGE_KEY` or `AZURE_LANGUAGE_KEY`
    - Project: `LANGUAGE_PROJECT` or `AZURE_LANGUAGE_PROJECT`
    - Deployment: `LANGUAGE_DEPLOYMENT` or `AZURE_LANGUAGE_DEPLOYMENT`
    """

    endpoint = _env_any("LANGUAGE_ENDPOINT", "AZURE_LANGUAGE_ENDPOINT")
    key = _env_any("LANGUAGE_KEY", "AZURE_LANGUAGE_KEY")
    project = _env_any("LANGUAGE_PROJECT", "AZURE_LANGUAGE_PROJECT")
    deployment = _env_any("LANGUAGE_DEPLOYMENT", "AZURE_LANGUAGE_DEPLOYMENT")

    if not endpoint or not key or not project or not deployment:
        raise RuntimeError("Azure AI Language env vars are not set")

    endpoint = endpoint.rstrip("/")
    url = f"{endpoint}/language/:analyze-conversations?api-version=2024-11-01"

    payload = {
        "kind": "Conversation",
        "analysisInput": {
            "conversationItem": {
                "text": text,
                "id": "1",
                "participantId": "user",
            }
        },
        "parameters": {
            "projectName": project,
            "deploymentName": deployment,
        },
    }

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Ocp-Apim-Subscription-Key": key,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            raw = res.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        details = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Azure AI Language HTTPError: {e.code} {details}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Azure AI Language URLError: {e.reason}") from e

    data = json.loads(raw)

    result = data.get("result") if isinstance(data, dict) else None
    prediction = result.get("prediction") if isinstance(result, dict) else None
    if not isinstance(prediction, dict):
        return IntentResult(intent="unknown", entities={"raw": data}, provider="azure-ai-language")

    top_intent = prediction.get("topIntent")
    intent = top_intent.strip() if isinstance(top_intent, str) and top_intent.strip() else "unknown"

    entities: dict[str, Any] = {}
    entities_raw = prediction.get("entities")
    if isinstance(entities_raw, list):
        # Keep the raw list, and also try to flatten common fields.
        entities["entities"] = entities_raw
        for e in entities_raw:
            if not isinstance(e, dict):
                continue
            name = e.get("category") or e.get("entity")
            val = e.get("text") or e.get("value")
            if isinstance(name, str) and name and val is not None:
                entities.setdefault(name, val)

    # Normalize common entity fields (e.g., query/path tokens)
    for key in ("query", "path"):
        raw_val = entities.get(key)
        if not isinstance(raw_val, str) or not raw_val.strip():
            continue
        raw_val = raw_val.strip()
        # Prefer leading ASCII-ish token for file paths / identifiers.
        m = re.match(r"^([A-Za-z0-9_./-]{2,})", raw_val)
        if m:
            entities[key] = m.group(1)
        else:
            # Fallback: strip common trailing particles/verbs.
            entities[key] = re.sub(r"(を開いて|開いて|を検索して|検索して|探して|を探して)\s*$", "", raw_val)

    # Normalize common entity fields (e.g., session names)
    session_val = entities.get("session")
    if isinstance(session_val, str) and session_val:
        session_val = session_val.strip()
        m = re.match(r"^([A-Za-z0-9_./-]{2,})", session_val)
        if m:
            entities["session"] = m.group(1)
        else:
            entities["session"] = re.sub(r"(を開いて|開いて|の続き|続き|再開)\s*$", "", session_val)

    return IntentResult(intent=intent, entities=entities, provider="azure-ai-language")


def interpret_with_heuristics(text: str) -> IntentResult:
    normalized = text.strip()

    session: Optional[str] = None
    match = re.search(r"([A-Za-z0-9_./-]{2,})\s*(の)?\s*(続き)", normalized)
    if match:
        session = match.group(1)

    if "続き" in normalized or "再開" in normalized:
        entities: dict[str, Any] = {}
        if session:
            entities["session"] = session
        return IntentResult(intent="continue_previous_task", entities=entities, provider="heuristic")

    return IntentResult(intent="unknown", entities={"text": normalized}, provider="heuristic")


def build_english_prompt(intent_result: IntentResult) -> str:
    """IntentResult -> English task instruction."""

    intent = intent_result.intent
    ent = intent_result.entities

    if intent == "continue_previous_task":
        session = ent.get("session") if isinstance(ent, dict) else None
        if isinstance(session, str) and session.strip():
            return f"Continue the previous development session named '{session.strip()}'."
        return "Continue the previous development work from the latest context."

    if intent == "summarize_logs":
        return "Summarize the following logs in a concise way."

    if intent == "open_unity_session":
        session = ent.get("session") if isinstance(ent, dict) else None
        session = session.strip() if isinstance(session, str) and session.strip() else "unity-dev"
        return f"Open the Unity development session named '{session}'."

    if intent == "search_in_repo":
        query = ent.get("query") if isinstance(ent, dict) else None
        query = query.strip() if isinstance(query, str) and query.strip() else None
        if query:
            return f"Search the repository for occurrences of '{query}'. Use ripgrep (rg)."
        return "Search the repository for the user-requested keyword. Use ripgrep (rg)."

    if intent == "open_file":
        path = ent.get("path") if isinstance(ent, dict) else None
        path = path.strip() if isinstance(path, str) and path.strip() else None
        if path:
            return f"Open and inspect the file at path '{path}'."
        return "Open and inspect the file the user mentioned."

    if intent == "run_checks":
        return "Run the project's local checks (bash run_checks.sh) and report results."

    if intent == "summarize_diff":
        return "Summarize the current git diff (changes) concisely."

    return "The user's intent is unclear. Ask one concise clarifying question in Japanese about what they want to do next, and wait for their answer."


def build_final_prompt_for_llm(english_prompt: str) -> str:
    """English understanding, Japanese-only response."""

    return f"""You are an AI assistant that ALWAYS responds in Japanese.
You will receive a task description in English.
You must understand the task in English, but your final answer MUST be in Japanese.

# Task (in English):
{english_prompt}
"""


def preprocess_for_llm(japanese_text: str) -> str:
    """Japanese -> Intent -> English prompt -> final prompt (Japanese response enforced)."""

    try:
        intent_result = interpret_with_azure_language(japanese_text)
    except Exception:
        intent_result = interpret_with_heuristics(japanese_text)

    english_prompt = build_english_prompt(intent_result)
    return build_final_prompt_for_llm(english_prompt)
