#!/usr/bin/env python3
"""Publish validated PDFs into the user's versioned Documents library.

A delivery may be a PDF alone (the default) or, when the report explicitly
declares its bibliography a deliverable, the exact pair ``<slug>-vNNN.pdf``
plus ``<slug>-vNNN.bib``. Reuse, versioning and refusals always consider the
complete requested artifact set, never the PDF alone.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from approval_marker import ApprovalState, approval_state, draft_is_fresh, sha256_file
from final_review_marker import FinalReviewState, final_review_state
from report_config import resolve_documents_root, versioned_artifact_pattern

try:  # POSIX pair-claim serialization; a non-POSIX platform degrades to the
    # historical single-writer behavior instead of failing to import.
    import fcntl
except ImportError:  # pragma: no cover - platform-specific
    fcntl = None  # type: ignore[assignment]


class PublicationError(RuntimeError):
    """A validated PDF could not be safely published."""


@dataclass(frozen=True)
class Publication:
    path: Path
    sha256: str
    created: bool


def _require_pdf_file(path: Path) -> None:
    if path.suffix.lower() != ".pdf" or not path.is_file():
        raise PublicationError(f"El PDF validado no existe o no es un PDF: {path}")


def _approval_refusal(state: ApprovalState, work_folder: Path) -> str:
    """Map an approval state onto the user-facing refusal message."""
    if state.state == "stale":
        return (
            "La aprobación está obsoleta: body_sha256 de "
            f"approval.yml no coincide con body.md en {work_folder}. "
            "Volvé a aprobar el cuerpo actual; no se publica nada."
        )
    if state.state == "malformed":
        return (
            f"approval.yml es inválido en {work_folder}: {state.detail}. "
            "No se publica nada y el marcador nunca se repara automáticamente."
        )
    return (
        "Falta la aprobación humana: no existe approval.yml en "
        f"{work_folder}. Ejecutá la fase de aprobación después de revisar "
        "body.md; no se publica nada. La validación técnica pasó; falta "
        "únicamente la aprobación humana."
    )


def _final_review_refusal(state: FinalReviewState, work_folder: Path, source: Path) -> str:
    """Map a final review state onto the user-facing refusal message."""
    if state.state == "stale":
        return (
            "La revisión final está obsoleta: pdf_sha256 de final-review.yml no "
            f"coincide con los bytes actuales de {source.name} en {work_folder}. "
            "Volvé a revisar el PDF actual; no se publica nada."
        )
    if state.state == "malformed":
        return (
            f"final-review.yml es inválido en {work_folder}: {state.detail}. "
            "No se publica nada y el marcador nunca se repara automáticamente."
        )
    return (
        "Falta la revisión humana final: no existe final-review.yml en "
        f"{work_folder}. Ejecutá la fase de revisión final sobre {source.name}; "
        "no se publica nada."
    )


def scan_delivery_versions(folder: Path, slug: str) -> list[tuple[int, Path, Path | None]]:
    """Read-only scan of a delivery folder: ``(version, pdf, paired bib | None)``.

    A per-document folder may hold only properly named versioned final
    artifacts: ``<slug>-vNNN.pdf`` and — for a delivery that declared its
    bibliography — the same-version ``<slug>-vNNN.bib``. Anything else (work
    files, stray artifacts) or a ``.bib`` whose paired PDF is missing is a
    ``PublicationError``, never silently ignored. Sorted by version.
    """
    folder = Path(folder)
    if not folder.exists():
        return []
    pdf_pattern = versioned_artifact_pattern(slug, ".pdf")
    bib_pattern = versioned_artifact_pattern(slug, ".bib")
    pdfs: dict[int, Path] = {}
    bibs: dict[int, Path] = {}
    for path in folder.iterdir():
        pdf_match = pdf_pattern.match(path.name)
        bib_match = bib_pattern.match(path.name)
        if pdf_match:
            pdfs[int(pdf_match.group(1))] = path
        elif bib_match:
            bibs[int(bib_match.group(1))] = path
        else:
            raise PublicationError(
                f"La carpeta de entrega solo puede contener {slug}-vNNN.pdf "
                f"y sus .bib emparejados: {folder}"
            )
    orphans = sorted(set(bibs) - set(pdfs))
    if orphans:
        names = ", ".join(bibs[version].name for version in orphans)
        raise PublicationError(
            f"La carpeta de entrega contiene un .bib sin su PDF emparejado: {names}"
        )
    return [(version, pdfs[version], bibs.get(version)) for version in sorted(pdfs)]


def matching_delivered_version(
    folder: Path, slug: str, pdf_sha256: str, bibliography_sha256: str | None
) -> Path | None:
    """First version whose complete artifact set matches the request, or ``None``.

    The set is exact: the PDF bytes, the declared bibliography's bytes, and —
    for a pdf-only request — the absence of a sibling ``.bib``. A version that
    pairs the requested PDF with a changed bibliography is never a reuse, and
    switching between PDF-only and pair claims a new version instead of
    silently reusing the other shape.
    """
    for _version, pdf_path, bib_path in scan_delivery_versions(folder, slug):
        try:
            if sha256_file(pdf_path) != pdf_sha256:
                continue
            if bibliography_sha256 is None:
                if bib_path is None:
                    return pdf_path
                continue
            if bib_path is None or sha256_file(bib_path) != bibliography_sha256:
                continue
            return pdf_path
        except OSError:
            continue
    return None


def _copy_to_temp(source: Path, folder: Path, destination_name: str) -> Path:
    """Copy ``source`` into a fsynced temporary file beside ``destination_name``."""
    with tempfile.NamedTemporaryFile(
        mode="wb", prefix=f".{destination_name}.", suffix=".tmp", dir=folder, delete=False
    ) as temporary:
        with source.open("rb") as input_stream:
            shutil.copyfileobj(input_stream, temporary)
        temporary.flush()
        os.fsync(temporary.fileno())
    return Path(temporary.name)


def publish_validated_pdf(
    source: Path,
    category: str,
    slug: str,
    documents_root: Path | None = None,
    *,
    work_folder: Path,
    expected_sha256: str | None = None,
    subject: str | None = None,
    bibliography: Path | None = None,
    destination: Path | None = None,
) -> Publication:
    """Atomically publish a validated PDF, reusing identical hashes by version.

    Publication requires the configured technical validation AND two current
    human markers: ``work_folder/approval.yml`` must hash the exact bytes of
    ``work_folder/body.md``, and ``work_folder/final-review.yml`` must hash the
    exact bytes of the PDF being published — plus, when ``bibliography`` is
    given, a ``bibliography_sha256`` binding those exact bytes. ``work_folder``
    is required keyword-only, so a caller cannot skip the guards by omission.
    All checks run before any hash, directory or temporary file, so a refused
    publication creates nothing.

    The destination is ``<root>/<category>/<slug>/``; passing the optional
    canonical ``subject`` slug (academic route) inserts the course level:
    ``<root>/<category>/<subject>/<slug>/``. Omitting it keeps the flat
    category layout, so direct publisher callers keep working unchanged. An
    explicit ``destination`` (report.yml ``delivery_dir``) replaces that whole
    layout; the version register, hashing and locking are unchanged.

    A declared ``bibliography`` (a regular ``.bib`` file) publishes as the
    same-version pair ``<slug>-vNNN.pdf`` + ``<slug>-vNNN.bib``. Reuse compares
    the complete requested set: the same PDF with a changed bibliography
    claims a new version, and switching between pair and PDF-only never reuses
    the other shape. The pair claim is serialized with ``flock`` on the
    destination directory (POSIX); a failure between the two claims removes
    only this call's own files and leaves every earlier delivery untouched.

    It remains a technical-copy operation: it never grants ``VISUAL_PASS``,
    ``HUMAN_REVIEW``, or ``READY_TO_SUBMIT``.
    """
    source = Path(source)
    work_folder = Path(work_folder)
    bibliography = Path(bibliography) if bibliography is not None else None
    _require_pdf_file(source)
    if not category or not slug:
        raise PublicationError("La categoría y el slug del documento son obligatorios")
    if bibliography is not None and (bibliography.suffix.lower() != ".bib" or not bibliography.is_file()):
        raise PublicationError(
            f"La bibliografía declarada no existe o no es un archivo .bib: {bibliography}"
        )

    state = approval_state(work_folder)
    if not state.ok:
        raise PublicationError(_approval_refusal(state, work_folder))

    review = final_review_state(work_folder, source, bibliography=bibliography)
    if not review.ok:
        message = _final_review_refusal(review, work_folder, source)
        if bibliography is not None and review.detail:
            message = f"{message} Detalle: {review.detail}."
        raise PublicationError(message)

    # A carried gate skips the human question, never the rebuild: the build
    # record next to the PDF must hold the sha256 of the body.md as it is now.
    if (state.state == "carried" or review.state == "carried") and not draft_is_fresh(
        source, work_folder / "body.md"
    ):
        raise PublicationError(
            "Hubo una edición acotada de body.md y el PDF no se generó desde el body.md actual. "
            "Volvé a generar y validar el PDF antes de publicar; no se publica nada."
        )

    if destination is not None:
        folder = Path(destination)
    else:
        root = resolve_documents_root(documents_root)
        folder = root / category / slug
        if subject:
            folder = root / category / subject / slug
    source_hash = sha256_file(source)
    if expected_sha256 is not None and source_hash != expected_sha256:
        raise PublicationError("El PDF cambió desde la validación técnica")
    bib_hash = sha256_file(bibliography) if bibliography is not None else None
    folder.mkdir(parents=True, exist_ok=True)

    return _claim_versions(folder, slug, source, source_hash, bibliography, bib_hash)


def _claim_versions(
    folder: Path,
    slug: str,
    source: Path,
    source_hash: str,
    bibliography: Path | None,
    bib_hash: str | None,
) -> Publication:
    """Claim the next version for the requested set under a directory lock.

    The lock serializes pair claims so two concurrent publishers can never
    interleave a mixed ``vNNN.pdf``/``vNNN.bib`` pair. A lost version race
    retries with a fresh scan instead of overwriting; a copy/link/verify
    failure cleans only this call's claimed paths.
    """
    lock_fd: int | None = None
    try:
        if fcntl is not None:
            lock_fd = os.open(folder, os.O_RDONLY)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
        while True:
            versions = scan_delivery_versions(folder, slug)
            reused = matching_delivered_version(folder, slug, source_hash, bib_hash)
            if reused is not None:
                return Publication(path=reused, sha256=source_hash, created=False)

            next_version = versions[-1][0] + 1 if versions else 1
            pdf_destination = folder / f"{slug}-v{next_version:03d}.pdf"
            bib_destination = (
                folder / f"{slug}-v{next_version:03d}.bib" if bibliography is not None else None
            )
            claimed: list[Path] = []
            temporary_paths: list[Path] = []
            try:
                pdf_temporary = _copy_to_temp(source, folder, pdf_destination.name)
                temporary_paths.append(pdf_temporary)
                bib_temporary: Path | None = None
                if bibliography is not None:
                    bib_temporary = _copy_to_temp(bibliography, folder, bib_destination.name)
                    temporary_paths.append(bib_temporary)
                # link(2) atomically claims each name and refuses to overwrite
                # an already claimed one; a lost race retries with a fresh scan.
                os.link(pdf_temporary, pdf_destination)
                claimed.append(pdf_destination)
                if bib_temporary is not None:
                    os.link(bib_temporary, bib_destination)
                    claimed.append(bib_destination)
            except FileExistsError:
                for path in claimed:
                    path.unlink(missing_ok=True)
                continue
            except OSError as exc:
                for path in claimed:
                    path.unlink(missing_ok=True)
                raise PublicationError(
                    f"No se pudo publicar el PDF en {bib_destination or pdf_destination}: {exc}"
                ) from exc
            finally:
                for path in temporary_paths:
                    path.unlink(missing_ok=True)

            # Post-copy verification covers BOTH files of the set: a mismatch
            # removes this call's claimed files; no success on a partial set.
            if sha256_file(pdf_destination) != source_hash:
                for path in claimed:
                    path.unlink(missing_ok=True)
                raise PublicationError(
                    f"SHA-256 no coincide después de publicar {pdf_destination}"
                )
            if bib_destination is not None and sha256_file(bib_destination) != bib_hash:
                for path in claimed:
                    path.unlink(missing_ok=True)
                raise PublicationError(
                    f"SHA-256 no coincide después de publicar {bib_destination}"
                )
            return Publication(path=pdf_destination, sha256=source_hash, created=True)
    finally:
        if lock_fd is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
