"""warn-only-gates S2: the publisher's quality refusals become warnings when the caller asks.

``publish_validated_pdf(..., warn=callback)`` hands each quality refusal (a stale
generated identity next to a valid approval, unresolved rubric or unmapped inventory, missing
or stale final review, a carried gate over an unrebuilt PDF) to ``callback`` as
``(code, message)`` and publishes. ``warn=None`` keeps the old raising
behaviour. A missing PDF or bibliography, a missing category/slug, a stale or malformed
approval (the user's explicit approve), a missing approval without a current
generated identity, and a malformed final review always raise, with or without
``warn``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import approval_marker
import publish_pdf
from conftest import _approval, _final_review, _pdf, _report

CONTENT = b"%PDF-1.7\nvalidated\n"


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "work" / "validated.pdf"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(CONTENT)
    return source


def _publish(source: Path, folder: Path, documents: Path, warnings: list | None, **extra: object):
    warn = None if warnings is None else (lambda code, message: warnings.append((code, message)))
    return publish_pdf.publish_validated_pdf(
        source, "Tecnicos", "informe", documents, work_folder=folder, warn=warn, **extra
    )


def _published(documents: Path) -> list[Path]:
    return sorted(documents.rglob("*.pdf"))


# -- downgraded refusals ---------------------------------------------------------


def _v1(folder: Path, source: Path) -> None:
    """A v1 report (no approval.yml) with a current generated identity for ``source``."""
    _report(folder)
    (folder / "body.md").write_text("# Informe\n\nCuerpo generado.\n", encoding="utf-8")
    approval_marker.write_generation_record(
        folder, source, approval_marker.generation_inputs(folder), approval_marker.sha256_file(source)
    )


def test_stale_generated_identity_next_to_approval_warns_and_publishes(tmp_path: Path) -> None:
    folder = tmp_path / "approved"
    _approval(folder)
    (folder / "build").mkdir()
    (folder / "build" / "generation.yml").write_text("pdf_sha256: stale\n", encoding="utf-8")
    source = _source(tmp_path)
    _final_review(folder, pdf=source)
    documents = tmp_path / "Documents"
    warnings: list = []

    published = _publish(source, folder, documents, warnings)

    assert warnings == [("generation_identity", publish_pdf.GENERATION_REFUSAL)]
    assert published.path.read_bytes() == CONTENT
    with pytest.raises(publish_pdf.PublicationError, match="identidad del PDF generado"):
        _publish(source, folder, tmp_path / "Other", None)


def test_missing_generated_identity_without_approval_raises_even_with_warn(tmp_path: Path) -> None:
    """Without approval.yml the generated identity is the integrity anchor (L3), never a warning."""
    folder = tmp_path / "v1"
    folder.mkdir()
    source = _source(tmp_path)
    _final_review(folder, pdf=source)
    documents = tmp_path / "Documents"

    with pytest.raises(publish_pdf.PublicationError) as raised:
        _publish(source, folder, documents, [])
    assert str(raised.value) == publish_pdf.GENERATION_REFUSAL
    assert not documents.exists()


def test_unresolved_content_check_warns_and_publishes(tmp_path: Path) -> None:
    folder = tmp_path / "v1"
    source = _source(tmp_path)
    _v1(folder, source)
    _final_review(folder, pdf=source)
    documents = tmp_path / "Documents"
    warnings: list = []

    _publish(source, folder, documents, warnings)

    content = [message for code, message in warnings if code == "content_check"]
    assert content == [publish_pdf._content_refusal(folder)]
    assert content[0].startswith("content-check.yml está absent")
    assert len(_published(documents)) == 1


def test_unmapped_inventory_warns_and_publishes(tmp_path: Path) -> None:
    from test_doc_status_inventory import CRITERIA, verified_with_guide

    folder = verified_with_guide(tmp_path / "unmapped", CRITERIA)
    source = _source(tmp_path)
    approval_marker.write_generation_record(
        folder, source, approval_marker.generation_inputs(folder), approval_marker.sha256_file(source)
    )
    _final_review(folder, pdf=source)
    documents = tmp_path / "Documents"
    warnings: list = []

    _publish(source, folder, documents, warnings)

    content = [message for code, message in warnings if code == "content_check"]
    assert len(content) == 1
    assert content[0].startswith("La guía tiene ítems sin criterio ni entrada not_applicable en rubric.yml: G5")
    assert len(_published(documents)) == 1


def test_missing_and_stale_final_review_warn_and_publish(tmp_path: Path) -> None:
    folder = tmp_path / "approved"
    _approval(folder)
    source = _source(tmp_path)
    documents = tmp_path / "Documents"
    warnings: list = []

    _publish(source, folder, documents, warnings)
    assert warnings == [("final_review", publish_pdf._final_review_refusal(
        publish_pdf.final_review_state(folder, source), folder, source))]
    assert warnings[0][1].startswith("Falta la revisión humana final")

    _final_review(folder, pdf=source, pdf_sha256="0" * 64)
    warnings.clear()
    _publish(source, folder, documents, warnings)
    assert [code for code, _ in warnings] == ["final_review"]
    assert warnings[0][1].startswith("La revisión final está obsoleta")
    assert len(_published(documents)) == 1  # identical bytes reuse v001


def test_carried_gate_over_an_unrebuilt_pdf_warns_and_publishes(tmp_path: Path) -> None:
    import final_review_marker

    folder = tmp_path / "wf"
    _report(folder)
    (folder / "body.md").write_text("# Informe\n\nPreparado por Juan Perez.\n", encoding="utf-8")
    approval_marker.record_approval(folder, "Alejandro")
    pdf = _pdf(folder)
    approval_marker.write_draft_record(pdf, folder / "body.md")
    final_review_marker.record_final_review(folder, "Alejandro", pdf)
    (folder / "body.md").write_text("# Informe\n\nPreparado por Ana Perez.\n", encoding="utf-8")
    documents = tmp_path / "Documents"
    warnings: list = []

    _publish(pdf, folder, documents, warnings)

    assert [code for code, _ in warnings] == ["stale_draft"]
    assert warnings[0][1].startswith("Hubo una edición acotada de body.md")
    assert len(_published(documents)) == 1


# -- kept hard refusals ------------------------------------------------------------


def test_missing_pdf_still_raises_with_warn(tmp_path: Path) -> None:
    folder = tmp_path / "approved"
    _approval(folder)
    documents = tmp_path / "Documents"
    with pytest.raises(publish_pdf.PublicationError, match="no existe o no es un PDF"):
        _publish(tmp_path / "missing.pdf", folder, documents, [])
    assert not documents.exists()


def test_missing_category_still_raises_with_warn(tmp_path: Path) -> None:
    folder = tmp_path / "approved"
    _approval(folder)
    source = _source(tmp_path)
    with pytest.raises(publish_pdf.PublicationError, match="obligatorios"):
        publish_pdf.publish_validated_pdf(source, "", "informe", tmp_path / "D", work_folder=folder,
                                          warn=lambda code, message: None)


def test_missing_declared_bibliography_still_raises_with_warn(tmp_path: Path) -> None:
    folder = tmp_path / "approved"
    _approval(folder)
    source = _source(tmp_path)
    with pytest.raises(publish_pdf.PublicationError, match="bibliografía declarada no existe"):
        _publish(source, folder, tmp_path / "D", [], bibliography=tmp_path / "missing.bib")


def test_stale_and_malformed_approval_still_raise_with_warn(tmp_path: Path) -> None:
    """approval.yml is the user's explicit approve, a human decision, not a quality check."""
    folder = tmp_path / "approved"
    _approval(folder)
    source = _source(tmp_path)
    _final_review(folder, pdf=source)
    (folder / "body.md").write_text("edited after approval\n", encoding="utf-8")
    documents = tmp_path / "Documents"
    with pytest.raises(publish_pdf.PublicationError, match="aprobación está obsoleta"):
        _publish(source, folder, documents, [])

    malformed = tmp_path / "malformed"
    malformed.mkdir()
    (malformed / "approval.yml").write_text("preview_sha256: [unclosed\n", encoding="utf-8")
    with pytest.raises(publish_pdf.PublicationError, match="approval.yml es inválido"):
        _publish(source, malformed, documents, [])
    assert not documents.exists()


def test_malformed_final_review_still_raises_with_warn(tmp_path: Path) -> None:
    folder = tmp_path / "approved"
    _approval(folder)
    source = _source(tmp_path)
    (folder / "final-review.yml").write_text("pdf_sha256: [unclosed\n", encoding="utf-8")
    documents = tmp_path / "Documents"
    with pytest.raises(publish_pdf.PublicationError, match="final-review.yml es inválido"):
        _publish(source, folder, documents, [])
    assert not documents.exists()
