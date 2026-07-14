from __future__ import annotations

import argparse

from .azure_openai import AzureOpenAIClient
from .excel_history import normalize_history_excel
from .json_utils import write_json
from .pipeline import run_folder_layout_pipeline, run_local_pipeline
from .settings import Settings


def cmd_normalize_history(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    ai_client = AzureOpenAIClient(settings)
    result = normalize_history_excel(args.input, ai_client=ai_client)
    write_json(args.output, result)
    print(f"Historico normalizado: {args.output}")
    print(f"Registros: {len(result.get('records', []))}")
    print(f"Confianza de mapeo: {result.get('mapping_confidence')}")
    for warning in result.get("warnings", []):
        print(f"WARNING: {warning}")


def cmd_run_local(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    outputs = run_local_pipeline(
        requests_dir=args.requests_dir,
        history_json=args.history_json,
        benefits_file=args.benefits_excel,
        output_dir=args.output_dir,
        settings=settings,
    )
    print(f"Recomendaciones JSON: {outputs['recommendations_json']}")
    print(f"Reporte CSV: {outputs['recommendations_csv']}")


def cmd_run_folder_layout(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    root_dir = args.root_dir or settings.local_layout_root_dir
    outputs = run_folder_layout_pipeline(
        root_dir=root_dir,
        output_dir=args.output_dir,
        settings=settings,
    )
    print(f"Recomendaciones JSON: {outputs['recommendations_json']}")
    print(f"Reporte CSV: {outputs['recommendations_csv']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="auxilios-mvp")
    sub = parser.add_subparsers(required=True)

    normalize = sub.add_parser("normalize-history", help="Convierte Excel historico desconocido a JSON canonico")
    normalize.add_argument("--input", required=True)
    normalize.add_argument("--output", required=True)
    normalize.set_defaults(func=cmd_normalize_history)

    run_local = sub.add_parser("run-local", help="Procesa solicitudes desde una carpeta local")
    run_local.add_argument("--requests-dir", required=True)
    run_local.add_argument("--history-json", required=True)
    run_local.add_argument("--benefits-excel", default="config/beneficios.csv")
    run_local.add_argument("--output-dir", required=True)
    run_local.set_defaults(func=cmd_run_local)

    run_layout = sub.add_parser(
        "run-folder-layout",
        help="Procesa una estructura 00_Config/01_EntradaSolicitudes/02_SalidaReportes",
    )
    run_layout.add_argument("--root-dir")
    run_layout.add_argument("--output-dir")
    run_layout.set_defaults(func=cmd_run_folder_layout)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except (FileNotFoundError, NotADirectoryError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
