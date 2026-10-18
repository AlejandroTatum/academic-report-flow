#!/usr/bin/env python3
"""Backend router for academic reports.

Chooses LaTeX/visual/DOCX routing based on report.yml. LaTeX and DOCX both have
a fully generic ``body.md`` builder; visual jobs are still validated with the
shared gates because their builders depend on the specific teacher/template
task.

Unsupported backends fail fast with a non-zero exit and a clear message
instead of silently falling through to validation.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import approval_marker
from approval_marker import (
    approval_state,
    draft_record_path,
    render_digest,
    render_record_path,
    sha256_file,
    write_draft_record,
    write_render_record,
)
from report_config import load_report_config
from validate_report import validate

# ---------------------------------------------------------------------------
# Backend router — messages for no-op / unsupported backends
# ---------------------------------------------------------------------------

UNSUPPORTED_BUILDER_MESSAGES: dict[str, str] = {
    "visual": (
        "Backend 'visual' no tiene builder genérico en este router. "
        "Usá el builder visual específico de tu tarea "
        "(ej: tools/build_mapa_conceptual_investigacion.py) "
        "y luego ejecutá este router con --validate-only."
    ),
}

# Backends with a generic builder in this router, mapped to their script.
GENERIC_BUILDERS: dict[str, str] = {
    "latex": "build_latex_report.py",
    "docx": "build_docx_report.py",
}


def build_backend(
    config: "ReportConfig",
    args: argparse.Namespace,
) -> None:
    """Run the backend builder for a configured report.

    Args:
        config: ReportConfig with .backend and .folder.
        args: argparse.Namespace with .tex_only and .validate_only.

    Raises:
        SystemExit: on unsupported/no-op backend or subprocess failure.
    """
    if config.backend in GENERIC_BUILDERS:
        script = GENERIC_BUILDERS[config.backend]
        cmd = [sys.executable, str(Path(__file__).with_name(script)), str(config.folder)]
        # --tex-only is a LaTeX-only switch; the DOCX builder has no such stage.
        if args.tex_only and config.backend == "latex":
            cmd.append("--tex-only")
        try:
            proc = subprocess.run(cmd, text=True)
        except FileNotFoundError:
            raise SystemExit(
                "Error: no se encontró el ejecutable de Python o el script "
                f"{script} en la ruta esperada."
            )
        except OSError as exc:
            raise SystemExit(
                f"Error del sistema al ejecutar el builder {config.backend}: {exc}"
            )
        if proc.returncode != 0:
            raise SystemExit(proc.returncode)
    elif config.backend in UNSUPPORTED_BUILDER_MESSAGES:
        raise SystemExit(UNSUPPORTED_BUILDER_MESSAGES[config.backend])
    else:
        raise SystemExit(
            f"Backend no soportado: '{config.backend}'. "
            "Soportados: latex, docx (builders completos), "
            "visual (solo validación con --validate-only tras build manual)."
        )


def build_with_records(config: "ReportConfig", args: argparse.Namespace) -> None:
    """Run the build and the record lifecycle around it.

    Two records tell ``doc_status`` and the publisher what a build rendered:
    every PDF build (draft or final) records the ``body.md`` bytes, so a fresh
    PDF is told apart from one that predates the latest edit -- the publisher
    relies on it to refuse an unrebuilt PDF after a carried gate; every build with
    a ``report.yml`` records its render settings, so a delivery-only edit is
    told apart from one that needs a rebuild. Old records go first and new ones
    are written only after the build succeeded, so a failed build never looks
    fresh; ``--tex-only`` compiles no PDF and writes neither.
    """
    draft_body = config.folder / "body.md"
    record_draft = not args.tex_only and draft_body.is_file()
    # Through the module, so tests that fake the PDF hash leave this one real.
    rendered = approval_marker.sha256_file(draft_body) if record_draft else ""
    report_yml = config.folder / "report.yml"
    settings = render_digest(report_yml) if report_yml.is_file() else None
    if record_draft:
        draft_record_path(config.pdf_path).unlink(missing_ok=True)
    if settings:
        render_record_path(config.folder).unlink(missing_ok=True)
    build_backend(config, args)
    if record_draft:
        write_draft_record(config.pdf_path, draft_body, rendered)
    if settings and not args.tex_only:
        write_render_record(config.folder, settings)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path, help="Carpeta del reporte con report.yml")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--tex-only", action="store_true", help="Para backend LaTeX: genera .tex sin compilar PDF")
    parser.add_argument(
        "--no-approval-check",
        action="store_true",
        help="Construye sin approval.yml vigente (solo previews; nunca para entrega)",
    )
    args = parser.parse_args()

    if not (args.validate_only or args.no_approval_check):
        approval = approval_state(args.folder)
        if not approval.ok:
            raise SystemExit(
                f"APPROVAL REQUIRED: no se construye sin approval.yml vigente para body.md "
                f"({approval.detail}). Pedí la aprobación explícita del usuario; "
                "--no-approval-check es solo para previews."
            )

    config = load_report_config(args.folder)
    print(f"Tipo: {config.type} | backend: {config.backend} | output: {config.output_format}")

    # Build step — skipped when --validate-only
    if not args.validate_only:
        build_with_records(config, args)

    if args.tex_only:
        # --tex-only leaves no compiled PDF behind, so the post-build gates
        # that inspect the PDF must not run. ReportConfig.validators defaults
        # pdf_layout to ``output_format == "pdf" or pdf_path.exists()``
        # (report_config.py), so without this adjustment the layout audit
        # would either fail on a missing pdf_path or inspect a stale PDF from
        # a previous full build. validate(config) is a shared contract with
        # validate_report.py and takes no extra flag, so the only channel is
        # mutating config.raw before the call: output "tex" makes
        # output_format reflect the real artifact of this run, and
        # validators.pdf_layout=False overrides the default. The user must
        # see this adjustment, hence the explicit notice below.
        config.raw["output"] = "tex"
        config.raw.setdefault("validators", {})["pdf_layout"] = False
        print(
            "tex-only: output forzado a 'tex' y validador pdf_layout "
            "desactivado (no se compila PDF en esta corrida)."
        )
    validated_pdf_hash = sha256_file(config.pdf_path) if config.output_format == "pdf" else None
    result = validate(config)
    if result.errors:
        raise SystemExit("VALIDATION FAILED:\n- " + "\n- ".join(result.errors) + f"\n\nReporte: {config.quality_report_path}")
    if result.warnings:
        print("VALIDATION PASSED WITH WARNINGS:\n- " + "\n- ".join(result.warnings))
    else:
        print("VALIDATION PASSED")

    if config.output_format == "pdf":
        if sha256_file(config.pdf_path) != validated_pdf_hash:
            raise SystemExit(
                "PDF CHANGED DURING VALIDATION: el PDF cambió entre las dos "
                "lecturas de hash; la validación no cubre estos bytes. "
                "Volvé a generar y validar antes de entregar."
            )
        print(
            f"PDF GENERADO Y VALIDADO: {config.pdf_path} "
            f"(SHA-256: {validated_pdf_hash}). La entrega a ~/Documents es una "
            "fase separada: ejecutá tools/deliver_report.py."
        )
    print(f"Reporte: {config.quality_report_path}")


if __name__ == "__main__":
    main()
