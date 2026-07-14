from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .azure_openai import AzureOpenAIClient
from .models import DocumentAnalysis
from .pdf_text import extract_pdf_text
from .settings import read_prompt


def _classify_from_name_and_text(file_name: str, text: str) -> tuple[str, float, list[str]]:
    blob = f"{file_name}\n{text[:2500]}".lower()
    warnings: list[str] = []
    if any(k in blob for k in ["formula", "fórmula", "optometr", "medic"]):
        return "formula_medica", 0.65, warnings
    if any(k in blob for k in ["factura", "invoice", "nit", "total", "subtotal"]):
        return "factura", 0.7, warnings
    if any(k in blob for k in ["eps", "afiliacion", "afiliación", "beneficiario"]):
        return "certificado_eps", 0.65, warnings
    if not text.strip():
        warnings.append("No hay texto suficiente para clasificar localmente")
        return "otro", 0.2, warnings
    return "otro", 0.35, warnings


def _extract_dates(text: str) -> list[str]:
    patterns = [
        r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
        r"\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b",
    ]
    dates: list[str] = []
    for pattern in patterns:
        dates.extend(re.findall(pattern, text))
    return dates[:5]


def _local_extract_fields(document_type: str, text: str) -> dict[str, Any]:
    ids = re.findall(r"\b\d{6,12}\b", text)
    amounts = re.findall(r"\$?\s?\d[\d.,]{3,}", text)
    return {
        "document_type": document_type,
        "possible_ids": ids[:5],
        "possible_dates": _extract_dates(text),
        "possible_amounts": amounts[:5],
        "raw_text_excerpt": text[:1200],
    }


class DocumentAnalyzer:
    def __init__(
        self,
        *,
        ai_client: AzureOpenAIClient | None = None,
    ):
        self.ai_client = ai_client

    def analyze_file(self, path: str | Path) -> DocumentAnalysis:
        target = Path(path)
        warnings: list[str] = []
        text = ""
        text, local_warnings = extract_pdf_text(target)
        warnings.extend(local_warnings)

        document_type, confidence, classifier_warnings = _classify_from_name_and_text(target.name, text)
        warnings.extend(classifier_warnings)
        extracted_fields = _local_extract_fields(document_type, text)

        if self.ai_client and self.ai_client.available():
            payload = {
                "file_name": target.name,
                "local_document_type": document_type,
                "text_excerpt": text[:12000],
                "local_extracted_fields": extracted_fields,
            }
            response = self.ai_client.chat_json(
                deployment=(
                    self.ai_client.settings.azure_openai_deployment_multimodal
                    or self.ai_client.settings.azure_openai_deployment_text
                ),
                system_prompt=read_prompt("prompts/extraer_datos_documento.txt"),
                user_payload=payload,
            )
            if response:
                document_type = str(response.get("document_type") or document_type)
                extracted_fields = response
                confidence = float(response.get("confidence") or confidence)

        return DocumentAnalysis(
            file_name=target.name,
            document_type=document_type,
            text=text,
            extracted_fields=extracted_fields,
            confidence=confidence,
            warnings=warnings,
        )
