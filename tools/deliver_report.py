#!/usr/bin/env python3
"""Deliver a validated report PDF into the user's versioned Documents library.

The deliver-phase entrypoint (#22): generation (``build_report_auto.py``) no
longer publishes, so delivery is explicit. This module is a thin gate-checker on
top of the existing guarded publisher (``publish_validated_pdf``), not a second
publication system. It adds exactly two checks the publisher does not own -- the
validation receipt ``validation.yml`` (schema ``academic.doc-validation/v1``)
must record ``result: pass`` for the exact bytes of the final PDF, and the final
human review marker ``final-review.yml`` (schema
``academic.doc-final-review/v1``) must be current for those same bytes -- and
then delegates to the publisher, which re-checks the human markers and performs
the atomic, versioned, hash-verified copy.

No new states, gates or approvals are introduced: a refusal is a non-zero exit
with the named missing evidence, and a rerun after fixing it is the only exit.
The destination is the report's shared delivery folder (``config.delivery_folder``):
the academic route is scoped by the confirmed subject's canonical slug
(``Academicos/<subject-slug>/<document-slug>/``); every other route keeps the flat
``<category>/<document-slug>/`` layout; ``delivery_dir:`` in report.yml replaces
either with an explicit folder. The publisher and ``doc_status`` both ask
``ReportConfig``, so they cannot disagree about the location.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from approval_marker import sha256_file
from final_review_marker import final_review_state
from publish_pdf import PublicationError, publish_validated_pdf
from report_config import load_report_config, read_yaml

VALIDATION_RECEIPT = "validation.yml"
FINAL_REVIEW_MARKER = "final-review.yml"

# The full gate vocabulary the validate phase can grant, in the order
# ``skills/academic-report-flow/references/production.md`` names them. The
# delivery message below reports exactly which of these the receipt
# actually names, never a fixed phrase.
KNOWN_GATES = ("BUILD_PASS", "VALIDATION_PASS", "VISUAL_PASS", "HUMAN_REVIEW", "READY_TO_SUBMIT")


def _granted_gates(receipt: dict) -> list[str]:
    """Return the ``KNOWN_GATES`` the receipt's ``gates:`` actually names.

    By the time this runs, delivery already happened: ``result: pass`` and the
    artifact hash were already checked, and the publisher already copied the
    PDF. ``gates:`` only feeds the informational message below, so a
    malformed value (a string, a mapping, ``None``, or a list with
    non-string entries) grants no gate instead of refusing an already
    completed delivery -- a naive ``gate in receipt.get("gates")`` would turn
    a string into a substring match and a mapping into a key lookup.
    """
    gates = receipt.get("gates")
    if not isinstance(gates, list) or not all(isinstance(gate, str) for gate in gates):
        return []
    return [gate for gate in KNOWN_GATES if gate in gates]


def _refuse(reason: str) -> int:
    """Print the refusal with its named missing evidence and fail the run."""
    print(f"DELIVERY REFUSED: {reason}", file=sys.stderr)
    print("No se publicó nada. Resolvé lo indicado y volvé a ejecutar deliver_report.py.", file=sys.stderr)
    return 1


def deliver(folder: Path, documents_root: Path | None = None) -> int:
    """Gate and publish the final PDF of ``folder``; return 0 or 1."""
    try:
        config = load_report_config(folder)
    except SystemExit as exc:
        return _refuse(f"report.yml inválido: {exc}")

    pdf = config.pdf_path
    if not pdf.is_file():
        return _refuse(f"falta el PDF final: {pdf}. Ejecutá primero la fase generate.")

    # The declared bibliography is resolved and refused before any gate that
    # must bind it, and long before a destination can exist.
    try:
        bibliography = config.delivery_bibliography()
    except ValueError as exc:
        return _refuse(str(exc))

    receipt_path = folder / VALIDATION_RECEIPT
    if not receipt_path.is_file():
        return _refuse(
            f"falta {VALIDATION_RECEIPT} en {folder}. Ejecutá primero la fase validate."
        )
    try:
        receipt = read_yaml(receipt_path)
    except Exception:
        return _refuse(f"{VALIDATION_RECEIPT} no es YAML válido en {folder}.")

    result = str(receipt.get("result") or "").strip().lower()
    if result != "pass":
        return _refuse(
            f"{VALIDATION_RECEIPT} no registra result: pass (registró: {result or 'nada'})."
        )

    pdf_hash = sha256_file(pdf)
    recorded = str(receipt.get("artifact_sha256") or "").strip().lower()
    if recorded != pdf_hash:
        return _refuse(
            f"{VALIDATION_RECEIPT} artifact_sha256 no coincide con los bytes actuales de "
            f"{pdf.name}; la evidencia está obsoleta. Volvé a validar."
        )

    if bibliography is not None:
        recorded_bib = str(receipt.get("bibliography_sha256") or "").strip().lower()
        if not recorded_bib:
            return _refuse(
                f"deliver_bibliography está activo pero {VALIDATION_RECEIPT} no registra "
                "bibliography_sha256; volvé a validar para vincular los bytes declarados."
            )
        if recorded_bib != sha256_file(bibliography):
            return _refuse(
                f"{VALIDATION_RECEIPT} bibliography_sha256 no coincide con los bytes actuales "
                f"de {bibliography.name}; la evidencia está obsoleta. Volvé a validar."
            )

    review = final_review_state(folder, pdf, bibliography=bibliography)
    if review.state == "absent":
        return _refuse(
            f"falta {FINAL_REVIEW_MARKER} en {folder}: falta la revisión humana final "
            f"de {pdf.name}. Ejecutá primero la fase review; no se publica nada."
        )
    if review.state == "stale":
        return _refuse(
            f"{FINAL_REVIEW_MARKER} no corresponde a los bytes actuales de {pdf.name} "
            f"({review.detail}); el PDF cambió después de la revisión final. "
            "Volvé a revisar."
        )
    if review.state == "malformed":
        return _refuse(
            f"{FINAL_REVIEW_MARKER} es inválido en {folder}: {review.detail}. "
            "No se publica nada y el marcador nunca se repara automáticamente."
        )

    try:
        category = config.publication_category
        slug = config.document_slug
        subject = config.delivery_subject_slug
        destination = config.delivery_dir
    except (KeyError, ValueError):
        return _refuse("identidad de publicación (categoría/slug) no disponible en report.yml.")

    try:
        publication = publish_validated_pdf(
            pdf,
            category,
            slug,
            documents_root=documents_root,
            work_folder=folder,
            expected_sha256=pdf_hash,
            subject=subject,
            bibliography=bibliography,
            destination=destination,
        )
    except PublicationError as exc:
        return _refuse(str(exc))

    action = "ENTREGADO" if publication.created else "REUTILIZADO"
    granted = _granted_gates(receipt)
    if final_review_state(folder, pdf).ok:
        granted = [gate for gate in KNOWN_GATES if gate == "HUMAN_REVIEW" or gate in granted]
    else:
        granted = [gate for gate in granted if gate != "HUMAN_REVIEW"]
    # READY_TO_SUBMIT follows once the receipt carries the inspected gates and
    # the human review of these exact bytes is current.
    if all(gate in granted for gate in ("BUILD_PASS", "VALIDATION_PASS", "VISUAL_PASS", "HUMAN_REVIEW")):
        granted = [gate for gate in KNOWN_GATES if gate == "READY_TO_SUBMIT" or gate in granted]
    missing = [gate for gate in KNOWN_GATES if gate not in granted]
    status_note = f"gates otorgados: {', '.join(granted) if granted else 'ninguno'}"
    if missing:
        status_note += f"; sin {', '.join(missing)}"
    print(
        f"PDF {action}: {publication.path} (SHA-256: {publication.sha256}); "
        f"copia técnicamente validada y aprobada; {status_note}."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publica el PDF validado y aprobado en ~/Documents (fase deliver)."
    )
    parser.add_argument("folder", type=Path, help="Carpeta del reporte con report.yml")
    parser.add_argument(
        "--documents-root",
        type=Path,
        default=None,
        help="Raíz alternativa de Documents (solo para pruebas; por defecto ~/Documents).",
    )
    args = parser.parse_args(argv)
    return deliver(args.folder, args.documents_root)


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
