from __future__ import annotations

from .pipeline import run_folder_layout_pipeline
from .settings import Settings


def log(message: str) -> None:
    print(message, flush=True)


def run_from_env(settings: Settings | None = None) -> dict[str, str]:
    settings = settings or Settings.from_env()
    mode = settings.app_input_mode
    log("=== MVP Auxilios Calidad de Vida ===")
    log(f"Modo de entrada: {mode}")

    if mode == "local_layout":
        log(f"Procesando layout local: {settings.local_layout_root_dir}")
        return run_folder_layout_pipeline(
            root_dir=settings.local_layout_root_dir,
            output_dir=None,
            settings=settings,
            log=log,
        )

    raise RuntimeError("APP_INPUT_MODE invalido. Usa local_layout.")


def main() -> None:
    try:
        outputs = run_from_env()
    except (FileNotFoundError, NotADirectoryError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Recomendaciones JSON: {outputs['recommendations_json']}")
    print(f"Reporte CSV: {outputs['recommendations_csv']}")
    print("Listo.", flush=True)


if __name__ == "__main__":
    main()
