from __future__ import annotations

import json
import threading
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

from .json_utils import read_json, to_jsonable, write_json
from .pipeline import run_folder_layout_pipeline
from .processing_state import ProcessingState, request_key, request_signature
from .request_parser import list_request_folders
from .settings import Settings


JOB_LOCK = threading.Lock()
JOB_STATE: dict[str, Any] = {
    "running": False,
    "mode": None,
    "logs": [],
    "outputs": None,
    "error": None,
    "started_at": None,
    "finished_at": None,
}


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).resolve().parent / "templates"),
        static_folder=str(Path(__file__).resolve().parent / "static"),
    )

    @app.get("/")
    def index() -> str:
        return render_template("dashboard.html")

    @app.get("/metrics")
    def metrics() -> str:
        return render_template("dashboard.html", open_metrics=True)

    @app.get("/api/dashboard")
    def api_dashboard() -> Any:
        settings = Settings.from_env()
        return jsonify(build_dashboard(settings))

    @app.get("/api/job")
    def api_job() -> Any:
        return jsonify(current_job())

    @app.post("/api/analyze")
    def api_analyze() -> Any:
        payload = request.get_json(silent=True) or {}
        mode = str(payload.get("mode") or "pending")
        if mode not in {"pending", "all"}:
            return jsonify({"ok": False, "error": "Modo de analisis no soportado"}), 400
        started = start_job(mode)
        status = 202 if started["ok"] else 409
        return jsonify(started), status

    @app.post("/api/recommendations/approve")
    def api_approve_recommendations() -> Any:
        payload = request.get_json(silent=True) or {}
        ids = [str(item) for item in payload.get("ids") or [] if str(item).strip()]
        settings = Settings.from_env()
        actions = load_actions(settings)
        approved = set(actions.get("approved_recommendations") or [])
        approved.update(ids)
        actions["approved_recommendations"] = sorted(approved)
        actions["last_approved_at"] = datetime.now().isoformat(timespec="seconds")
        save_actions(settings, actions)
        return jsonify({"ok": True, "approved_count": len(approved)})

    @app.post("/api/sus-factory")
    def api_sus_factory() -> Any:
        payload = request.get_json(silent=True) or {}
        ids = [str(item) for item in payload.get("ids") or [] if str(item).strip()]
        settings = Settings.from_env()
        actions = load_actions(settings)
        events = list(actions.get("sus_factory_events") or [])
        events.append(
            {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "recommendation_ids": ids,
                "status": "DUMMY_READY",
                "message": "Accion dummy registrada para futura integracion con Success Factory.",
            }
        )
        actions["sus_factory_events"] = events[-20:]
        save_actions(settings, actions)
        return jsonify({"ok": True, "message": "Accion dummy registrada"})

    return app


def build_dashboard(settings: Settings) -> dict[str, Any]:
    root = Path(settings.local_layout_root_dir)
    requests_dir = root / settings.layout_requests_dir
    reports_dir = root / settings.layout_reports_dir
    state = ProcessingState(reports_dir / settings.processing_state_filename)
    decisions = load_latest_decisions(reports_dir)
    actions = load_actions(settings)
    requests_payload = []

    if requests_dir.exists():
        for item in list_request_folders(requests_dir):
            key = request_key(item)
            signature = request_signature(item)
            previous = state.payload.get("requests", {}).get(key)
            decision = decisions.get(key)
            if not previous:
                status = "NUEVA"
            elif previous.get("signature") != signature:
                status = "MODIFICADA"
            else:
                status = "PROCESADA"
            summary = {}
            if decision:
                summary = decision.get("recommendation") or {}
            elif previous:
                summary = previous.get("recommendation") or {}
            requests_payload.append(
                {
                    "key": key,
                    "signature": signature,
                    "request_id": item.request_id,
                    "employee_id": item.employee_id,
                    "benefit_code": item.benefit_code,
                    "files_count": len(item.files),
                    "source_path": item.source_path,
                    "status": status,
                    "processed_at": previous.get("processed_at") if previous else None,
                    "recommendation": summary,
                }
            )

    recommendations = []
    approved = set(actions.get("approved_recommendations") or [])
    for decision in decisions.values():
        recommendation = decision.get("recommendation") or {}
        request_payload = decision.get("request") or {}
        recommendation_id = str(decision.get("id") or decision.get("state_key") or "")
        recommendations.append(
            {
                "id": recommendation_id,
                "request_id": recommendation.get("request_id") or request_payload.get("request_id"),
                "employee_id": recommendation.get("employee_id") or request_payload.get("employee_id"),
                "benefit_code": recommendation.get("benefit_code") or request_payload.get("benefit_code"),
                "recommended_status": recommendation.get("recommended_status"),
                "confidence": recommendation.get("confidence"),
                "summary": recommendation.get("summary"),
                "approved": recommendation_id in approved,
            }
        )

    counts = {
        "total": len(requests_payload),
        "new": sum(1 for item in requests_payload if item["status"] == "NUEVA"),
        "modified": sum(1 for item in requests_payload if item["status"] == "MODIFICADA"),
        "processed": sum(1 for item in requests_payload if item["status"] == "PROCESADA"),
        "approved": sum(1 for item in recommendations if item["recommended_status"] == "APROBAR"),
        "rejected": sum(1 for item in recommendations if item["recommended_status"] == "RECHAZAR"),
        "review": sum(1 for item in recommendations if item["recommended_status"] == "REVISION"),
    }
    counts["notifications"] = counts["new"] + counts["modified"]

    return {
        "root_dir": str(root),
        "requests_dir": str(requests_dir),
        "reports_dir": str(reports_dir),
        "counts": counts,
        "requests": requests_payload,
        "recommendations": sorted(recommendations, key=lambda item: str(item.get("request_id") or "")),
        "actions": actions,
        "job": current_job(),
    }


def load_latest_decisions(reports_dir: Path) -> dict[str, dict[str, Any]]:
    path = reports_dir / "decisions.jsonl"
    latest: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return latest
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = str(payload.get("state_key") or "")
        if key:
            latest[key] = payload
    return latest


def load_actions(settings: Settings) -> dict[str, Any]:
    path = actions_path(settings)
    if not path.exists():
        return {"approved_recommendations": [], "sus_factory_events": []}
    try:
        payload = read_json(path)
        return payload if isinstance(payload, dict) else {"approved_recommendations": [], "sus_factory_events": []}
    except Exception:
        return {"approved_recommendations": [], "sus_factory_events": []}


def save_actions(settings: Settings, actions: dict[str, Any]) -> None:
    write_json(actions_path(settings), actions)


def actions_path(settings: Settings) -> Path:
    root = Path(settings.local_layout_root_dir)
    return root / settings.layout_reports_dir / "front_actions.json"


def current_job() -> dict[str, Any]:
    with JOB_LOCK:
        return to_jsonable(dict(JOB_STATE))


def start_job(mode: str) -> dict[str, Any]:
    with JOB_LOCK:
        if JOB_STATE["running"]:
            return {"ok": False, "error": "Ya hay un analisis en ejecucion"}
        JOB_STATE.update(
            {
                "running": True,
                "mode": mode,
                "logs": [],
                "outputs": None,
                "error": None,
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "finished_at": None,
            }
        )
    thread = threading.Thread(target=run_job, args=(mode,), daemon=True)
    thread.start()
    return {"ok": True, "message": "Analisis iniciado", "job": current_job()}


def append_log(message: str) -> None:
    with JOB_LOCK:
        logs = JOB_STATE.setdefault("logs", [])
        logs.append({"time": datetime.now().strftime("%H:%M:%S"), "message": message})
        JOB_STATE["logs"] = logs[-300:]


def run_job(mode: str) -> None:
    try:
        settings = Settings.from_env()
        if mode == "all":
            settings = replace(settings, processing_policy="reprocess_all")
        append_log("Preparando ejecucion local desde Flask.")
        outputs = run_folder_layout_pipeline(
            root_dir=settings.local_layout_root_dir,
            output_dir=None,
            settings=settings,
            log=append_log,
        )
        with JOB_LOCK:
            JOB_STATE["outputs"] = outputs
            JOB_STATE["running"] = False
            JOB_STATE["finished_at"] = datetime.now().isoformat(timespec="seconds")
    except Exception as exc:
        with JOB_LOCK:
            JOB_STATE["error"] = str(exc)
            JOB_STATE["running"] = False
            JOB_STATE["finished_at"] = datetime.now().isoformat(timespec="seconds")
        append_log(f"ERROR: {exc}")


def main() -> None:
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=False)
