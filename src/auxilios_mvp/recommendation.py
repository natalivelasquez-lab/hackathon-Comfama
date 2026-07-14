from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from .azure_openai import AzureOpenAIClient
from .models import BenefitRule, DocumentAnalysis, Recommendation, RequestContext
from .settings import read_prompt


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def _parse_amount(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, int | float):
        return float(value)
    cleaned = re.sub(r"[^\d,.-]", "", str(value)).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _ids_equal(left: Any, right: Any) -> bool:
    left_digits = re.sub(r"\D", "", str(left or ""))
    right_digits = re.sub(r"\D", "", str(right or ""))
    return bool(left_digits and right_digits and left_digits == right_digits)


def _doc_dates(doc: DocumentAnalysis) -> list[date]:
    fields = doc.extracted_fields or {}
    values: list[Any] = [
        fields.get("issue_date"),
        fields.get("date"),
        fields.get("document_date"),
        fields.get("fecha"),
    ]
    values.extend(fields.get("possible_dates") or [])
    parsed = [_parse_date(value) for value in values]
    return [value for value in parsed if value is not None]


def _doc_amounts(doc: DocumentAnalysis) -> list[float]:
    fields = doc.extracted_fields or {}
    values: list[Any] = [
        fields.get("total_amount"),
        fields.get("amount"),
        fields.get("invoice_amount"),
        fields.get("valor"),
    ]
    values.extend(fields.get("possible_amounts") or [])
    parsed = [_parse_amount(value) for value in values]
    return [value for value in parsed if value is not None]


def _doc_ids(doc: DocumentAnalysis, *field_names: str) -> list[str]:
    fields = doc.extracted_fields or {}
    ids: list[str] = []
    for field in field_names:
        value = fields.get(field)
        if value:
            ids.append(str(value))
    ids.extend(str(value) for value in fields.get("possible_ids") or [])
    return ids


def _rule_eval(name: str, status: str, reason: str, evidence: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"rule": name, "status": status, "reason": reason}
    if evidence is not None:
        payload["evidence"] = evidence
    return payload


def _history_matches(
    history_records: list[dict[str, Any]],
    *,
    employee_id: str | None,
    benefit_code: str | None,
    benefit_name: str | None,
    concept_code: str | None,
    beneficiary_id: str | None = None,
) -> list[dict[str, Any]]:
    matches = []
    for record in history_records:
        if employee_id and not _ids_equal(record.get("employee_id"), employee_id):
            continue
        if beneficiary_id and not _ids_equal(record.get("beneficiary_id"), beneficiary_id):
            continue
        record_code = str(record.get("benefit_code") or "").strip().upper()
        record_name = str(record.get("benefit_name") or "").strip().upper()
        record_concept = str(record.get("payroll_concept") or "").strip().upper()
        code = str(benefit_code or "").strip().upper()
        name = str(benefit_name or "").strip().upper()
        concept = str(concept_code or "").strip().upper()
        if code and record_code and code == record_code:
            matches.append(record)
        elif concept and record_concept and concept == record_concept:
            matches.append(record)
        elif name and record_name and (name in record_name or record_name in name):
            matches.append(record)
    return matches


def _recent_history(
    history_matches: list[dict[str, Any]],
    periodicity_months: int | None,
) -> list[dict[str, Any]]:
    if not periodicity_months:
        return []
    today = date.today()
    recent = []
    for item in history_matches:
        grant_date = _parse_date(item.get("grant_date"))
        if grant_date and _months_between(grant_date, today) < periodicity_months:
            recent.append(item)
    return recent


def _extract_beneficiary_id(documents: list[DocumentAnalysis], employee_id: str | None) -> str | None:
    for doc in documents:
        fields = doc.extracted_fields or {}
        for field in ("beneficiary_id", "beneficiario_id", "id_beneficiario"):
            value = fields.get(field)
            if value and not _ids_equal(value, employee_id):
                return str(value)
    for doc in documents:
        for candidate in _doc_ids(doc, "beneficiary_id"):
            if candidate and not _ids_equal(candidate, employee_id):
                return str(candidate)
    return None


def _evaluate_rules(
    *,
    request: RequestContext,
    documents: list[DocumentAnalysis],
    benefit_rule: BenefitRule,
    history_records: list[dict[str, Any]],
) -> tuple[str, list[str], list[str], list[dict[str, Any]], float, list[dict[str, Any]]]:
    reasons: list[str] = []
    missing: list[str] = []
    evidence: list[dict[str, Any]] = []
    rule_results: list[dict[str, Any]] = []
    confidence = 0.65

    found_types = {doc.document_type for doc in documents}
    missing_docs = [doc_type for doc_type in benefit_rule.expected_documents if doc_type not in found_types]
    if missing_docs:
        missing.extend(f"Documento esperado no detectado: {doc_type}" for doc_type in missing_docs)
        rule_results.append(
            _rule_eval(
                "documentos_requeridos",
                "REVISION",
                "Faltan documentos obligatorios para el auxilio.",
                {"esperados": benefit_rule.expected_documents, "detectados": sorted(found_types)},
            )
        )
    else:
        rule_results.append(
            _rule_eval(
                "documentos_requeridos",
                "APROBAR",
                "Todos los tipos documentales esperados fueron detectados.",
                {"esperados": benefit_rule.expected_documents, "detectados": sorted(found_types)},
            )
        )

    for doc in documents:
        evidence.append(
            {
                "file_name": doc.file_name,
                "document_type": doc.document_type,
                "confidence": doc.confidence,
                "warnings": doc.warnings,
            }
        )
        if doc.warnings:
            reasons.append(f"{doc.file_name}: {'; '.join(doc.warnings)}")
            rule_results.append(
                _rule_eval(
                    "calidad_documental",
                    "REVISION",
                    "El documento tiene advertencias de lectura o calidad.",
                    {"file_name": doc.file_name, "warnings": doc.warnings},
                )
            )
        if doc.confidence < 0.5:
            reasons.append(f"{doc.file_name}: baja confianza de clasificacion/extraccion")
            rule_results.append(
                _rule_eval(
                    "confianza_extraccion",
                    "REVISION",
                    "La clasificacion/extraccion documental tiene baja confianza.",
                    {"file_name": doc.file_name, "confidence": doc.confidence},
                )
            )

    if benefit_rule.requires_history and not history_records:
        missing.append("Historico no disponible o vacio")
        rule_results.append(
            _rule_eval(
                "historico_disponible",
                "REVISION",
                "No hay historico disponible para validar elegibilidad.",
            )
        )
    else:
        rule_results.append(
            _rule_eval(
                "historico_disponible",
                "APROBAR",
                "El historico esta disponible para consulta.",
                {"registros": len(history_records)},
            )
        )

    employee_matches = _history_matches(
        history_records,
        employee_id=request.employee_id,
        benefit_code=benefit_rule.benefit_code,
        benefit_name=benefit_rule.benefit_name,
        concept_code=benefit_rule.concept_code or request.concept_code,
    )
    recent_employee = _recent_history(employee_matches, benefit_rule.periodicity_months)
    max_previous_allowed = max((benefit_rule.max_count_period or 1) - 1, 0)
    if benefit_rule.periodicity_months and len(recent_employee) > max_previous_allowed:
        reasons.append(
            f"Historico indica {len(recent_employee)} otorgamiento(s) previo(s) dentro de "
            f"{benefit_rule.periodicity_months} meses"
        )
        evidence.append({"employee_history_matches": recent_employee[:5]})
        rule_results.append(
            _rule_eval(
                "periodicidad_empleado",
                "RECHAZAR",
                "El empleado supera la cantidad permitida en el periodo configurado.",
                {
                    "periodicidad_meses": benefit_rule.periodicity_months,
                    "cantidad_maxima_periodo": benefit_rule.max_count_period,
                    "maximo_previo_permitido": max_previous_allowed,
                    "coincidencias_periodo": len(recent_employee),
                },
            )
        )
    else:
        rule_results.append(
            _rule_eval(
                "periodicidad_empleado",
                "APROBAR",
                "No se encontraron otorgamientos del empleado que incumplan la periodicidad.",
                {
                    "periodicidad_meses": benefit_rule.periodicity_months,
                    "coincidencias_periodo": len(recent_employee),
                },
            )
        )

    beneficiary_id = _extract_beneficiary_id(documents, request.employee_id)
    if benefit_rule.applies_beneficiary:
        if not beneficiary_id:
            missing.append("Identificacion del beneficiario")
            rule_results.append(
                _rule_eval(
                    "beneficiario_requerido",
                    "REVISION",
                    "El auxilio aplica a beneficiario, pero no se detecto identificacion de beneficiario.",
                )
            )
        else:
            beneficiary_matches = _history_matches(
                history_records,
                employee_id=request.employee_id,
                benefit_code=benefit_rule.benefit_code,
                benefit_name=benefit_rule.benefit_name,
                concept_code=benefit_rule.concept_code or request.concept_code,
                beneficiary_id=beneficiary_id,
            )
            recent_beneficiary = _recent_history(beneficiary_matches, benefit_rule.periodicity_months)
            if benefit_rule.periodicity_months and len(recent_beneficiary) > max_previous_allowed:
                reasons.append(
                    f"Historico indica beneficio previo para beneficiario {beneficiary_id} "
                    f"dentro de {benefit_rule.periodicity_months} meses"
                )
                evidence.append({"beneficiary_history_matches": recent_beneficiary[:5]})
                rule_results.append(
                    _rule_eval(
                        "periodicidad_beneficiario",
                        "RECHAZAR",
                        "El beneficiario supera la cantidad permitida en el periodo configurado.",
                        {
                            "beneficiary_id": beneficiary_id,
                            "periodicidad_meses": benefit_rule.periodicity_months,
                            "maximo_previo_permitido": max_previous_allowed,
                            "coincidencias_periodo": len(recent_beneficiary),
                        },
                    )
                )
            else:
                rule_results.append(
                    _rule_eval(
                        "periodicidad_beneficiario",
                        "APROBAR",
                        "No se encontraron otorgamientos del beneficiario que incumplan la periodicidad.",
                        {"beneficiary_id": beneficiary_id, "coincidencias_periodo": len(recent_beneficiary)},
                    )
                )

    for doc_type, max_age in (
        ("factura", benefit_rule.invoice_max_age_months),
        ("formula_medica", benefit_rule.formula_max_age_months),
    ):
        if not max_age or doc_type not in found_types:
            continue
        docs_of_type = [doc for doc in documents if doc.document_type == doc_type]
        dates = [doc_date for doc in docs_of_type for doc_date in _doc_dates(doc)]
        if not dates:
            missing.append(f"Fecha de {doc_type}")
            rule_results.append(
                _rule_eval(
                    f"vigencia_{doc_type}",
                    "REVISION",
                    f"No se detecto fecha para validar vigencia de {doc_type}.",
                )
            )
            continue
        newest = max(dates)
        age = _months_between(newest, date.today())
        if age > max_age:
            reasons.append(f"{doc_type} vencido: fecha {newest.isoformat()}, maximo {max_age} meses")
            rule_results.append(
                _rule_eval(
                    f"vigencia_{doc_type}",
                    "RECHAZAR",
                    f"El documento supera la vigencia maxima configurada de {max_age} meses.",
                    {"fecha": newest.isoformat(), "edad_meses": age, "maximo_meses": max_age},
                )
            )
        else:
            rule_results.append(
                _rule_eval(
                    f"vigencia_{doc_type}",
                    "APROBAR",
                    "El documento esta dentro de la vigencia configurada.",
                    {"fecha": newest.isoformat(), "edad_meses": age, "maximo_meses": max_age},
                )
            )

    if benefit_rule.max_amount is not None:
        amounts = [amount for doc in documents for amount in _doc_amounts(doc)]
        if not amounts:
            missing.append("Valor del soporte")
            rule_results.append(
                _rule_eval("tope_monto", "REVISION", "No se detecto monto para validar tope del auxilio.")
            )
        elif max(amounts) > benefit_rule.max_amount:
            reasons.append(f"Valor del soporte supera el tope configurado: {max(amounts)} > {benefit_rule.max_amount}")
            rule_results.append(
                _rule_eval(
                    "tope_monto",
                    "RECHAZAR",
                    "El valor detectado supera el monto maximo configurado.",
                    {"valor_detectado": max(amounts), "tope_monto": benefit_rule.max_amount},
                )
            )
        else:
            rule_results.append(
                _rule_eval(
                    "tope_monto",
                    "APROBAR",
                    "El valor detectado no supera el monto maximo configurado.",
                    {"valor_detectado": max(amounts), "tope_monto": benefit_rule.max_amount},
                )
            )

    statuses = {item["status"] for item in rule_results}
    if "RECHAZAR" in statuses:
        final_status = "RECHAZAR"
        confidence = max(confidence, 0.75)
    elif "REVISION" in statuses:
        final_status = "REVISION"
        confidence = min(confidence, 0.45)
    else:
        final_status = "APROBAR"
        reasons.append("Todas las reglas evaluadas cumplen con la informacion disponible")
        confidence = max(confidence, 0.75)

    evidence.append(
        {
            "rules_evaluated": rule_results,
            "benefit_rule": {
                "benefit_code": benefit_rule.benefit_code,
                "benefit_name": benefit_rule.benefit_name,
                "concept_code": benefit_rule.concept_code,
                "applies_beneficiary": benefit_rule.applies_beneficiary,
                "periodicity_months": benefit_rule.periodicity_months,
                "max_count_period": benefit_rule.max_count_period,
                "max_amount": benefit_rule.max_amount,
                "acceptance_criteria": benefit_rule.acceptance_criteria,
                "rejection_criteria": benefit_rule.rejection_criteria,
                "manual_review_criteria": benefit_rule.manual_review_criteria,
            },
        }
    )
    return final_status, reasons, missing, evidence, confidence, rule_results


def recommend(
    *,
    request: RequestContext,
    documents: list[DocumentAnalysis],
    benefit_rule: BenefitRule | None,
    history_records: list[dict[str, Any]],
    ai_client: AzureOpenAIClient | None = None,
) -> Recommendation:
    if not benefit_rule:
        return Recommendation(
            request_id=request.request_id,
            employee_id=request.employee_id,
            benefit_code=request.benefit_code,
            recommended_status="REVISION",
            summary="No se encontro configuracion para el beneficio solicitado.",
            reasons=["Beneficio no parametrizado o codigo no reconocido"],
            missing_information=["Configuracion del beneficio"],
            evidence=[
                _rule_eval(
                    "beneficio_parametrizado",
                    "REVISION",
                    "El codigo o alias del beneficio no existe en beneficios.csv.",
                )
            ],
            confidence=0.2,
        )

    status, reasons, missing, evidence, confidence, rule_results = _evaluate_rules(
        request=request,
        documents=documents,
        benefit_rule=benefit_rule,
        history_records=history_records,
    )

    recommendation = Recommendation(
        request_id=request.request_id,
        employee_id=request.employee_id,
        benefit_code=benefit_rule.benefit_code,
        recommended_status=status,
        summary=f"Recomendacion {status} para {benefit_rule.benefit_name}",
        reasons=reasons,
        missing_information=missing,
        evidence=evidence,
        confidence=confidence,
    )

    if ai_client and ai_client.available():
        response = ai_client.chat_json(
            deployment=ai_client.settings.azure_openai_deployment_text,
            system_prompt=read_prompt("prompts/generar_recomendacion.txt"),
            user_payload={
                "request": request.__dict__,
                "benefit_rule": benefit_rule.__dict__,
                "documents": [doc.__dict__ for doc in documents],
                "rules_evaluated": rule_results,
                "initial_recommendation": recommendation.to_dict(),
            },
        )
        if response and response.get("recommended_status") in {"APROBAR", "RECHAZAR", "REVISION"}:
            recommendation.recommended_status = response["recommended_status"]
            recommendation.summary = str(response.get("summary") or recommendation.summary)
            recommendation.reasons = list(response.get("reasons") or recommendation.reasons)
            recommendation.missing_information = list(
                response.get("missing_information") or recommendation.missing_information
            )
            recommendation.evidence = list(response.get("evidence") or recommendation.evidence)
            recommendation.confidence = float(response.get("confidence") or recommendation.confidence)

    return recommendation
