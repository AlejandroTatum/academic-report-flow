"""Validate/deliver-phase tests for ``tools/doc_status.py`` (slice 2b-iii).

Slice 2b-iii ships the last two derivations. Validate is ``done`` when
``validation.yml`` records ``result: pass`` for the exact bytes of the final PDF,
``done`` with a ``warning: validation_failed`` detail when it records a fail
(warn-only-gates S2), and ``pending`` when
the receipt is missing or its hash no longer matches. Deliver is ``done`` when a
``<slug>-vNNN.pdf`` under the Documents root hash-matches the final PDF and
``pending`` otherwise. Like the 2a/2b-i/2b-ii suites these tests call the handlers
directly and assert the raw token, detail and blocked reason -- ``derive``, the
renderers and the CLI are slice 2c. Artifact shapes come from ``tools/conftest.py``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import doc_status
import publish_pdf
from conftest import (
    _approval,
    _bibliography,
    _body,
    _config,
    _declare_bibliography_delivery,
    _final_review,
    _pdf,
    _published,
    _report,
    _sha256,
    _validation,
)

CATEGORY = "Academicos"
SLUG = "informe-de-laboratorio"


def _final_pdf(folder: Path) -> Path:
    """Build the default report and its configured final PDF; return the PDF path."""
    _report(folder)
    return _pdf(folder)


# ---------------------------------------------------------------------------
# 2.12 validate
# ---------------------------------------------------------------------------


def test_validate_pass_with_matching_hash_is_done(tmp_path: Path) -> None:
    """A pass receipt bound to the current PDF bytes is the validate artifact."""
    folder = tmp_path / "wf"
    pdf = _final_pdf(folder)
    _validation(folder, pdf=pdf)

    phase = doc_status._phase_validate(folder, _config(folder), None)

    assert phase.name == "validate"
    assert phase.state == doc_status.DONE
    assert phase.blocked_reason == ""
    assert pdf.name in phase.detail


def test_validate_pass_with_mismatched_hash_is_pending(tmp_path: Path) -> None:
    """A receipt for other bytes does not validate this PDF; rerun validation."""
    folder = tmp_path / "wf"
    pdf = _final_pdf(folder)
    _validation(folder, pdf=pdf, artifact_sha256="0" * 64)

    phase = doc_status._phase_validate(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert phase.blocked_reason == ""
    assert phase.state != doc_status.DONE


def test_validate_result_fail_is_a_validation_failed_warning(tmp_path: Path) -> None:
    """A recorded failure is a warning: the route continues to review (warn-only-gates S2)."""
    folder = tmp_path / "wf"
    pdf = _final_pdf(folder)
    _validation(folder, pdf=pdf, result="fail")

    phase = doc_status._phase_validate(folder, _config(folder), None)

    assert phase.state == doc_status.DONE
    assert phase.blocked_reason == ""
    assert phase.detail == "warning: validation_failed: validation.yml recorded result: fail"


def test_validate_stale_fail_receipt_does_not_block_a_new_pdf(tmp_path: Path) -> None:
    """A fail receipt bound to older bytes is stale: the new PDF simply revalidates.

    Receipt identity is checked before the recorded outcome is interpreted, so a
    ``result: fail`` that describes a superseded build returns to ``pending``
    instead of blocking the route forever.
    """
    folder = tmp_path / "wf"
    pdf = _final_pdf(folder)
    _validation(folder, pdf=pdf, result="fail")
    pdf.write_bytes(b"%PDF-1.4\nREBUILT\n%%EOF\n")  # a new build after the failed run

    phase = doc_status._phase_validate(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert phase.blocked_reason == ""


def test_validate_fail_receipt_without_bound_identity_is_pending(tmp_path: Path) -> None:
    """TRIANGULATE: a fail receipt that proves no identity cannot block either."""
    folder = tmp_path / "wf"
    pdf = _final_pdf(folder)
    _validation(folder, pdf=pdf, result="fail", drop=("artifact_sha256",))

    phase = doc_status._phase_validate(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert phase.blocked_reason == ""


def test_validate_missing_receipt_is_pending(tmp_path: Path) -> None:
    """TRIANGULATE: a folder that was never validated waits at validate."""
    folder = tmp_path / "wf"
    _final_pdf(folder)

    phase = doc_status._phase_validate(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert phase.blocked_reason == ""
    assert "validation.yml" in phase.detail


def test_validate_missing_final_pdf_is_pending(tmp_path: Path) -> None:
    """TRIANGULATE: a receipt cannot bind to a PDF that no longer exists."""
    folder = tmp_path / "wf"
    pdf = _final_pdf(folder)
    _validation(folder, pdf=pdf)
    pdf.unlink()

    phase = doc_status._phase_validate(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert phase.blocked_reason == ""
    assert phase.state != doc_status.DONE


def test_validate_unparsable_receipt_is_pending_not_done(tmp_path: Path) -> None:
    """TRIANGULATE: a corrupt receipt is never read as a pass."""
    folder = tmp_path / "wf"
    _final_pdf(folder)
    (folder / "validation.yml").write_text("artifact_sha256: [unclosed\n", encoding="utf-8")

    phase = doc_status._phase_validate(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert phase.blocked_reason == ""
    assert phase.state != doc_status.DONE


# ---------------------------------------------------------------------------
# 2.14 deliver
# ---------------------------------------------------------------------------


def test_deliver_hash_matched_published_pdf_is_done(tmp_path: Path) -> None:
    """A published version whose bytes match the final PDF is the delivery."""
    folder = tmp_path / "wf"
    pdf = _final_pdf(folder)
    root = tmp_path / "Documents"
    published = _published(root, category=f"{CATEGORY}/fisica", slug=SLUG, source=pdf)

    phase = doc_status._phase_deliver(folder, _config(folder), root)

    assert phase.name == "deliver"
    assert phase.state == doc_status.DONE
    assert phase.blocked_reason == ""
    assert published.name in phase.detail


def test_deliver_absent_published_pdf_is_pending(tmp_path: Path) -> None:
    """Nothing published for this report keeps delivery pending."""
    folder = tmp_path / "wf"
    _final_pdf(folder)
    root = tmp_path / "Documents"

    phase = doc_status._phase_deliver(folder, _config(folder), root)

    assert phase.state == doc_status.PENDING
    assert phase.blocked_reason == ""
    assert phase.state != doc_status.DONE


def test_deliver_published_copy_with_other_bytes_is_pending(tmp_path: Path) -> None:
    """TRIANGULATE: a same-named version with different bytes is not a delivery."""
    folder = tmp_path / "wf"
    _final_pdf(folder)
    root = tmp_path / "Documents"
    _published(root, category=f"{CATEGORY}/fisica", slug=SLUG, content=b"%PDF-1.4\nOTHER\n%%EOF\n")

    phase = doc_status._phase_deliver(folder, _config(folder), root)

    assert phase.state == doc_status.PENDING


def test_deliver_scans_every_version_for_a_hash_match(tmp_path: Path) -> None:
    """TRIANGULATE: an older mismatched version does not hide the matching v002."""
    folder = tmp_path / "wf"
    pdf = _final_pdf(folder)
    root = tmp_path / "Documents"
    _published(root, category=f"{CATEGORY}/fisica", slug=SLUG, content=b"%PDF-1.4\nSTALE\n%%EOF\n", version=1)
    matched = _published(root, category=f"{CATEGORY}/fisica", slug=SLUG, source=pdf, version=2)

    phase = doc_status._phase_deliver(folder, _config(folder), root)

    assert phase.state == doc_status.DONE
    assert matched.name in phase.detail


def test_deliver_defaults_to_home_documents(tmp_path: Path, monkeypatch) -> None:
    """TRIANGULATE: without an explicit root the phase reads ``~/Documents``."""
    folder = tmp_path / "wf"
    pdf = _final_pdf(folder)
    root = tmp_path / "home" / "Documents"
    published = _published(root, category=f"{CATEGORY}/fisica", slug=SLUG, source=pdf)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))

    phase = doc_status._phase_deliver(folder, _config(folder), None)

    assert phase.state == doc_status.DONE
    assert published.name in phase.detail


# ---------------------------------------------------------------------------
# 2.14 deliver — subject-scoped academic layout (course-deliverables-hierarchy T1)
# ---------------------------------------------------------------------------


def test_deliver_done_for_the_canonical_subject_folder(tmp_path: Path) -> None:
    """A canonical academic subject scopes the folder the phase scans."""
    folder = tmp_path / "wf"
    _report(folder, subject="Sistemas Operativos")
    pdf = _pdf(folder)
    root = tmp_path / "Documents"
    published = _published(
        root, category=f"{CATEGORY}/sistemas-operativos", slug=SLUG, source=pdf
    )

    phase = doc_status._phase_deliver(folder, _config(folder), root)

    assert phase.state == doc_status.DONE
    assert published.name in phase.detail


def test_deliver_pending_when_only_the_legacy_flat_folder_has_the_copy(tmp_path: Path) -> None:
    """TRIANGULATE: a subject-scoped report ignores the pre-hierarchy location.

    Publisher and status derivation share one folder answer, so a copy left at
    the flat legacy path by an older delivery never counts as delivered.
    """
    folder = tmp_path / "wf"
    _report(folder, subject="Sistemas Operativos")
    _pdf(folder)
    root = tmp_path / "Documents"
    _published(root, category=CATEGORY, slug=SLUG)

    phase = doc_status._phase_deliver(folder, _config(folder), root)

    assert phase.state == doc_status.PENDING
    assert phase.blocked_reason == ""


def test_deliver_done_for_a_newly_named_course_folder(tmp_path: Path) -> None:
    """A confirmed subject absent from the alias vocabulary still scopes the scan.

    Publisher and doc_status derive the same ASCII level from the confirmed
    subject itself, so a newly named course agrees without registration.
    """
    folder = tmp_path / "wf"
    _report(folder, subject="Fisica")
    pdf = _pdf(folder)
    root = tmp_path / "Documents"
    published = _published(root, category=f"{CATEGORY}/fisica", slug=SLUG, source=pdf)

    phase = doc_status._phase_deliver(folder, _config(folder), root)

    assert phase.state == doc_status.DONE
    assert published.name in phase.detail


def test_deliver_flat_folder_for_nonacademic_category(tmp_path: Path) -> None:
    """Non-academic routes keep scanning Proyectos/<slug>/ with no subject level."""
    folder = tmp_path / "wf"
    _report(folder, route="project")
    pdf = _pdf(folder)
    root = tmp_path / "Documents"
    published = _published(root, category="Proyectos", slug=SLUG, source=pdf)

    phase = doc_status._phase_deliver(folder, _config(folder), root)

    assert phase.state == doc_status.DONE
    assert published.name in phase.detail


def test_deliver_ignores_git_metadata_at_the_course_root(tmp_path: Path) -> None:
    """A course root that is the user's Git repo does not disturb the scan."""
    folder = tmp_path / "wf"
    _report(folder, subject="Sistemas Operativos")
    pdf = _pdf(folder)
    root = tmp_path / "Documents"
    course_root = root / CATEGORY / "sistemas-operativos"
    (course_root / ".git").mkdir(parents=True)
    (course_root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    published = _published(
        root, category=f"{CATEGORY}/sistemas-operativos", slug=SLUG, source=pdf
    )

    phase = doc_status._phase_deliver(folder, _config(folder), root)

    assert phase.state == doc_status.DONE
    assert published.name in phase.detail


# ---------------------------------------------------------------------------
# Declared bibliography binding (course-deliverables-hierarchy T2)
# ---------------------------------------------------------------------------


def _opted_in_folder(tmp_path: Path, name: str = "wf") -> tuple[Path, Path, Path]:
    """A report opted into bibliography delivery with its final PDF and .bib."""
    folder = tmp_path / name
    _report(folder)
    _approval(folder)
    pdf = _pdf(folder)
    bib = _bibliography(folder)
    _declare_bibliography_delivery(folder)
    return folder, pdf, bib


def test_validate_binds_bibliography_hash_when_opted_in(tmp_path: Path) -> None:
    """A pass receipt must also bind the declared bibliography bytes."""
    folder, pdf, bib = _opted_in_folder(tmp_path)
    _validation(folder, pdf=pdf, bibliography_sha256=_sha256(bib))

    phase = doc_status._phase_validate(folder, _config(folder), None)

    assert phase.state == doc_status.DONE


def test_validate_missing_bibliography_hash_is_pending(tmp_path: Path) -> None:
    """TRIANGULATE: a pdf-only receipt never validates an opted-in report."""
    folder, pdf, _ = _opted_in_folder(tmp_path)
    _validation(folder, pdf=pdf, drop=("bibliography_sha256",))

    phase = doc_status._phase_validate(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert "bibliography_sha256" in phase.detail


def test_validate_stale_bibliography_hash_is_pending(tmp_path: Path) -> None:
    """A receipt bound to older bibliography bytes is stale evidence."""
    folder, pdf, bib = _opted_in_folder(tmp_path)
    _validation(folder, pdf=pdf, bibliography_sha256=_sha256(bib))
    bib.write_text('@book{bib1, title = "CHANGED"}\n', encoding="utf-8")

    phase = doc_status._phase_validate(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert "bibliography_sha256" in phase.detail


def test_validate_missing_declared_source_is_pending(tmp_path: Path) -> None:
    """TRIANGULATE: a vanished declared source cannot complete validation."""
    folder, pdf, bib = _opted_in_folder(tmp_path)
    _validation(folder, pdf=pdf, bibliography_sha256=_sha256(bib))
    bib.unlink()

    phase = doc_status._phase_validate(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING


def test_deliver_pair_required_for_opted_in_report(tmp_path: Path) -> None:
    """Only the complete matching pair counts as delivered for an opted-in report."""
    folder, pdf, bib = _opted_in_folder(tmp_path)
    root = tmp_path / "Documents"

    # A pdf-only copy is not the requested set.
    _published(root, category=f"{CATEGORY}/fisica", slug=SLUG, source=pdf)
    phase = doc_status._phase_deliver(folder, _config(folder), root)
    assert phase.state == doc_status.PENDING

    # A pair with a different .bib is not the requested set either.
    (root / CATEGORY / "fisica" / SLUG / f"{SLUG}-v001.bib").write_text(
        '@book{other, title = "OTHER"}\n', encoding="utf-8"
    )
    phase = doc_status._phase_deliver(folder, _config(folder), root)
    assert phase.state == doc_status.PENDING

    # The exact pair is.
    (root / CATEGORY / "fisica" / SLUG / f"{SLUG}-v001.bib").write_bytes(bib.read_bytes())
    phase = doc_status._phase_deliver(folder, _config(folder), root)
    assert phase.state == doc_status.DONE


def test_deliver_pdf_only_set_requires_no_sibling_bib(tmp_path: Path) -> None:
    """TRIANGULATE: switching from pair to pdf-only is not silently delivered."""
    folder = tmp_path / "wf"
    _report(folder)
    pdf = _pdf(folder)
    root = tmp_path / "Documents"
    _published(root, category=f"{CATEGORY}/fisica", slug=SLUG, source=pdf)
    (root / CATEGORY / "fisica" / SLUG / f"{SLUG}-v001.bib").write_text(
        '@book{old, title = "OLD"}\n', encoding="utf-8"
    )

    phase = doc_status._phase_deliver(folder, _config(folder), root)

    assert phase.state == doc_status.PENDING


def test_review_phase_uses_bibliography_binding_when_opted_in(tmp_path: Path) -> None:
    """The review phase agrees with the publisher on the declared set."""
    folder, pdf, bib = _opted_in_folder(tmp_path)

    _final_review(folder, pdf=pdf)
    phase = doc_status._phase_review(folder, _config(folder), None)
    assert phase.state == doc_status.PENDING
    assert phase.detail.startswith("warning: final_review_marker_malformed: ")

    _final_review(folder, pdf=pdf, bibliography=bib)
    phase = doc_status._phase_review(folder, _config(folder), None)
    assert phase.state == doc_status.DONE


# ---------------------------------------------------------------------------
# purity
# ---------------------------------------------------------------------------


def test_validate_and_deliver_derivations_never_write(tmp_path: Path) -> None:
    """Both late handlers only read: the folder listing is byte-identical after."""
    folder = tmp_path / "wf"
    pdf = _final_pdf(folder)
    _validation(folder, pdf=pdf)
    root = tmp_path / "Documents"
    _published(root, category=CATEGORY, slug=SLUG, source=pdf)
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    config = _config(folder)

    doc_status._phase_validate(folder, config, root)
    doc_status._phase_deliver(folder, config, root)

    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert after == before


# ---------------------------------------------------------------------------
# T3: publish_pdf._approval_refusal names body.md for a body-stale marker
# ---------------------------------------------------------------------------


def test_publish_refuses_body_stale_marker_and_names_body_md(tmp_path: Path) -> None:
    """A body edited after approval refuses publication and names body.md."""
    folder = tmp_path / "wf"
    _approval(folder)
    _body(folder, "# Informe\n\nOtro cuerpo.\n")
    source = tmp_path / "validated.pdf"
    source.write_bytes(b"%PDF-1.7\nvalidated content\n")
    documents = tmp_path / "Documents"

    with pytest.raises(publish_pdf.PublicationError) as exc:
        publish_pdf.publish_validated_pdf(
            source, "Academicos", "informe", documents, work_folder=folder
        )

    assert "body.md" in str(exc.value)
    assert not documents.exists()
