from __future__ import annotations

from pathlib import Path
import re

from .schemas import RequestContext


def parse_request_folder(path: str | Path) -> RequestContext:
    target = Path(path)
    parts = target.name.split("_")
    employee_id = parts[0] if parts else None
    request_id = parts[-1] if len(parts) >= 3 else target.name
    raw_benefit = "_".join(parts[1:-1]) if len(parts) >= 3 else None
    digits = re.sub(r"\D", "", raw_benefit or "")
    concept_code = digits.zfill(4) if digits and len(digits) <= 4 else None
    benefit_code = concept_code or raw_benefit
    files = [str(p) for p in target.iterdir() if p.is_file()]
    return RequestContext(
        request_id=request_id,
        employee_id=employee_id,
        benefit_code=benefit_code,
        concept_code=concept_code,
        source_path=str(target),
        files=files,
    )


def list_request_folders(requests_dir: str | Path) -> list[RequestContext]:
    root = Path(requests_dir)
    contexts = []
    for child in sorted(root.iterdir()):
        if child.is_dir():
            contexts.append(parse_request_folder(child))
    return contexts
