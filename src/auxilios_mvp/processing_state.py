from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schemas import RequestContext


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def request_key(request: RequestContext) -> str:
    return "::".join(
        [
            str(request.employee_id or "sin_cedula"),
            str(request.concept_code or request.benefit_code or "sin_beneficio"),
            str(request.request_id or "sin_solicitud"),
        ]
    ).upper()


def request_signature(request: RequestContext) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(request.files):
        path = Path(file_path)
        digest.update(path.name.encode("utf-8"))
        digest.update(file_sha256(path).encode("ascii"))
    return digest.hexdigest()


class ProcessingState:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.payload = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"requests": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"requests": {}}

    def save(self) -> None:
        self.path.write_text(json.dumps(self.payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def should_process(self, request: RequestContext, policy: str) -> tuple[bool, str, str]:
        key = request_key(request)
        signature = request_signature(request)
        previous = self.payload.get("requests", {}).get(key)

        if policy == "reprocess_all":
            return True, key, signature
        if policy == "skip_existing" and previous:
            return False, key, signature
        if policy == "skip_unchanged" and previous and previous.get("signature") == signature:
            return False, key, signature
        return True, key, signature

    def mark_processed(self, *, key: str, signature: str, recommendation: dict[str, Any]) -> None:
        requests = self.payload.setdefault("requests", {})
        previous = requests.get(key) or {}
        version = int(previous.get("version") or 0) + 1
        requests[key] = {
            "signature": signature,
            "version": version,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "recommendation": {
                "recommended_status": recommendation.get("recommended_status"),
                "confidence": recommendation.get("confidence"),
                "summary": recommendation.get("summary"),
            },
        }
