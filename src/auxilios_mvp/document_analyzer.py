from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .azure_openai import AzureOpenAIClient
from .document_media import build_document_content
from .schemas import DocumentAnalysis
from .settings import read_prompt


SUPPORTED_DOCUMENT_TYPES = {
    "factura",
    "formula_medica",
    "certificado_eps",
    "certificado_escolar",
    "soporte_pago",
    "otro",
}


def _safe_confidence(value: Any, default: float) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(confidence, 1.0))


class DocumentAnalyzer:
    def __init__(
        self,
        *,
        ai_client: AzureOpenAIClient | None = None,
    ):
        self.ai_client = ai_client

    def analyze_file(self, path: str | Path) -> DocumentAnalysis:
        target = Path(path)
        if not self.ai_client or not self.ai_client.available():
            raise RuntimeError(
                "El analisis documental requiere Azure OpenAI configurado. "
                "Activa AZURE_OPENAI_ENABLED=true y completa endpoint, API key y deployment."
            )

        media_content, warnings, extracted_text = build_document_content(target)
        deployment = (
            self.ai_client.settings.azure_openai_deployment_multimodal
            or self.ai_client.settings.azure_openai_deployment_text
        )
        classification_payload = {
            "file_name": target.name,
            "supported_document_types": sorted(SUPPORTED_DOCUMENT_TYPES),
            "instruction": (
                "Clasifica semanticamente el documento usando texto e imagenes adjuntas. "
                "No dependas de palabras clave fijas ni de plantillas especificas."
            ),
        }
        classification = self.ai_client.chat_json_content(
            deployment=deployment,
            system_prompt=read_prompt("prompts/clasificar_documentos.txt"),
            user_content=[
                {"type": "text", "text": json.dumps(classification_payload, ensure_ascii=False)},
                *media_content,
            ],
        )

        document_type = str((classification or {}).get("document_type") or "otro")
        if document_type not in SUPPORTED_DOCUMENT_TYPES:
            warnings.append(f"IA retorno tipo documental no soportado: {document_type}")
            document_type = "otro"
        confidence = _safe_confidence((classification or {}).get("confidence"), 0.5)

        extraction_payload = {
            "file_name": target.name,
            "document_type": document_type,
            "classification": classification or {},
            "supported_document_types": sorted(SUPPORTED_DOCUMENT_TYPES),
            "instruction": (
                "Extrae campos y evidencia con criterio semantico desde texto e imagenes. "
                "No inventes datos que no esten soportados por evidencia verificable."
            ),
        }
        extraction = self.ai_client.chat_json_content(
            deployment=deployment,
            system_prompt=read_prompt("prompts/extraer_datos_documento.txt"),
            user_content=[
                {"type": "text", "text": json.dumps(extraction_payload, ensure_ascii=False)},
                *media_content,
            ],
        )

        extracted_fields = extraction or classification or {}
        if extraction:
            extracted_type = str(extraction.get("document_type") or document_type)
            if extracted_type in SUPPORTED_DOCUMENT_TYPES:
                document_type = extracted_type
            confidence = _safe_confidence(extraction.get("confidence"), confidence)
        extracted_fields.setdefault("document_type", document_type)
        extracted_fields.setdefault("classification", classification or {})

        return DocumentAnalysis(
            file_name=target.name,
            document_type=document_type,
            text=extracted_text,
            extracted_fields=extracted_fields,
            confidence=confidence,
            warnings=warnings,
        )
