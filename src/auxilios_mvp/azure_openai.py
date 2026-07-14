from __future__ import annotations

import json
from typing import Any

try:
    import requests
except Exception:  # pragma: no cover - dependency optional in local fallback
    requests = None

from .json_utils import try_parse_json
from .settings import Settings


class AzureOpenAIClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def available(self) -> bool:
        return self.settings.has_azure_openai() and requests is not None

    def chat_json(
        self,
        *,
        deployment: str | None,
        system_prompt: str,
        user_payload: dict[str, Any],
        temperature: float = 0.0,
    ) -> dict[str, Any] | None:
        if not self.available() or not deployment:
            return None

        endpoint = self.settings.azure_openai_endpoint.rstrip("/")
        url = (
            f"{endpoint}/openai/deployments/{deployment}/chat/completions"
            f"?api-version={self.settings.azure_openai_api_version}"
        )
        body = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": "Devuelve solamente JSON valido.\n\n"
                    + json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        response = requests.post(
            url,
            headers={
                "api-key": self.settings.azure_openai_api_key,
                "content-type": "application/json",
            },
            json=body,
            timeout=90,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        parsed = try_parse_json(content)
        return parsed if isinstance(parsed, dict) else None
