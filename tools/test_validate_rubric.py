"""validate re-runs the rubric checks on body.typeset.md and the PDF text (skill-rubric-improvements T3, S3)."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import rubric_trace
import validate_report
from conftest import _config, _pdf
from test_rubric_trace import BODY, planned_folder

PAGES = ["Portada", "Objetivos\nAnalizar el protocolo de red", "Metodologia\nSe configuro la topologia\n\nConclusiones\nEl enlace opera"]


@pytest.fixture
def pdf_text(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    pages = [list(PAGES)]
    monkeypatch.setattr(rubric_trace, "pdf_pages", lambda path: pages[0])
    return pages


def bind_typeset(folder: Path, text: str) -> None:
    """Write body.typeset.md plus a binding to the current body.md bytes."""
    (folder / "body.typeset.md").write_text(text, encoding="utf-8")
    digest = hashlib.sha256((folder / "body.md").read_bytes()).hexdigest()
    (folder / "typeset.yml").write_text(f"schema: academic.typeset/v1\nbody_sha256: {digest}\n", encoding="utf-8")


def _folder(tmp_path: Path, typeset: str | None = None) -> Path:
    folder = planned_folder(tmp_path)
    _pdf(folder)
    if typeset is not None:
        bind_typeset(folder, typeset)
    return folder


def test_validate_passes_when_typeset_and_pdf_keep_the_checked_text(tmp_path: Path, pdf_text) -> None:
    folder = _folder(tmp_path, BODY + "\n![Diagrama](fig.png)\n")
    result = validate_report.rubric_validation(_config(folder))
    assert result.errors == [] and result.warnings == []


def test_validate_fails_when_typeset_loses_a_criterion_s_evidence(tmp_path: Path, pdf_text) -> None:
    folder = _folder(tmp_path, BODY.replace("topologia", "red"))
    result = validate_report.rubric_validation(_config(folder))
    assert len(result.errors) == 1
    assert "metodologia" in result.errors[0] and "topologia" in result.errors[0]
    assert "body.typeset.md" in result.errors[0] and "lost in typeset" in result.errors[0]


def test_validate_fails_when_the_pdf_text_loses_checked_text(tmp_path: Path, pdf_text) -> None:
    folder = _folder(tmp_path, BODY)
    pdf_text[0] = [PAGES[0], PAGES[1], "Metodologia\nSe configuro la topologia"]
    result = validate_report.rubric_validation(_config(folder))
    assert len(result.errors) == 1 and "conclusiones" in result.errors[0] and "PDF" in result.errors[0]


def test_validate_without_typeset_checks_body_md(tmp_path: Path, pdf_text) -> None:
    folder = _folder(tmp_path)
    assert validate_report.rubric_validation(_config(folder)).errors == []
    (folder / "body.md").write_text(BODY.replace("enlace", "vinculo"), encoding="utf-8")
    errors = validate_report.rubric_validation(_config(folder)).errors
    assert any("conclusiones" in e and "body.md" in e for e in errors)


def test_validate_skips_the_pdf_when_its_text_is_unavailable(tmp_path: Path, pdf_text) -> None:
    folder = _folder(tmp_path, BODY)
    pdf_text[0] = []
    result = validate_report.rubric_validation(_config(folder))
    assert result.errors == []
    assert any("PDF text unavailable" in w for w in result.warnings)


def test_validate_ignores_a_report_without_a_valid_rubric(tmp_path: Path, pdf_text) -> None:
    folder = _folder(tmp_path)
    (folder / "rubric.yml").unlink()
    result = validate_report.rubric_validation(_config(folder))
    assert result.errors == [] and result.warnings == []
    (folder / "rubric.yml").write_text("schema: nope\n", encoding="utf-8")
    result = validate_report.rubric_validation(_config(folder))
    assert result.errors == [] and any("rubric.yml" in w for w in result.warnings)


def test_validate_registers_the_rubric_check_and_propagates_its_errors(
    tmp_path: Path, pdf_text, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _folder(tmp_path, BODY.replace("topologia", "red"))
    empty = validate_report.ValidationResult
    for name in ("common_validation", "pdf_layout_validation", "validate_ieee", "asset_validation",
                 "connector_final_size_validation", "table_style_receipts_validation"):
        monkeypatch.setattr(validate_report, name, lambda *_a, _n=name, **_k: empty())
    monkeypatch.setattr(validate_report, "write_quality_report", lambda *_a, **_k: None)
    monkeypatch.setattr(validate_report, "write_table_style_receipts", lambda *_a, **_k: None)
    validation = validate_report.validate(_config(folder))
    assert "rubric" in validation.checks
    assert any("metodologia" in e for e in validation.errors)
