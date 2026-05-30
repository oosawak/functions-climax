from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from azure.cosmos import CosmosClient

from chronicle_models import ArtifactUpsert, LogAppend, SessionUpdate, utc_now_iso


class ChronicleStorage:
    def upsert_session(self, update: SessionUpdate) -> dict[str, Any]:
        raise NotImplementedError

    def append_log(self, item: LogAppend) -> dict[str, Any]:
        raise NotImplementedError

    def get_session(self, server_id: str, session_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def list_sessions(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def list_logs(
        self,
        server_id: str,
        session_id: str,
        *,
        limit: int = 200,
        since: str | None = None,
        until: str | None = None,
        topic: str | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def list_artifacts(self) -> list[dict[str, Any]]:
        return []


class FileStorage(ChronicleStorage):
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, record: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def upsert_session(self, update: SessionUpdate) -> dict[str, Any]:
        record = {
            "id": f"session-{update.server_id}-{update.session_id}",
            "type": "session",
            **asdict(update),
        }
        self._append(record)
        return record

    def append_log(self, item: LogAppend) -> dict[str, Any]:
        record = {
            "id": f"log-{item.server_id}-{item.session_id}-{item.timestamp}",
            "type": "log",
            **asdict(item),
        }
        self._append(record)
        return record

    def get_session(self, server_id: str, session_id: str) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        target_id = f"session-{server_id}-{session_id}"
        latest: dict[str, Any] | None = None
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("type") != "session":
                    continue
                if item.get("id") != target_id:
                    continue
                latest = item
        return latest

    def list_sessions(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        sessions: dict[str, dict[str, Any]] = {}
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("type") != "session":
                    continue
                sessions[item["id"]] = item
        return sorted(sessions.values(), key=lambda x: x.get("updated_at", ""), reverse=True)

    def list_logs(
        self,
        server_id: str,
        session_id: str,
        *,
        limit: int = 200,
        since: str | None = None,
        until: str | None = None,
        topic: str | None = None,
    ) -> list[dict[str, Any]]:
        if limit < 1:
            return []
        if limit > 2000:
            limit = 2000
        if not self.path.exists():
            return []

        items: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("type") != "log":
                    continue
                if item.get("server_id") != server_id or item.get("session_id") != session_id:
                    continue
                if topic and item.get("topic") != topic:
                    continue
                ts = str(item.get("timestamp") or "")
                if since and ts and ts < since:
                    continue
                if until and ts and ts > until:
                    continue
                items.append(item)

        items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return items[:limit]


class CosmosStorage(ChronicleStorage):
    def __init__(self, endpoint: str, key: str, database: str, container: str) -> None:
        self.client = CosmosClient(endpoint, credential=key)
        self.container = self.client.get_database_client(database).get_container_client(container)

    def upsert_session(self, update: SessionUpdate) -> dict[str, Any]:
        record = {
            "id": f"session-{update.server_id}-{update.session_id}",
            "type": "session",
            "pk": f"session:{update.server_id}",
            **asdict(update),
        }
        self.container.upsert_item(record)
        return record

    def append_log(self, item: LogAppend) -> dict[str, Any]:
        record = {
            "id": f"log-{item.server_id}-{item.session_id}-{item.timestamp}",
            "type": "log",
            "pk": f"log:{item.server_id}:{item.session_id}",
            **asdict(item),
        }
        self.container.upsert_item(record)
        return record

    def get_session(self, server_id: str, session_id: str) -> dict[str, Any] | None:
        target_id = f"session-{server_id}-{session_id}"
        pk = f"session:{server_id}"
        try:
            return self.container.read_item(item=target_id, partition_key=pk)
        except Exception:
            return None

    def list_sessions(self) -> list[dict[str, Any]]:
        query = "SELECT * FROM c WHERE c.type = 'session' ORDER BY c.updated_at DESC"
        return list(self.container.query_items(query=query, enable_cross_partition_query=True))

    def list_logs(
        self,
        server_id: str,
        session_id: str,
        *,
        limit: int = 200,
        since: str | None = None,
        until: str | None = None,
        topic: str | None = None,
    ) -> list[dict[str, Any]]:
        if limit < 1:
            return []
        if limit > 2000:
            limit = 2000

        pk = f"log:{server_id}:{session_id}"
        where = ["c.type = 'log'", "c.pk = @pk"]
        params: list[dict[str, Any]] = [{"name": "@pk", "value": pk}]
        if since:
            where.append("c.timestamp >= @since")
            params.append({"name": "@since", "value": since})
        if until:
            where.append("c.timestamp <= @until")
            params.append({"name": "@until", "value": until})
        if topic:
            where.append("c.topic = @topic")
            params.append({"name": "@topic", "value": topic})

        query = (
            "SELECT TOP @limit * FROM c WHERE "
            + " AND ".join(where)
            + " ORDER BY c.timestamp DESC"
        )
        params.insert(0, {"name": "@limit", "value": limit})

        return list(
            self.container.query_items(
                query=query,
                parameters=params,
                enable_cross_partition_query=True,
            )
        )


def get_storage() -> ChronicleStorage:
    kind = (os.getenv("CHRONICLE_STORAGE") or "file").strip().lower()
    if kind == "cosmos":
        endpoint = os.getenv("COSMOS_ENDPOINT") or ""
        key = os.getenv("COSMOS_KEY") or ""
        database = os.getenv("COSMOS_DATABASE") or "climax-chronicle"
        container = os.getenv("COSMOS_CONTAINER") or "items"
        if not endpoint or not key:
            raise RuntimeError("CHRONICLE_STORAGE=cosmos but COSMOS_ENDPOINT/COSMOS_KEY missing")
        return CosmosStorage(endpoint=endpoint, key=key, database=database, container=container)

    path = os.getenv("CHRONICLE_FILE_PATH") or "./.data/chronicle.jsonl"
    return FileStorage(path)


def health_payload(storage_kind: str) -> dict[str, Any]:
    return {"ok": True, "storage": storage_kind, "timestamp": utc_now_iso()}
