from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .settings import Settings


class ResultStore:
    name = "base"

    def save_decision(self, payload: dict[str, Any]) -> None:
        raise NotImplementedError


class JsonlResultStore(ResultStore):
    name = "jsonl"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save_decision(self, payload: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


class CosmosResultStore(ResultStore):
    name = "cosmos"

    def __init__(self, settings: Settings):
        try:
            from azure.cosmos import CosmosClient
        except Exception as exc:
            raise RuntimeError("Instala azure-cosmos para usar CosmosResultStore") from exc

        if not (settings.cosmos_endpoint and settings.cosmos_key):
            raise RuntimeError("Faltan COSMOS_ENDPOINT o COSMOS_KEY")
        client = CosmosClient(settings.cosmos_endpoint, credential=settings.cosmos_key)
        database = client.get_database_client(settings.cosmos_database)
        self.container = database.get_container_client(settings.cosmos_container_decisions)

    def save_decision(self, payload: dict[str, Any]) -> None:
        self.container.upsert_item(payload)


def build_result_store(settings: Settings, fallback_path: str | Path) -> ResultStore:
    if settings.cosmos_enabled:
        if not (settings.cosmos_endpoint and settings.cosmos_key):
            raise RuntimeError(
                "COSMOS_ENABLED=true, pero faltan COSMOS_ENDPOINT o COSMOS_KEY en .env"
            )
        return CosmosResultStore(settings)
    return JsonlResultStore(fallback_path)
