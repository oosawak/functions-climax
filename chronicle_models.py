from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing or invalid '{key}'")
    return value


def optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"invalid '{key}'")
    return value


@dataclass(frozen=True)
class SessionUpdate:
    server_id: str
    session_id: str
    directory: str | None
    panes: list[dict[str, Any]]
    updated_at: str

    @staticmethod
    def from_payload(payload: dict[str, Any]) -> "SessionUpdate":
        server_id = require_str(payload, "server_id")
        session_id = require_str(payload, "session_id")
        directory = optional_str(payload, "directory")

        panes_raw = payload.get("panes", [])
        if not isinstance(panes_raw, list):
            raise ValueError("invalid 'panes'")
        panes: list[dict[str, Any]] = []
        for item in panes_raw:
            if not isinstance(item, dict):
                raise ValueError("invalid 'panes' item")
            panes.append(item)

        updated_at = optional_str(payload, "updated_at") or utc_now_iso()
        return SessionUpdate(
            server_id=server_id,
            session_id=session_id,
            directory=directory,
            panes=panes,
            updated_at=updated_at,
        )


@dataclass(frozen=True)
class LogAppend:
    server_id: str
    session_id: str
    timestamp: str
    log: str

    @staticmethod
    def from_payload(payload: dict[str, Any]) -> "LogAppend":
        server_id = require_str(payload, "server_id")
        session_id = require_str(payload, "session_id")
        timestamp = optional_str(payload, "timestamp") or utc_now_iso()
        log = require_str(payload, "log")
        return LogAppend(server_id=server_id, session_id=session_id, timestamp=timestamp, log=log)


@dataclass(frozen=True)
class ArtifactUpsert:
    session_id: str
    repo: str
    path: str
    commit: str | None
    updated_at: str

    @staticmethod
    def from_payload(payload: dict[str, Any]) -> "ArtifactUpsert":
        session_id = require_str(payload, "session_id")
        repo = require_str(payload, "repo")
        path = require_str(payload, "path")
        commit = optional_str(payload, "commit")
        updated_at = optional_str(payload, "updated_at") or utc_now_iso()
        return ArtifactUpsert(session_id=session_id, repo=repo, path=path, commit=commit, updated_at=updated_at)

