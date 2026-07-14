from __future__ import annotations

from pathlib import Path
from typing import Callable

from .azure_openai import AzureOpenAIClient
from .benefits import load_benefit_rules
from .cosmos_store import build_result_store
from .document_analyzer import DocumentAnalyzer
from .json_utils import read_json, write_json
from .excel_history import normalize_history_excel
from .recommendation import recommend
from .reporting import write_recommendations_csv
from .request_parser import list_request_folders
from .processing_state import ProcessingState
from .settings import Settings


def _default_log(message: str) -> None:
    print(message, flush=True)


def run_local_pipeline(
    *,
    requests_dir: str | Path,
    history_json: str | Path,
    benefits_file: str | Path,
    output_dir: str | Path,
    settings: Settings,
    log: Callable[[str], None] | None = None,
) -> dict[str, str]:
    log = log or _default_log
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    log("Iniciando procesamiento de solicitudes.")
    log(f"  Solicitudes: {Path(requests_dir)}")
    log(f"  Historico JSON: {Path(history_json)}")
    log(f"  Reglas: {Path(benefits_file)}")
    log(f"  Salida: {out}")

    ai_client = AzureOpenAIClient(settings)
    log(f"  Azure OpenAI: {'configurado' if ai_client.available() else 'no configurado'}")
    analyzer = DocumentAnalyzer(ai_client=ai_client)
    benefit_rules = load_benefit_rules(benefits_file)
    log(f"  Reglas cargadas: {len(benefit_rules)} claves/alias")
    history = read_json(history_json)
    history_records = history.get("records", []) if isinstance(history, dict) else []
    log(f"  Registros historicos normalizados: {len(history_records)}")
    log("  Preparando almacenamiento de resultados.")
    store = build_result_store(settings, out / "decisions.jsonl")
    if store.name == "cosmos":
        log(f"  Almacenamiento: Cosmos DB / contenedor {settings.cosmos_container_decisions}")
    else:
        log(f"  Almacenamiento: archivo local {out / 'decisions.jsonl'}")
    state = ProcessingState(out / settings.processing_state_filename)

    recommendations = []
    analyses_payload = []
    skipped_payload = []
    requests = list_request_folders(requests_dir)
    log(f"Solicitudes detectadas: {len(requests)}")
    for index, request in enumerate(requests, start=1):
        log(
            f"[{index}/{len(requests)}] Solicitud {request.request_id} "
            f"- empleado={request.employee_id or 'sin_cedula'} "
            f"- beneficio={request.benefit_code or 'sin_beneficio'} "
            f"- archivos={len(request.files)}"
        )
        should_process, state_key, signature = state.should_process(request, settings.processing_policy)
        if not should_process:
            log("  Saltada: ya fue procesada y no cambio. No se vuelve a guardar decision.")
            skipped_payload.append(
                {
                    "request": request.__dict__,
                    "state_key": state_key,
                    "signature": signature,
                    "reason": settings.processing_policy,
                }
            )
            continue
        documents = []
        for file_index, path in enumerate(request.files, start=1):
            log(f"  Analizando documento {file_index}/{len(request.files)}: {Path(path).name}")
            documents.append(analyzer.analyze_file(path))
        rule = benefit_rules.get(str(request.benefit_code or "").upper())
        log("  Generando recomendacion.")
        rec = recommend(
            request=request,
            documents=documents,
            benefit_rule=rule,
            history_records=history_records,
            ai_client=ai_client,
        )
        recommendations.append(rec)
        log(f"  Resultado: {rec.recommended_status} (confianza={rec.confidence})")
        payload = {
            "id": f"{request.request_id}-{request.employee_id}-{request.benefit_code}",
            "request": request.__dict__,
            "state_key": state_key,
            "signature": signature,
            "documents": [doc.__dict__ for doc in documents],
            "recommendation": rec.to_dict(),
        }
        analyses_payload.append(payload)
        store.save_decision(payload)
        state.mark_processed(key=state_key, signature=signature, recommendation=rec.to_dict())

    json_path = out / "recommendations.json"
    csv_path = out / "recommendations.csv"
    log("Escribiendo archivos de salida.")
    write_json(json_path, [rec.to_dict() for rec in recommendations])
    write_json(out / "document_analyses.json", analyses_payload)
    write_json(out / "skipped_requests.json", skipped_payload)
    write_recommendations_csv(csv_path, recommendations)
    state.save()
    log(f"Proceso terminado. Recomendaciones generadas: {len(recommendations)}; saltadas: {len(skipped_payload)}")
    return {"recommendations_json": str(json_path), "recommendations_csv": str(csv_path)}


def run_folder_layout_pipeline(
    *,
    root_dir: str | Path,
    output_dir: str | Path | None,
    settings: Settings,
    log: Callable[[str], None] | None = None,
) -> dict[str, str]:
    log = log or _default_log
    root = Path(root_dir)
    config_dir = root / settings.layout_config_dir
    requests_dir = root / settings.layout_requests_dir
    reports_dir = Path(output_dir) if output_dir else root / settings.layout_reports_dir
    log("Validando estructura de carpetas.")
    log(f"  Raiz: {root}")
    log(f"  Configuracion: {config_dir}")
    log(f"  Solicitudes: {requests_dir}")
    log(f"  Reportes: {reports_dir}")

    history_candidates = [
        config_dir / settings.history_excel_filename,
        config_dir / "Historico Auxilios.xlsx",
        config_dir / "Historico Auxilios (2026).xlsx",
        config_dir / "historico_auxilios.xlsx",
        config_dir / "historico.xlsx",
    ]
    benefits_candidates = [
        config_dir / settings.benefits_filename,
        config_dir / "beneficios.csv",
        config_dir / "beneficios.xlsx",
        Path("config/beneficios.csv"),
    ]
    history_excel = next((path for path in history_candidates if path.exists()), None)
    benefits_file = next((path for path in benefits_candidates if path.exists()), None)

    if not history_excel:
        raise FileNotFoundError(
            f"No encontre el historico en {settings.layout_config_dir}. "
            f"Nombre esperado: {settings.history_excel_filename}"
        )
    if not benefits_file:
        raise FileNotFoundError(
            "No encontre beneficios.csv/beneficios.xlsx en 00_Config ni config/beneficios.csv."
        )
    if not requests_dir.exists():
        raise FileNotFoundError(f"No encontre la carpeta {settings.layout_requests_dir}.")
    log(f"  Historico encontrado: {history_excel}")
    log(f"  Reglas encontradas: {benefits_file}")

    history_json = reports_dir / "history_normalized.json"
    ai_client = AzureOpenAIClient(settings)
    log("Normalizando historico Excel.")
    normalized = normalize_history_excel(history_excel, ai_client=ai_client)
    write_json(history_json, normalized)
    log(
        f"Historico normalizado: {len(normalized.get('records', []))} registros; "
        f"confianza mapeo={normalized.get('mapping_confidence')}"
    )
    for warning in normalized.get("warnings", []):
        log(f"WARNING historico: {warning}")
    return run_local_pipeline(
        requests_dir=requests_dir,
        history_json=history_json,
        benefits_file=benefits_file,
        output_dir=reports_dir,
        settings=settings,
        log=log,
    )
