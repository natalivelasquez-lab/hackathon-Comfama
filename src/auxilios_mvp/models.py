from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


CANONICAL_HISTORY_FIELDS = [
    "employee_id",
    "employee_name",
    "case_id",
    "benefit_code",
    "benefit_name",
    "beneficiary_id",
    "beneficiary_name",
    "relationship",
    "grant_date",
    "attention_date",
    "invoice_amount",
    "recognized_amount",
    "amount",
    "balance",
    "institution",
    "observations",
    "support_type",
    "payroll_concept",
    "status",
    "source_sheet",
    "source_row",
]


@dataclass
class MappingCandidate:
    canonical_field: str
    source_column: str | None
    confidence: float
    reason: str


@dataclass
class HistoryRecord:
    employee_id: str | None = None
    employee_name: str | None = None
    case_id: str | None = None
    benefit_code: str | None = None
    benefit_name: str | None = None
    beneficiary_id: str | None = None
    beneficiary_name: str | None = None
    relationship: str | None = None
    grant_date: str | None = None
    attention_date: str | None = None
    invoice_amount: float | None = None
    recognized_amount: float | None = None
    amount: float | None = None
    balance: float | None = None
    institution: str | None = None
    observations: str | None = None
    support_type: str | None = None
    payroll_concept: str | None = None
    status: str | None = None
    source_sheet: str | None = None
    source_row: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "employee_id": self.employee_id,
            "employee_name": self.employee_name,
            "case_id": self.case_id,
            "benefit_code": self.benefit_code,
            "benefit_name": self.benefit_name,
            "beneficiary_id": self.beneficiary_id,
            "beneficiary_name": self.beneficiary_name,
            "relationship": self.relationship,
            "grant_date": self.grant_date,
            "attention_date": self.attention_date,
            "invoice_amount": self.invoice_amount,
            "recognized_amount": self.recognized_amount,
            "amount": self.amount,
            "balance": self.balance,
            "institution": self.institution,
            "observations": self.observations,
            "support_type": self.support_type,
            "payroll_concept": self.payroll_concept,
            "status": self.status,
            "source_sheet": self.source_sheet,
            "source_row": self.source_row,
        }


@dataclass
class BenefitRule:
    benefit_code: str
    benefit_name: str
    concept_code: str | None = None
    aliases: list[str] = field(default_factory=list)
    applies_beneficiary: bool = False
    expected_documents: list[str] = field(default_factory=list)
    invoice_max_age_months: int | None = None
    formula_max_age_months: int | None = None
    periodicity_months: int | None = None
    max_count_period: int | None = None
    max_amount: float | None = None
    requires_history: bool = True
    acceptance_criteria: str = ""
    rejection_criteria: str = ""
    manual_review_criteria: str = ""


@dataclass
class RequestContext:
    request_id: str
    employee_id: str | None
    benefit_code: str | None
    concept_code: str | None
    source_path: str
    files: list[str]


@dataclass
class DocumentAnalysis:
    file_name: str
    document_type: str = "otro"
    text: str = ""
    extracted_fields: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)


@dataclass
class Recommendation:
    request_id: str
    employee_id: str | None
    benefit_code: str | None
    recommended_status: str
    summary: str
    reasons: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "employee_id": self.employee_id,
            "benefit_code": self.benefit_code,
            "recommended_status": self.recommended_status,
            "summary": self.summary,
            "reasons": self.reasons,
            "missing_information": self.missing_information,
            "evidence": self.evidence,
            "confidence": self.confidence,
        }


def parse_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date().isoformat()
        except ValueError:
            pass
    return text
