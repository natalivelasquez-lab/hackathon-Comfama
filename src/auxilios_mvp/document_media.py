from __future__ import annotations

import base64
from pathlib import Path
from typing import Any


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _image_part(mime_type: str, data: bytes) -> dict[str, Any]:
    encoded = base64.b64encode(data).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
    }


def _read_image(path: Path) -> tuple[list[dict[str, Any]], list[str], str]:
    mime_type = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else f"image/{path.suffix.lower()[1:]}"
    return [_image_part(mime_type, path.read_bytes())], [], ""


def _read_pdf(path: Path, *, max_pages: int, max_text_chars: int) -> tuple[list[dict[str, Any]], list[str], str]:
    warnings: list[str] = []
    parts: list[dict[str, Any]] = []
    text_parts: list[str] = []

    try:
        import fitz
    except Exception:
        return (
            [],
            ["No esta instalado PyMuPDF; no se pueden renderizar paginas PDF para analisis omnimodal"],
            "",
        )

    try:
        document = fitz.open(str(path))
    except Exception as exc:
        return [], [f"No fue posible abrir el PDF para analisis omnimodal: {exc}"], ""

    page_count = min(len(document), max_pages)
    for index in range(page_count):
        page = document[index]
        page_text = (page.get_text("text") or "").strip()
        if page_text:
            text_parts.append(f"--- pagina {index + 1} ---\n{page_text}")
        try:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            parts.append(_image_part("image/png", pixmap.tobytes("png")))
        except Exception as exc:
            warnings.append(f"No fue posible renderizar pagina {index + 1} del PDF: {exc}")

    if len(document) > max_pages:
        warnings.append(f"Solo se enviaron las primeras {max_pages} paginas del PDF al modelo")

    text = "\n\n".join(text_parts).strip()
    if not text:
        warnings.append("El PDF no entrego texto extraible; se enviaron imagenes de pagina al modelo")

    return parts, warnings, text[:max_text_chars]


def build_document_content(
    path: str | Path,
    *,
    max_pages: int = 3,
    max_text_chars: int = 12000,
) -> tuple[list[dict[str, Any]], list[str], str]:
    target = Path(path)
    warnings: list[str] = []
    media_parts: list[dict[str, Any]] = []
    text = ""

    if target.suffix.lower() == ".pdf":
        media_parts, warnings, text = _read_pdf(target, max_pages=max_pages, max_text_chars=max_text_chars)
    elif target.suffix.lower() in IMAGE_EXTENSIONS:
        media_parts, warnings, text = _read_image(target)
    else:
        warnings.append(f"Tipo de archivo no soportado para analisis documental: {target.suffix or target.name}")

    text_part = {
        "type": "text",
        "text": (
            f"Archivo: {target.name}\n"
            f"Tipo local de archivo: {target.suffix.lower() or 'sin_extension'}\n\n"
            "Texto extraido del documento, si existe:\n"
            f"{text or '[sin texto extraido]'}"
        ),
    }
    return [text_part, *media_parts], warnings, text
