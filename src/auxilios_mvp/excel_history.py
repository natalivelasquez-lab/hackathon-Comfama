from __future__ import annotations

import re
import warnings
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from .azure_openai import AzureOpenAIClient
from .schemas import CANONICAL_HISTORY_FIELDS, HistoryRecord, MappingCandidate, parse_date


FIELD_HINTS = {
    "employee_id": [
        "cc",
        "cedem",
        "cedula",
        "cédula",
        "documento",
        "identificacion",
        "identificación",
        "id empleado",
        "dni",
    ],
    "employee_name": ["nombre", "colaborador", "empleado", "trabajador", "titular"],
    "case_id": ["caso", "solicitud", "radicado", "folio"],
    "benefit_code": ["codigo auxilio", "código auxilio", "cod beneficio", "codigo beneficio"],
    "benefit_name": ["beneficio", "auxilio", "servicio", "tipo auxilio", "tipo de auxilio", "destino"],
    "beneficiary_id": ["documento beneficiario", "id beneficiario", "cedula beneficiario", "identificacion beneficiario"],
    "beneficiary_name": ["beneficiario", "nombre beneficiario", "hijo", "familiar"],
    "relationship": ["parentesco", "relacion", "relación", "quien exacto", "quién exacto"],
    "grant_date": ["fecha", "fecha pago", "fecha otorgamiento", "fecha aprobacion", "fecha aprobación", "periodo"],
    "attention_date": ["fecha atencion", "fecha atención"],
    "invoice_amount": ["valor factura", "monto factura", "valor soporte"],
    "recognized_amount": ["valor reconocimiento", "valor reconocido", "valor aprobado", "monto aprobado"],
    "amount": ["valor reconocimiento", "valor reconocido", "valor aprobado", "monto aprobado"],
    "balance": ["saldo"],
    "institution": ["institucion", "institución", "entidad", "proveedor"],
    "observations": ["observaciones", "novedades", "comentarios"],
    "support_type": ["tipo de soporte", "soporte"],
    "payroll_concept": ["concepto nomina", "concepto nómina", "concepto"],
    "status": ["estado", "resultado", "decision", "decisión", "aprobado", "estatus"],
}


def _norm(text: Any) -> str:
    value = "" if text is None else str(text)
    value = value.strip().lower()
    value = value.replace("\n", " ")
    value = re.sub(r"\s+", " ", value)
    return value


def _score_column(field: str, column_name: str, sample_values: list[Any]) -> tuple[float, str]:
    normalized = _norm(column_name)
    hints = FIELD_HINTS.get(field, [])
    score = 0.0
    reasons: list[str] = []
    for hint in hints:
        if hint in normalized:
            score = max(score, 0.85)
            reasons.append(f"nombre de columna contiene '{hint}'")

    name_required_fields = {
        "case_id",
        "invoice_amount",
        "recognized_amount",
        "balance",
        "institution",
        "observations",
        "support_type",
        "payroll_concept",
        "relationship",
    }
    if field in name_required_fields and score == 0.0:
        return 0.0, "campo opcional requiere coincidencia por nombre de columna"

    samples = [_norm(v) for v in sample_values if str(v).strip() and str(v) != "nan"][:20]
    if field.endswith("_id") and any(
        token in normalized for token in ["fecha", "acta", "caso", "quincena", "cenfro", "nº per", "no per", "n per"]
    ):
        return 0.0, "columna operativa/fecha no debe mapearse como identificador"
    if field == "beneficiary_id" and not any(
        token in normalized for token in ["beneficiario", "familiar", "hijo", "dependiente"]
    ):
        return 0.0, "identificador de beneficiario requiere una columna de beneficiario/familiar"
    if field == "status" and any(token in normalized for token in ["diagnostico", "diagnóstico"]):
        return 0.0, "diagnostico no debe mapearse como estado"
    if field == "employee_id" and normalized in {"cc", "cedem"}:
        score = max(score, 0.85)
        reasons.append(f"columna '{normalized}' usada como identificador del empleado")
    if field.endswith("_id") and samples:
        numericish = sum(1 for v in samples if re.sub(r"\D", "", v).isdigit())
        ratio = numericish / max(len(samples), 1)
        if ratio >= 0.7:
            score = max(score, 0.65)
            reasons.append("valores parecen identificadores numericos")
    if field == "amount":
        return 0.0, "amount se deriva de recognized_amount o invoice_amount"
    if field in {"invoice_amount", "recognized_amount", "balance"} and samples and score > 0:
        moneyish = sum(1 for v in samples if re.search(r"\d", v) and not re.search(r"[a-zA-Z]{4,}", v))
        if moneyish / max(len(samples), 1) >= 0.7:
            score = max(score, 0.65)
            reasons.append("valores parecen montos")
    if field in {"grant_date", "attention_date"} and samples:
        dateish = sum(
            1
            for v in samples
            if re.search(r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}", v) or "00:00:00" in v
        )
        if dateish / max(len(samples), 1) >= 0.4:
            score = max(score, 0.65)
            reasons.append("valores parecen fechas")
    if field == "status" and samples:
        statusish = sum(1 for v in samples if any(s in v for s in ["apro", "rech", "pend", "pag", "neg", "ok"]))
        if statusish / max(len(samples), 1) >= 0.3:
            score = max(score, 0.6)
            reasons.append("valores parecen estados")

    return score, "; ".join(reasons) or "sin coincidencias fuertes"


def _find_header_row(raw: pd.DataFrame) -> int:
    best_idx = 0
    best_score = -1
    for idx in range(min(len(raw), 12)):
        row = raw.iloc[idx].tolist()
        non_empty = [v for v in row if str(v).strip() and str(v) != "nan"]
        text = " ".join(_norm(v) for v in non_empty)
        keyword_hits = sum(1 for hints in FIELD_HINTS.values() for hint in hints if hint in text)
        score = len(non_empty) + keyword_hits * 3
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx


def load_excel_tables(path: str | Path) -> list[dict[str, Any]]:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Data Validation extension is not supported and will be removed",
            category=UserWarning,
            module="openpyxl.worksheet._reader",
        )
        xl = pd.ExcelFile(path)
        sheet_names = xl.sheet_names

    tables: list[dict[str, Any]] = []
    for sheet in sheet_names:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Data Validation extension is not supported and will be removed",
                category=UserWarning,
                module="openpyxl.worksheet._reader",
            )
            raw = pd.read_excel(path, sheet_name=sheet, header=None)
        if raw.dropna(how="all").empty:
            continue
        header_idx = _find_header_row(raw)
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Data Validation extension is not supported and will be removed",
                category=UserWarning,
                module="openpyxl.worksheet._reader",
            )
            df = pd.read_excel(path, sheet_name=sheet, header=header_idx)
        df = df.dropna(how="all")
        df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed")]]
        if df.empty or len(df.columns) == 0:
            continue
        tables.append({"sheet": sheet, "header_row": header_idx + 1, "dataframe": df})
    return tables


def infer_mapping_for_table(df: pd.DataFrame) -> list[MappingCandidate]:
    used_columns: set[str] = set()
    candidates: list[MappingCandidate] = []
    inference_order = [
        "employee_id",
        "employee_name",
        "case_id",
        "benefit_code",
        "benefit_name",
        "grant_date",
        "attention_date",
        "recognized_amount",
        "invoice_amount",
        "balance",
        "institution",
        "relationship",
        "observations",
        "support_type",
        "payroll_concept",
        "status",
        "beneficiary_id",
        "beneficiary_name",
    ]
    candidate_by_field: dict[str, MappingCandidate] = {}
    for field in inference_order:
        if field in {"source_sheet", "source_row"}:
            continue
        best_col = None
        best_score = 0.0
        best_reason = "sin columna candidata"
        for column in df.columns:
            col_name = str(column)
            if col_name in used_columns:
                continue
            samples = df[column].dropna().head(30).tolist()
            score, reason = _score_column(field, col_name, samples)
            if score > best_score:
                best_col = col_name
                best_score = score
                best_reason = reason
        if best_score >= 0.55:
            used_columns.add(best_col or "")
            candidate_by_field[field] = MappingCandidate(field, best_col, round(best_score, 2), best_reason)
        else:
            candidate_by_field[field] = MappingCandidate(field, None, round(best_score, 2), best_reason)
    for field in CANONICAL_HISTORY_FIELDS:
        if field in {"source_sheet", "source_row"}:
            continue
        candidates.append(candidate_by_field.get(field, MappingCandidate(field, None, 0.0, "sin evaluar")))
    return candidates


def improve_mapping_with_ai(
    *,
    ai_client: AzureOpenAIClient | None,
    table_profile: dict[str, Any],
    mapping: list[MappingCandidate],
) -> list[MappingCandidate]:
    if not ai_client or not ai_client.available():
        return mapping
    prompt = Path("prompts/mapear_historico_excel.txt").read_text(encoding="utf-8")
    payload = {
        "task": "Inferir mapeo de columnas de un historico de auxilios a campos canonicos.",
        "canonical_fields": CANONICAL_HISTORY_FIELDS,
        "table_profile": table_profile,
        "initial_mapping": [asdict(m) for m in mapping],
        "expected_output": {
            "mapping": [
                {
                    "canonical_field": "employee_id",
                    "source_column": "Cedula",
                    "confidence": 0.0,
                    "reason": "explicacion breve",
                }
            ]
        },
    }
    response = ai_client.chat_json(
        deployment=ai_client.settings.azure_openai_deployment_text,
        system_prompt=prompt,
        user_payload=payload,
    )
    if not response or not isinstance(response.get("mapping"), list):
        return mapping
    improved: list[MappingCandidate] = []
    for item in response["mapping"]:
        field = item.get("canonical_field")
        if field not in CANONICAL_HISTORY_FIELDS:
            continue
        improved.append(
            MappingCandidate(
                canonical_field=field,
                source_column=item.get("source_column"),
                confidence=float(item.get("confidence") or 0),
                reason=str(item.get("reason") or "mapeo sugerido por IA"),
            )
        )
    return improved or mapping


def normalize_history_excel(
    path: str | Path,
    *,
    ai_client: AzureOpenAIClient | None = None,
    sample_rows: int = 8,
) -> dict[str, Any]:
    tables = load_excel_tables(path)
    all_records: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    warnings: list[str] = []

    for table in tables:
        sheet = table["sheet"]
        df: pd.DataFrame = table["dataframe"]
        profile = {
            "sheet": sheet,
            "header_row": table["header_row"],
            "columns": [str(c) for c in df.columns],
            "sample_rows": df.head(sample_rows).fillna("").to_dict(orient="records"),
        }
        mapping = infer_mapping_for_table(df)
        mapping = improve_mapping_with_ai(ai_client=ai_client, table_profile=profile, mapping=mapping)
        mapping_by_field = {m.canonical_field: m.source_column for m in mapping if m.source_column}
        if not mapping_by_field.get("employee_id") or not mapping_by_field.get("benefit_name"):
            warnings.append(
                f"Hoja '{sheet}': omitida porque no parece historico transaccional "
                "(no se identifico empleado y beneficio)"
            )
            continue

        mappings.append(
            {
                "sheet": sheet,
                "header_row": table["header_row"],
                "mapping": [asdict(m) for m in mapping],
            }
        )

        required = ["employee_id", "benefit_name", "grant_date"]
        missing_required = [field for field in required if not mapping_by_field.get(field)]
        if missing_required:
            warnings.append(f"Hoja '{sheet}': no se mapearon campos clave: {', '.join(missing_required)}")

        for row_idx, row in df.iterrows():
            record = HistoryRecord(source_sheet=sheet, source_row=int(row_idx) + table["header_row"] + 1)
            for field, source_col in mapping_by_field.items():
                value = row.get(source_col)
                if pd.isna(value):
                    value = None
                if field in {"grant_date", "attention_date"}:
                    value = parse_date(value)
                elif field in {"amount", "invoice_amount", "recognized_amount", "balance"} and value is not None:
                    cleaned = re.sub(r"[^\d,.-]", "", str(value)).replace(",", ".")
                    try:
                        value = float(cleaned)
                    except ValueError:
                        value = None
                elif value is not None:
                    value = str(value).strip()
                setattr(record, field, value)
            if record.recognized_amount is not None:
                record.amount = record.recognized_amount
            elif record.amount is None and record.invoice_amount is not None:
                record.amount = record.invoice_amount
            if not record.status:
                record.status = "REGISTRO_HISTORICO"
            if any(record.to_dict().get(f) for f in ["employee_id", "benefit_code", "benefit_name"]):
                all_records.append(record.to_dict())

    confidence_values = [
        item["confidence"]
        for sheet_mapping in mappings
        for item in sheet_mapping["mapping"]
        if item.get("source_column")
    ]
    mapping_confidence = round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.0
    return {
        "source_file": str(path),
        "mapping_confidence": mapping_confidence,
        "records": all_records,
        "mappings": mappings,
        "warnings": warnings,
    }
