from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        return


@dataclass(frozen=True)
class Settings:
    app_input_mode: str
    local_layout_root_dir: str
    processing_policy: str
    processing_state_filename: str
    layout_config_dir: str
    layout_requests_dir: str
    layout_reports_dir: str
    history_excel_filename: str
    benefits_filename: str
    azure_openai_endpoint: str | None
    azure_openai_api_key: str | None
    azure_openai_enabled: bool
    azure_openai_api_version: str
    azure_openai_deployment_multimodal: str | None
    azure_openai_deployment_text: str | None
    cosmos_endpoint: str | None
    cosmos_key: str | None
    cosmos_enabled: bool
    cosmos_database: str
    cosmos_container_requests: str
    cosmos_container_documents: str
    cosmos_container_decisions: str
    cosmos_container_executions: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv_if_available()
        return cls(
            app_input_mode=os.getenv("APP_INPUT_MODE", "local_layout").strip().lower(),
            local_layout_root_dir=os.getenv("LOCAL_LAYOUT_ROOT_DIR", "data/mvp_layout"),
            processing_policy=os.getenv("PROCESSING_POLICY", "skip_unchanged").strip().lower(),
            processing_state_filename=os.getenv("PROCESSING_STATE_FILENAME", "processing_state.json"),
            layout_config_dir=os.getenv("LAYOUT_CONFIG_DIR", "00_Config"),
            layout_requests_dir=os.getenv("LAYOUT_REQUESTS_DIR", "01_EntradaSolicitudes"),
            layout_reports_dir=os.getenv("LAYOUT_REPORTS_DIR", "02_SalidaReportes"),
            history_excel_filename=os.getenv("HISTORY_EXCEL_FILENAME", "Historico Auxilios.xlsx"),
            benefits_filename=os.getenv("BENEFITS_FILENAME", "beneficios.csv"),
            azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT") or None,
            azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY") or None,
            azure_openai_enabled=os.getenv("AZURE_OPENAI_ENABLED", "true").strip().lower()
            in {"1", "true", "yes", "si", "sí"},
            azure_openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
            azure_openai_deployment_multimodal=(
                os.getenv("AZURE_OPENAI_DEPLOYMENT_OMNIMODAL")
                or os.getenv("AZURE_OPENAI_DEPLOYMENT_MULTIMODAL")
                or None
            ),
            azure_openai_deployment_text=os.getenv("AZURE_OPENAI_DEPLOYMENT_TEXT") or None,
            cosmos_endpoint=os.getenv("COSMOS_ENDPOINT") or None,
            cosmos_key=os.getenv("COSMOS_KEY") or None,
            cosmos_enabled=os.getenv("COSMOS_ENABLED", "false").strip().lower()
            in {"1", "true", "yes", "si", "sí"},
            cosmos_database=os.getenv("COSMOS_DATABASE", "calidad_vida_auxilios"),
            cosmos_container_requests=os.getenv("COSMOS_CONTAINER_REQUESTS", "requests"),
            cosmos_container_documents=os.getenv("COSMOS_CONTAINER_DOCUMENTS", "documents"),
            cosmos_container_decisions=os.getenv("COSMOS_CONTAINER_DECISIONS", "decisions"),
            cosmos_container_executions=os.getenv("COSMOS_CONTAINER_EXECUTIONS", "executions"),
        )

    def has_azure_openai(self) -> bool:
        return bool(self.azure_openai_enabled and self.azure_openai_endpoint and self.azure_openai_api_key)


def read_prompt(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")
