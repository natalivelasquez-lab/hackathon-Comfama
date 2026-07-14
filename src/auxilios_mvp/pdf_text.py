from __future__ import annotations

from pathlib import Path


def extract_pdf_text(path: str | Path) -> tuple[str, list[str]]:
    warnings: list[str] = []
    target = Path(path)
    if target.suffix.lower() != ".pdf":
        return "", [f"Archivo no PDF omitido: {target.name}"]

    try:
        from pypdf import PdfReader

        reader = PdfReader(str(target))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        text = "\n".join(parts).strip()
        if not text:
            warnings.append("PDF sin texto extraible localmente; se requiere analisis omnimodal")
        return text, warnings
    except Exception as exc:
        return "", [f"No fue posible extraer texto local del PDF: {exc}"]
