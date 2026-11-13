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
from typing import Callable

from approval_marker import ApprovalState, approval_state, draft_is_fresh, generation_record_current, sha256_file
from final_review_marker import FinalReviewState, final_review_state
from report_config import read_yaml, resolve_documents_root, versioned_artifact_pattern

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


GENERATION_REFUSAL = (
    "Falta o está obsoleta la identidad del PDF generado y sus entradas; "
    "volvé a generar y validar antes de publicar. No se publica nada."
)


def _content_refusal(work_folder: Path) -> str | None:
    """Why a report without a current draft approval may not publish, or ``None``.

    A v1 report reaches publication without the draft approval that used to
    vouch for the verify gate, so the publisher re-derives that gate here: the
    guide inventory is mapped and ``content-check.yml`` passes for the current
    inputs -- every rubric requirement found or a partial a human accepted,
    every citation resolved. Read-only; never writes.
    """
    import accepted_gaps
    import content_check
    import rubric_plan

    unmapped = rubric_plan.inventory_problems(work_folder)
    if unmapped:
        ids = ", ".join(problem.split(":", 1)[0] for problem in unmapped)
        return (
            f"La guía tiene ítems sin criterio ni entrada not_applicable en rubric.yml: {ids}. "
            "No se publica nada."
        )
    state = content_check.content_check_state(work_folder)
    if state == "pass":
        return None
    if state != "fail":
        return (
            f"content-check.yml está {state} en {work_folder}: falta la verificación vigente "
            "del contenido. Volvé a verificar antes de publicar; no se publica nada."
        )
    try:
        marker = read_yaml(work_folder / content_check.CONTENT_CHECK_NAME)
    except Exception:
        marker = {}
    mechanical = [item for item in marker.get("mechanical") or [] if isinstance(item, dict)]
    citations = [item for item in mechanical if item.get("check") == "citations_resolve" and item.get("ok") is not True]
    if citations:
        return (
            f"Hay citas sin resolver en body.md ({citations[0].get('detail', '')}). "
            "Corregí las citas y volvé a verificar y generar antes de publicar; no se publica nada."
        )
    requirements = [item for item in marker.get("requirements") or [] if isinstance(item, dict)]
    waived = accepted_gaps.waived_requirements(work_folder, requirements)
    open_items = [
        f"{item.get('status')}: {item.get('requirement')}"
        for item in requirements
        if item.get("status") in ("missing", "partial")
        and (str(item.get("criterion")), str(item.get("requirement"))) not in waived
    ]
    open_items += [f"{item.get('check')}: {item.get('detail', '')}" for item in mechanical if item.get("ok") is not True]
    detail = "; ".join(open_items) or "content-check.yml: fail"
    return (
        f"Hay fallas de rúbrica sin resolver y sin brecha aceptada ({detail}). "
        "Corregí el informe o, solo si el usuario lo decide, registrá la brecha parcial con "
        "accepted_gaps.py; no se publica nada."
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


# The course-repo template ships documento/README.md; delivery allows and ignores it.
DELIVERY_README = "README.md"


def scan_delivery_versions(folder: Path, slug: str) -> list[tuple[int, Path, Path | None]]:
    """Read-only scan of a delivery folder: ``(version, pdf, paired bib | None)``.

    A per-document folder may hold only properly named versioned final
    artifacts: ``<slug>-vNNN.pdf`` and — for a delivery that declared its
    bibliography — the same-version ``<slug>-vNNN.bib``. Anything else (work
    files, stray artifacts) or a ``.bib`` whose paired PDF is missing is a
    ``PublicationError``, never silently ignored. The one exception is a
    regular file named exactly ``README.md`` (the course-repo template ships
    one): it is allowed, never listed and never touched. Sorted by version.
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
        elif path.name == DELIVERY_README and path.is_file() and not path.is_symlink():
            continue
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
    warn: Callable[[str, str], None] | None = None,
) -> Publication:
    """Atomically publish a validated PDF, reusing identical hashes by version.

    Publication requires the configured technical validation AND two current
    human markers: ``work_folder/approval.yml`` must hash the exact bytes of
    ``work_folder/body.md``, and ``work_folder/final-review.yml`` must hash the
    exact bytes of the PDF being published — plus, when ``bibliography`` is
    given, a ``bibliography_sha256`` binding those exact bytes. A v1 report
    (no ``approval.yml``, or a ``build/generation.yml`` record) replaces the
    draft approval with the generated artifact identity and, without a current
    approval, the verify gate it vouched for (``_content_refusal``). ``work_folder``
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

    warn-only-gates S2: with ``warn``, each quality refusal is handed to
    ``warn(code, message)`` and publication proceeds instead of raising. The
    codes are ``generation_identity`` (a stale generated identity next to a
    valid approval),
    ``content_check`` (unmapped inventory or unresolved content check),
    ``final_review`` (missing or stale final review) and ``stale_draft`` (a
    carried gate over a PDF not rebuilt from the current body.md). A missing PDF
    or bibliography, a missing category/slug, a stale or malformed approval.yml
    (the user's explicit approve, not a quality check) whatever
    build/generation.yml holds, a missing approval.yml without a current
    generated identity (the only integrity anchor then), a malformed
    final-review.yml and version-claim errors always raise. ``warn=None`` keeps
    every refusal raising. The message handed to ``warn`` is the raw refusal
    text; a caller that delivers anyway rewords its "no se publica nada" clause
    (``deliver_report.delivered_anyway``) before printing it.
    """

    def refuse_or_warn(code: str, message: str) -> None:
        if warn is None:
            raise PublicationError(message)
        warn(code, message)

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
    # A report built as v1 (no draft approval, or a generation record) is
    # bound to its generated artifact identity and re-checks the verify gate
    # the approval used to vouch for; a legacy approval keeps its own path.
    #
    # Integrity, not quality (L3): a present but stale or malformed approval.yml
    # always refuses, whatever build/generation.yml holds. Without approval.yml
    # the generated identity is the only anchor, so a missing or stale record
    # refuses too. Only a stale identity next to a valid approval is a warning.
    generation_record = work_folder / "build" / "generation.yml"
    if state.state in ("stale", "malformed"):
        raise PublicationError(_approval_refusal(state, work_folder))
    if state.state == "absent":
        if not generation_record_current(work_folder, source):
            raise PublicationError(GENERATION_REFUSAL)
        refusal = _content_refusal(work_folder)
        if refusal:
            refuse_or_warn("content_check", refusal)
    elif generation_record.is_file() and not generation_record_current(work_folder, source):
        refuse_or_warn("generation_identity", GENERATION_REFUSAL)

    review = final_review_state(work_folder, source, bibliography=bibliography)
    if not review.ok:
        message = _final_review_refusal(review, work_folder, source)
        if bibliography is not None and review.detail:
            message = f"{message} Detalle: {review.detail}."
        if review.state == "malformed":
            raise PublicationError(message)
        refuse_or_warn("final_review", message)

    # A carried gate skips the human question, never the rebuild: the build
    # record next to the PDF must hold the sha256 of the body.md as it is now.
    if (state.state == "carried" or review.state == "carried") and not draft_is_fresh(
        source, work_folder / "body.md"
    ):
        refuse_or_warn(
            "stale_draft",
            "Hubo una edición acotada de body.md y el PDF no se generó desde el body.md actual. "
            "Volvé a generar y validar el PDF antes de publicar; no se publica nada.",
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
