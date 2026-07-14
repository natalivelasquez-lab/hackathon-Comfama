from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .json_utils import to_jsonable
from .schemas import Recommendation


def _cell(value: Any) -> str:
    safe_value = to_jsonable(value)
    if safe_value is None:
        return ""
    if isinstance(safe_value, str):
        return safe_value
    if isinstance(safe_value, int | float | bool):
        return str(safe_value)
    return json.dumps(safe_value, ensure_ascii=False)


def _join_cell(values: list[Any]) -> str:
    return " | ".join(_cell(value) for value in values if _cell(value))


def write_recommendations_csv(path: str | Path, recommendations: list[Recommendation]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "request_id",
                "employee_id",
                "benefit_code",
                "recommended_status",
                "confidence",
                "summary",
                "reasons",
                "missing_information",
            ],
        )
        writer.writeheader()
        for item in recommendations:
            writer.writerow(
                {
                    "request_id": item.request_id,
                    "employee_id": item.employee_id,
                    "benefit_code": item.benefit_code,
                    "recommended_status": item.recommended_status,
                    "confidence": item.confidence,
                    "summary": item.summary,
                    "reasons": _join_cell(item.reasons),
                    "missing_information": _join_cell(item.missing_information),
                }
            )
