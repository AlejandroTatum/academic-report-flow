"""Tests for tools/deliver_report.py — the explicit deliver-phase entrypoint (#22).

Generation no longer publishes; delivery does, through the existing guarded
publisher (``publish_validated_pdf``). Delivery is thin: it adds the validation
receipt gate (``validation.yml`` with ``result: pass`` bound to the exact final
PDF bytes) on top of the publisher's approval gate, preserves hash continuity
across checking and copying, and creates no new states or human approvals.

Artifact shapes come from ``tools/conftest.py``; the Documents root is always a
temporary directory, never the real ``~/Documents``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS_DIR = str(Path(__file__).resolve().parent)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from conftest import (  # noqa: E402
    _approval,
    _bibliography,
    _declare_bibliography_delivery,
    _final_review,
    _pdf,
    _report,
    _sha256,
    _validation,
)
from deliver_report import main  # noqa: E402

import doc_status  # noqa: E402
import approval_marker  # noqa: E402
from report_config import ReportConfig, read_yaml  # noqa: E402

CATEGORY = "Academicos"
SLUG = "informe-de-laboratorio"


def _ready_folder(tmp_path: Path) -> tuple[Path, Path]:
    """A work folder with report, approved body, reviewed PDF and a passing receipt."""
    folder = tmp_path / "wf"
    _report(folder)
    _approval(folder)
    pdf = _pdf(folder)
    _validation(folder, pdf=pdf)
    _final_review(folder, pdf=pdf)
    return folder, pdf


def _run(folder: Path, documents_root: Path) -> int:
    return main([str(folder), "--documents-root", str(documents_root)])


# -- Happy path ---------------------------------------------------------------


def test_delivery_publishes_the_validated_bytes_once(tmp_path: Path) -> None:
    """A fully gated folder delivers the exact PDF bytes as v001."""
    folder, pdf = _ready_folder(tmp_path)
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 0

    # The default confirmed subject "Fisica" scopes its own ASCII course level.
    published = documents_root / CATEGORY / "fisica" / SLUG / f"{SLUG}-v001.pdf"
    assert published.is_file()
    assert _sha256(published) == _sha256(pdf)


def test_delivery_message_lists_gates_from_the_receipt(tmp_path: Path, capsys) -> None:
    """The granted/missing gate list is derived from validation.yml, not fixed.

    A receipt that recorded VISUAL_PASS must show it as granted; the old
    message unconditionally claimed "sin VISUAL_PASS" even when the receipt
    said otherwise (#33).
    """
    folder, pdf = _ready_folder(tmp_path)
    _validation(folder, pdf=pdf, gates=["BUILD_PASS", "VALIDATION_PASS", "VISUAL_PASS"])
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 0

    out = capsys.readouterr().out
    assert "VISUAL_PASS" in out
    assert "sin VISUAL_PASS" not in out
    assert "HUMAN_REVIEW" in out
    assert "READY_TO_SUBMIT" in out


def test_delivery_grants_current_human_review_but_not_other_gates(tmp_path: Path, capsys) -> None:
    folder, pdf = _ready_folder(tmp_path)
    _validation(folder, pdf=pdf, gates=['BUILD_PASS', 'VALIDATION_PASS'])
    assert _run(folder, tmp_path / 'docs') == 0
    out = capsys.readouterr().out
    assert 'gates otorgados: BUILD_PASS, VALIDATION_PASS, HUMAN_REVIEW' in out
    assert 'sin VISUAL_PASS, READY_TO_SUBMIT' in out
    assert 'sin HUMAN_REVIEW' not in out


def test_delivery_message_grants_no_gate_from_a_string(tmp_path: Path, capsys) -> None:
    """A malformed ``gates:`` string never turns substring matches into grants (#37).

    ``"VISUAL_PASS" in "BUILD_PASS NO_VISUAL_PASS"`` is true, so a naive
    membership check reports VISUAL_PASS as granted even though the receipt
    never listed it as a gate name.
    """
    folder, pdf = _ready_folder(tmp_path)
    _validation(folder, pdf=pdf, gates="BUILD_PASS NO_VISUAL_PASS")
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 0

    out = capsys.readouterr().out
    assert "gates otorgados: HUMAN_REVIEW" in out
    assert "VISUAL_PASS" in out  # only in the missing list, never as granted


def test_delivery_message_grants_no_gate_from_a_mapping(tmp_path: Path, capsys) -> None:
    """A malformed ``gates:`` mapping never turns key lookups into grants (#37)."""
    folder, pdf = _ready_folder(tmp_path)
    _validation(folder, pdf=pdf, gates={"VISUAL_PASS": False})
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 0

    out = capsys.readouterr().out
    assert "gates otorgados: HUMAN_REVIEW" in out


def test_delivery_is_idempotent_for_identical_bytes(tmp_path: Path, capsys) -> None:
    """A second delivery of the same bytes reuses the version, not a new one."""
    folder, _ = _ready_folder(tmp_path)
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 0
    assert _run(folder, documents_root) == 0

    published = documents_root / CATEGORY / "fisica" / SLUG
    assert len(list(published.iterdir())) == 1
    assert "REUTILIZADO" in capsys.readouterr().out


# -- Validation receipt gate ----------------------------------------------------


def test_delivery_refuses_missing_validation_receipt(tmp_path: Path, capsys) -> None:
    """No validation.yml means no delivery, and nothing is created."""
    folder, _ = tmp_path / "wf", None
    _report(folder)
    _approval(folder)
    _pdf(folder)
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 1

    captured = capsys.readouterr()
    assert "validation.yml" in captured.err
    assert not (documents_root / CATEGORY).exists()


def test_delivery_refuses_failed_validation_receipt(tmp_path: Path) -> None:
    """A recorded ``result: fail`` is a refusal, never a delivery."""
    folder, _ = _ready_folder(tmp_path)
    _validation(folder, result="fail")
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 1
    assert not (documents_root / CATEGORY).exists()


def test_delivery_refuses_receipt_bound_to_other_bytes(tmp_path: Path) -> None:
    """The receipt's artifact_sha256 must match the current final PDF bytes."""
    folder, _ = _ready_folder(tmp_path)
    _validation(folder, artifact_sha256="0" * 64)
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 1
    assert not (documents_root / CATEGORY).exists()


def test_delivery_refuses_pdf_changed_after_validation(tmp_path: Path) -> None:
    """Editing the PDF after the receipt stales the evidence: delivery refuses."""
    folder, pdf = _ready_folder(tmp_path)
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\nedited after validation\n")
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 1
    assert not (documents_root / CATEGORY).exists()


# -- Approval gate (enforced by the shared publisher) ---------------------------


def test_delivery_refuses_without_current_approval(tmp_path: Path, capsys) -> None:
    """Without a current approval.yml the publisher refuses and nothing appears."""
    folder = tmp_path / "wf"
    _report(folder)
    pdf = _pdf(folder)
    _validation(folder)
    _final_review(folder, pdf=pdf)
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 1

    captured = capsys.readouterr()
    assert "aprobación" in captured.err
    assert not (documents_root / CATEGORY).exists()


def test_delivery_refuses_stale_approval(tmp_path: Path) -> None:
    """A stale marker (edited body) is refused by the publisher."""
    folder = tmp_path / "wf"
    _report(folder)
    _approval(folder)
    pdf = _pdf(folder)
    _validation(folder)
    _final_review(folder, pdf=pdf)
    (folder / "body.md").write_text("edited after approval\n", encoding="utf-8")
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 1
    assert not (documents_root / CATEGORY).exists()


def test_delivery_accepts_an_approval_carried_across_a_bounded_edit(tmp_path: Path) -> None:
    """A name fix after approval keeps the approval: the publisher publishes."""
    import approval_marker

    folder = tmp_path / "wf"
    _report(folder)
    body = folder / "body.md"
    body.write_text("# Informe\n\nPreparado por Juan Perez.\n", encoding="utf-8")
    approval_marker.record_approval(folder, "Alejandro")
    pdf = _pdf(folder)
    _validation(folder, pdf=pdf)
    _final_review(folder, pdf=pdf)
    body.write_text("# Informe\n\nPreparado por Ana Perez.\n", encoding="utf-8")
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 0
    assert (documents_root / CATEGORY).exists()


def test_delivery_refuses_an_approval_stale_after_an_unbounded_edit(tmp_path: Path) -> None:
    import approval_marker

    folder = tmp_path / "wf"
    _report(folder)
    body = folder / "body.md"
    body.write_text("# Informe\n\nPreparado por Juan Perez.\n", encoding="utf-8")
    approval_marker.record_approval(folder, "Alejandro")
    pdf = _pdf(folder)
    _validation(folder, pdf=pdf)
    _final_review(folder, pdf=pdf)
    body.write_text("# Informe\n\n" + " ".join(["nuevo"] * 41) + "\n", encoding="utf-8")
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 1
    assert not (documents_root / CATEGORY).exists()


def test_delivery_accepts_a_final_review_carried_across_a_bounded_edit(tmp_path: Path) -> None:
    """A name fix after the final review: rebuild and validate again, then publish without re-asking."""
    import final_review_marker

    folder = tmp_path / "wf"
    _report(folder)
    body = folder / "body.md"
    body.write_text("# Informe\n\nPreparado por Juan Perez.\n", encoding="utf-8")
    approval_marker.record_approval(folder, "Alejandro")
    pdf = _pdf(folder)
    final_review_marker.record_final_review(folder, "Alejandro", pdf)
    body.write_text("# Informe\n\nPreparado por Ana Perez.\n", encoding="utf-8")
    pdf.write_bytes(pdf.read_bytes() + b"rebuilt\n")
    _validation(folder, pdf=pdf)
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 0
    assert (documents_root / CATEGORY).exists()


def test_delivery_refuses_a_final_review_stale_after_an_unbounded_edit(tmp_path: Path) -> None:
    import final_review_marker

    folder = tmp_path / "wf"
    _report(folder)
    body = folder / "body.md"
    body.write_text("# Informe\n\nPreparado por Juan Perez.\n", encoding="utf-8")
    approval_marker.record_approval(folder, "Alejandro")
    pdf = _pdf(folder)
    final_review_marker.record_final_review(folder, "Alejandro", pdf)
    pdf.write_bytes(pdf.read_bytes() + b"rebuilt\n")
    body.write_text("# Informe\n\nPreparado por Juan Perez.\n" + " ".join(["nuevo"] * 41) + "\n", encoding="utf-8")
    approval_marker.record_approval(folder, "Alejandro")
    _validation(folder, pdf=pdf)
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 1
    assert not (documents_root / CATEGORY).exists()


# -- Final review gate ---------------------------------------------------------


def test_delivery_refuses_missing_final_review_marker(tmp_path: Path, capsys) -> None:
    """The human must review the final PDF before delivery; no marker, no delivery."""
    folder, _ = _ready_folder(tmp_path)
    (folder / "final-review.yml").unlink()
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 1

    captured = capsys.readouterr()
    assert "final-review.yml" in captured.err
    assert "revisión humana final" in captured.err
    assert not (documents_root / CATEGORY).exists()


def test_delivery_refuses_stale_final_review_marker(tmp_path: Path, capsys) -> None:
    """A marker whose pdf_sha256 no longer matches the PDF bytes refuses delivery."""
    folder, pdf = _ready_folder(tmp_path)
    _final_review(folder, pdf=pdf, pdf_sha256="0" * 64)
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 1

    captured = capsys.readouterr()
    assert "final-review.yml" in captured.err
    assert pdf.name in captured.err
    assert not (documents_root / CATEGORY).exists()


def test_delivery_refuses_malformed_final_review_marker(tmp_path: Path, capsys) -> None:
    """An unparsable final-review.yml refuses delivery; the marker is never repaired."""
    folder, _ = _ready_folder(tmp_path)
    (folder / "final-review.yml").write_text("pdf_sha256: [unclosed\n", encoding="utf-8")
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 1

    captured = capsys.readouterr()
    assert "final-review.yml es inválido" in captured.err
    assert not (documents_root / CATEGORY).exists()


# -- Basic input checks ---------------------------------------------------------


def test_delivery_refuses_missing_final_pdf(tmp_path: Path) -> None:
    """No final PDF, no delivery."""
    folder = tmp_path / "wf"
    _report(folder)
    _approval(folder)
    # Receipt bound to some bytes; the final PDF itself is absent.
    stray = tmp_path / "elsewhere.pdf"
    stray.write_bytes(b"%PDF-1.4\n%%EOF\n")
    _validation(folder, pdf=stray)
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 1
    assert not (documents_root / CATEGORY).exists()


# -- Subject-scoped academic delivery (course-deliverables-hierarchy T1) --------


def test_delivery_publishes_under_the_canonical_subject_folder(tmp_path: Path) -> None:
    """An academic report with a canonical subject delivers into the course level."""
    folder = tmp_path / "wf"
    _report(folder, subject="Sistemas Operativos")
    _approval(folder)
    pdf = _pdf(folder)
    _validation(folder, pdf=pdf)
    _final_review(folder, pdf=pdf)
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 0

    published = (
        documents_root / "Academicos" / "sistemas-operativos" / SLUG / f"{SLUG}-v001.pdf"
    )
    assert published.is_file()
    assert _sha256(published) == _sha256(pdf)


def test_delivery_publishes_under_a_newly_named_course_folder(tmp_path: Path) -> None:
    """A confirmed subject without a registered alias gets its own course level."""
    folder = tmp_path / "wf"
    _report(folder, subject="Fisica")
    _approval(folder)
    pdf = _pdf(folder)
    _validation(folder, pdf=pdf)
    _final_review(folder, pdf=pdf)
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 0

    published = documents_root / "Academicos" / "fisica" / SLUG / f"{SLUG}-v001.pdf"
    assert published.is_file()
    assert _sha256(published) == _sha256(pdf)


def test_nonacademic_delivery_keeps_the_category_folder(tmp_path: Path) -> None:
    """A project route never gains a subject level: Proyectos/<slug>/ stays."""
    folder = tmp_path / "wf"
    _report(folder, route="project")
    _approval(folder)
    pdf = _pdf(folder)
    _validation(folder, pdf=pdf)
    _final_review(folder, pdf=pdf)
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 0

    published = documents_root / "Proyectos" / SLUG / f"{SLUG}-v001.pdf"
    assert published.is_file()
    assert not (documents_root / "Proyectos" / "fisica").exists()


def test_canonical_alias_spelling_delivers_to_the_same_versioned_folder(tmp_path: Path, capsys) -> None:
    """Two alias spellings of one course land together; the second is a reuse."""
    documents_root = tmp_path / "docs"
    for subject in ("Sistema operativo", "Sistemas Operativos"):
        folder = tmp_path / f"wf-{subject.split()[0].lower()}-{len(subject)}"
        _report(folder, subject=subject)
        _approval(folder)
        pdf = _pdf(folder)
        _validation(folder, pdf=pdf)
        _final_review(folder, pdf=pdf)
        assert _run(folder, documents_root) == 0

    published = sorted(
        (documents_root / "Academicos" / "sistemas-operativos" / SLUG).iterdir()
    )
    assert [path.name for path in published] == [f"{SLUG}-v001.pdf"]
    assert "REUTILIZADO" in capsys.readouterr().out


def test_refused_delivery_never_creates_the_subject_folder(tmp_path: Path, capsys) -> None:
    """A missing receipt refuses before the course level exists on disk."""
    folder = tmp_path / "wf"
    _report(folder, subject="Sistemas Operativos")
    _approval(folder)
    _pdf(folder)
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 1

    assert "validation.yml" in capsys.readouterr().err
    assert not (documents_root / "Academicos").exists()


def test_doc_status_agrees_with_the_delivered_subject_folder(tmp_path: Path) -> None:
    """After a real delivery, the status derivation reads the same folder."""
    folder = tmp_path / "wf"
    _report(folder, subject="Sistemas Operativos")
    _approval(folder)
    pdf = _pdf(folder)
    _validation(folder, pdf=pdf)
    _final_review(folder, pdf=pdf)
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 0

    config = ReportConfig(folder=folder, raw=read_yaml(folder / "report.yml"))
    phase = doc_status._phase_deliver(folder, config, documents_root)

    assert phase.state == doc_status.DONE
    assert f"{SLUG}-v001.pdf" in phase.detail


# -- Declared bibliography delivery (course-deliverables-hierarchy T2) ----------


def _ready_pair_folder(tmp_path: Path, *, name: str = "sources.bib") -> tuple[Path, Path, Path]:
    """A work folder gated for pair delivery: PDF + declared bibliography."""
    folder = tmp_path / "wf"
    _report(folder)
    _approval(folder)
    pdf = _pdf(folder)
    bib = _bibliography(folder, name=name)
    _declare_bibliography_delivery(folder, name=name)
    _validation(folder, pdf=pdf, bibliography_sha256=_sha256(bib))
    _final_review(folder, pdf=pdf, bibliography=bib)
    return folder, pdf, bib


def test_delivery_with_requested_bibliography_publishes_the_exact_pair(tmp_path: Path) -> None:
    """An opted-in report delivers <slug>-v001.pdf and the same-version .bib."""
    folder, pdf, bib = _ready_pair_folder(tmp_path)
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 0

    pair = documents_root / "Academicos" / "fisica" / SLUG
    assert (pair / f"{SLUG}-v001.pdf").is_file()
    assert (pair / f"{SLUG}-v001.bib").read_bytes() == bib.read_bytes()
    assert _sha256(pair / f"{SLUG}-v001.pdf") == _sha256(pdf)


def test_delivery_without_opt_in_never_copies_sources_bib(tmp_path: Path) -> None:
    """sources.bib existing alone never travels: PDF-only stays the default."""
    folder, _ = _ready_folder(tmp_path)
    _bibliography(folder)
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 0

    delivered = documents_root / "Academicos" / "fisica" / SLUG
    assert [path.name for path in delivered.iterdir()] == [f"{SLUG}-v001.pdf"]


def test_delivery_refuses_receipt_without_bibliography_hash(tmp_path: Path, capsys) -> None:
    """An opted-in delivery requires validation.yml to bind the bibliography bytes."""
    folder, _, _ = _ready_pair_folder(tmp_path)
    _validation(folder, drop=("bibliography_sha256",))
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 1

    assert "bibliography_sha256" in capsys.readouterr().err
    assert not (documents_root / "Academicos").exists()


def test_delivery_refuses_stale_bibliography_receipt_hash(tmp_path: Path) -> None:
    """Editing the bibliography after validation stales the receipt: refusal."""
    folder, _, bib = _ready_pair_folder(tmp_path)
    bib.write_text('@book{bib1, title = "EDITED"}\n', encoding="utf-8")
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 1
    assert not (documents_root / "Academicos").exists()


def test_delivery_refuses_final_review_without_bibliography_binding(tmp_path: Path, capsys) -> None:
    """The human final review must have covered the declared bibliography too."""
    folder, pdf, _ = _ready_pair_folder(tmp_path)
    _final_review(folder, pdf=pdf)  # pdf-only marker: no bibliography_sha256
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 1

    assert "bibliography_sha256" in capsys.readouterr().err
    assert not (documents_root / "Academicos").exists()


def test_delivery_refuses_missing_declared_source_before_any_destination(tmp_path: Path) -> None:
    """A declared source that vanished refuses before the tree is created."""
    folder, _, bib = _ready_pair_folder(tmp_path)
    bib.unlink()
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 1
    assert not documents_root.exists()


def test_doc_status_agrees_with_the_delivered_pair(tmp_path: Path) -> None:
    """After a pair delivery the status derivation reads the same complete set."""
    folder, _, _ = _ready_pair_folder(tmp_path)
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 0

    config = ReportConfig(folder=folder, raw=read_yaml(folder / "report.yml"))
    phase = doc_status._phase_deliver(folder, config, documents_root)

    assert phase.state == doc_status.DONE
    assert f"{SLUG}-v001.pdf" in phase.detail


def test_inspected_and_reviewed_pdf_reports_visual_pass_and_ready_to_submit(tmp_path: Path, capsys) -> None:
    folder, pdf = _ready_folder(tmp_path)
    _validation(folder, pdf=pdf, gates=["BUILD_PASS", "VALIDATION_PASS", "VISUAL_PASS"])
    assert _run(folder, tmp_path / "docs") == 0
    out = capsys.readouterr().out
    assert (
        "gates otorgados: BUILD_PASS, VALIDATION_PASS, VISUAL_PASS, HUMAN_REVIEW, READY_TO_SUBMIT"
    ) in out
    assert "sin " not in out


def test_ready_to_submit_needs_visual_pass_in_the_receipt(tmp_path: Path, capsys) -> None:
    folder, pdf = _ready_folder(tmp_path)
    _validation(folder, pdf=pdf, gates=["BUILD_PASS", "VALIDATION_PASS"])
    assert _run(folder, tmp_path / "docs") == 0
    out = capsys.readouterr().out
    assert "sin VISUAL_PASS, READY_TO_SUBMIT" in out


# -- delivery_dir override ------------------------------------------------------


def _set_delivery_dir(folder: Path, value: str) -> None:
    report = folder / "report.yml"
    report.write_text(report.read_text(encoding="utf-8") + f"delivery_dir: {value}\n", encoding="utf-8")


def test_delivery_dir_override_receives_the_versioned_pdf(tmp_path: Path) -> None:
    folder, pdf = _ready_folder(tmp_path)
    target = tmp_path / "course" / "unidad-1" / "ape-1" / "documento"
    _set_delivery_dir(folder, str(target))
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) == 0
    assert _run(folder, documents_root) == 0  # idempotent: same bytes reuse v001

    assert [p.name for p in target.iterdir()] == [f"{SLUG}-v001.pdf"]
    assert _sha256(target / f"{SLUG}-v001.pdf") == _sha256(pdf)
    assert not documents_root.exists()


def test_delivery_dir_override_increments_versions_in_its_folder(tmp_path: Path) -> None:
    folder, pdf = _ready_folder(tmp_path)
    target = tmp_path / "course" / "documento"
    _set_delivery_dir(folder, str(target))
    assert _run(folder, tmp_path / "docs") == 0

    pdf.write_bytes(pdf.read_bytes() + b"\n% changed\n")
    _validation(folder, pdf=pdf)
    _final_review(folder, pdf=pdf)
    assert _run(folder, tmp_path / "docs") == 0

    assert sorted(p.name for p in target.iterdir()) == [f"{SLUG}-v001.pdf", f"{SLUG}-v002.pdf"]


def test_delivery_dir_invalid_value_refuses_delivery(tmp_path: Path) -> None:
    folder, _pdf_path = _ready_folder(tmp_path)
    _set_delivery_dir(folder, "''")
    documents_root = tmp_path / "docs"

    assert _run(folder, documents_root) != 0
    assert not documents_root.exists()


def test_without_delivery_dir_the_default_folder_is_unchanged(tmp_path: Path) -> None:
    folder, _pdf_path = _ready_folder(tmp_path)
    assert _run(folder, tmp_path / "docs") == 0
    assert (tmp_path / "docs" / CATEGORY / "fisica" / SLUG / f"{SLUG}-v001.pdf").is_file()
