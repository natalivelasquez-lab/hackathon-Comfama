from __future__ import annotations

import csv
from pathlib import Path
import re

from .models import BenefitRule


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"si", "sí", "true", "1", "yes", "y"}


def _int(value: str | None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def _float(value: object) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    cleaned = re.sub(r"[^\d,.-]", "", str(value)).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _split_list(value: object) -> list[str]:
    text = "" if value is None else str(value)
    return [item.strip() for item in re.split(r"[;,]", text) if item.strip()]


def _concept(value: object) -> str | None:
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    return digits.zfill(4) if digits else text.upper()


def load_benefit_rules(path: str | Path) -> dict[str, BenefitRule]:
    target = Path(path)
    if target.suffix.lower() == ".csv":
        with target.open("r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
    else:
        import pandas as pd

        rows = pd.read_excel(target).fillna("").to_dict(orient="records")

    rules: dict[str, BenefitRule] = {}
    for row in rows:
        code = str(row.get("beneficio_codigo") or row.get("codigo") or "").strip()
        if not code:
            continue
        concept_code = _concept(row.get("concepto_codigo") or row.get("concepto") or row.get("codigo_concepto"))
        aliases = _split_list(row.get("aliases") or row.get("alias") or "")
        rule = BenefitRule(
            benefit_code=code,
            benefit_name=str(row.get("beneficio_nombre") or code).strip(),
            concept_code=concept_code,
            aliases=aliases,
            applies_beneficiary=_bool(row.get("aplica_beneficiario")),
            expected_documents=_split_list(row.get("documentos_esperados")),
            invoice_max_age_months=_int(row.get("vigencia_factura_meses")),
            formula_max_age_months=_int(row.get("vigencia_formula_meses")),
            periodicity_months=_int(row.get("periodicidad_meses")),
            max_count_period=_int(row.get("cantidad_maxima_periodo")),
            max_amount=_float(row.get("tope_monto") or row.get("monto_maximo") or row.get("valor_maximo")),
            requires_history=_bool(row.get("requiere_historico"), default=True),
            acceptance_criteria=str(row.get("criterios_aceptacion") or ""),
            rejection_criteria=str(row.get("criterios_rechazo") or ""),
            manual_review_criteria=str(row.get("criterios_revision_manual") or ""),
        )
        rules[code.upper()] = rule
        if concept_code:
            rules[concept_code.upper()] = rule
        for alias in aliases:
            rules[alias.upper()] = rule
    return rules
