"""Review-phase tests for ``tools/doc_status.py`` with a carried final review.

A bounded edit after the final review keeps it, provided the current PDF has a
passing validation receipt; the phase reports ``done`` with the carried detail.
"""
from __future__ import annotations

from pathlib import Path

import doc_status
import final_review_marker
from conftest import _body, _config, _pdf, _report, _validation

BODY = "# Informe\n\nPreparado por Juan Perez.\n"


def _reviewed(folder: Path) -> Path:
    _report(folder)
    body = _body(folder, BODY)
    pdf = _pdf(folder)
    final_review_marker.record_final_review(folder, "Alejandro", pdf)
    return body


def test_a_bounded_edit_after_review_reports_done_with_the_carried_detail(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    body = _reviewed(folder)
    body.write_text(BODY.replace("Juan", "Ana"), encoding="utf-8")
    pdf = _pdf(folder)
    pdf.write_bytes(pdf.read_bytes() + b"rebuilt\n")
    _validation(folder, pdf=pdf)

    phase = doc_status._phase_review(folder, _config(folder), None)

    assert phase.state == doc_status.DONE
    assert phase.detail == "bounded edit since final review (2 words)"


def test_a_rebuilt_pdf_without_a_passing_validation_is_still_pending(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    body = _reviewed(folder)
    body.write_text(BODY.replace("Juan", "Ana"), encoding="utf-8")
    pdf = _pdf(folder)
    pdf.write_bytes(pdf.read_bytes() + b"rebuilt\n")

    phase = doc_status._phase_review(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING


def test_an_unbounded_edit_after_review_is_still_pending(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    body = _reviewed(folder)
    body.write_text("# Otro titulo\n\nPreparado por Juan Perez.\n", encoding="utf-8")
    pdf = _pdf(folder)
    pdf.write_bytes(pdf.read_bytes() + b"rebuilt\n")
    _validation(folder, pdf=pdf)

    assert doc_status._phase_review(folder, _config(folder), None).state == doc_status.PENDING
