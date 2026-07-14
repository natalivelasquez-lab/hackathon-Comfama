from __future__ import annotations

import csv
from pathlib import Path

from .models import Recommendation


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
                    "reasons": " | ".join(item.reasons),
                    "missing_information": " | ".join(item.missing_information),
                }
            )
