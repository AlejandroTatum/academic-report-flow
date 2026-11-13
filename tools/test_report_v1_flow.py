"""Public contracts for the first formatted report version (v1).

S1/S2: v1 generation needs no draft approval and is not stopped by rubric
findings; publication keeps refusing unresolved rubric failures without an
accepted gap, unresolved citations and a missing human final review.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

import accepted_gaps
import approval_marker
import build_report_auto
import content_check
import deliver_report
import doc_status
import publish_pdf
import typeset
import validate_report
from conftest import _config, _declared_format, _final_review, _pdf, _validation, _verification
from test_rubric_trace import BODY, REQUIREMENTS, planned_folder

FOUND_ONLY = [item for item in REQUIREMENTS if item["status"] == "found"]


class _Validation:
    def __init__(self, errors: list[str] | None = None, findings: list[str] | None = None) -> None:
        self.errors = list(errors or [])
        self.warnings: list[str] = []
        self.findings = list(findings or [])


def _build(folder: Path, monkeypatch: pytest.MonkeyPatch, validation: _Validation | None = None) -> None:
    monkeypatch.setattr(build_report_auto, "build_backend", lambda config, args: _pdf(folder))
    monkeypatch.setattr(build_report_auto, "validate", lambda config: validation or _Validation())
    monkeypatch.setattr(sys, "argv", ["build_report_auto.py", str(folder)])
    build_report_auto.main()


def _v1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, *, body: str = BODY,
        requirements: list[dict] = REQUIREMENTS, review: bool = True,
        needs_person: list[dict] | None = None) -> tuple[Path, Path]:
    """A v1 built without draft approval, validated and (optionally) reviewed."""
    folder = planned_folder(tmp_path, body=body)
    if needs_person is not None:
        rubric = folder / "rubric.yml"
        data = yaml.safe_load(rubric.read_text(encoding="utf-8"))
        data["needs_person"] = needs_person
        rubric.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    _declared_format(folder, "libre")
    content_check.main([str(folder), "--verification", str(_verification(folder, requirements=requirements))])
    assert typeset.main(["bind", str(folder)]) == 0
    _build(folder, monkeypatch)
    pdf = folder / "final" / "report.pdf"
    _validation(folder, pdf=pdf)
    if review:
        _final_review(folder, pdf=pdf)
    capsys.readouterr()
    return folder, pdf


def _deliver_warned(folder: Path, documents: Path, capsys) -> str:
    """warn-only-gates S2: the gap is a ``warning:`` on stderr and the PDF is delivered."""
    review = folder / "final-review.yml"
    before = review.read_bytes() if review.is_file() else None
    assert deliver_report.main([str(folder), "--documents-root", str(documents)]) == 0
    output = capsys.readouterr()
    assert "CON ADVERTENCIAS" in output.out
    assert len(list(documents.rglob("*.pdf"))) == 1
    assert not (folder / "approval.yml").exists()
    assert (review.read_bytes() if review.is_file() else None) == before
    return output.err


def test_typeset_bind_needs_no_draft_approval(tmp_path: Path, capsys) -> None:
    folder = planned_folder(tmp_path)
    assert typeset.main(["bind", str(folder)]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert f"bound {folder / 'body.typeset.md'} to body.md" in output.out
    assert (folder / "body.typeset.md").read_bytes() == (folder / "body.md").read_bytes()
    assert not (folder / "approval.yml").exists()


def test_missing_rubric_findings_remain_visible_but_do_not_stop_route(tmp_path: Path, capsys) -> None:
    folder = planned_folder(tmp_path)
    verification = _verification(folder, requirements=REQUIREMENTS)
    assert content_check.main([str(folder), "--verification", str(verification)]) == 0
    capsys.readouterr()
    status = doc_status.derive(folder)
    verify = next(phase for phase in status.phases if phase.name == "verify")
    assert verify.state == doc_status.DONE
    assert "not a compliance pass" in verify.detail and "missing: Lists recommendations" in verify.detail
    assert status.next_token not in ("verify", "approval")
    assert not (folder / "approval.yml").exists()


def test_preexisting_rubric_failure_is_a_finding_and_still_a_validation_error(tmp_path: Path) -> None:
    folder = planned_folder(tmp_path, body=BODY.replace("topologia", "red"))
    result, findings = validate_report.rubric_validation_with_findings(_config(folder))
    assert result.errors and findings == result.errors
    assert any("metodologia" in error and "fails in body.md" in error for error in result.errors)
    assert validate_report.rubric_validation(_config(folder)).errors == result.errors


def test_generation_reports_rubric_findings_and_warns_on_other_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    folder = planned_folder(tmp_path)
    _declared_format(folder, "libre")
    assert typeset.main(["bind", str(folder)]) == 0
    capsys.readouterr()
    finding = "rubric: criterion 'metodologia' check 1 (contains) fails in body.typeset.md: missing"
    _build(folder, monkeypatch, _Validation(errors=[finding], findings=[finding]))
    out = capsys.readouterr().out
    assert "RUBRIC FINDINGS (no es una declaración de cumplimiento; son avisos y no impiden la entrega):\n- " + finding in out
    pdf = folder / "final" / "report.pdf"
    lines = out.splitlines()
    assert (
        f"PDF GENERADO CON HALLAZGOS DE RÚBRICA (no validado): {pdf} "
        f"(SHA-256: {approval_marker.sha256_file(pdf)}). No es una declaración de cumplimiento: "
        "revisá esta versión con el usuario y pedí una revisión (v2/v3); la entrega avisa "
        "estos hallazgos mientras sigan abiertos."
    ) in lines
    assert "VALIDADO" not in out
    assert "VALIDATION PASSED" not in out
    assert "FORMAT CHECKS PASSED; RUBRIC FINDINGS REMAIN" in lines
    assert approval_marker.generation_record_current(folder, folder / "final" / "report.pdf")
    assert not (folder / "approval.yml").exists()

    # warn-only-gates S2: another validation error warns; the build finishes and records v1.
    (folder / "build" / "generation.yml").unlink()
    _build(folder, monkeypatch, _Validation(errors=[finding, "La tabla 1 no cabe"], findings=[finding]))
    captured = capsys.readouterr()
    assert captured.err.startswith("warning: VALIDATION FAILED:\n- La tabla 1 no cabe\n")
    assert "PDF GENERADO CON ADVERTENCIAS DE VALIDACIÓN" in captured.out
    assert (folder / "build" / "generation.yml").is_file()


def test_generation_without_findings_keeps_the_validated_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    folder = planned_folder(tmp_path)
    _declared_format(folder, "libre")
    assert typeset.main(["bind", str(folder)]) == 0
    capsys.readouterr()
    _build(folder, monkeypatch)  # returns normally: exit code 0
    out = capsys.readouterr().out
    pdf = folder / "final" / "report.pdf"
    lines = out.splitlines()
    assert "VALIDATION PASSED" in lines
    assert (
        f"PDF GENERADO Y VALIDADO: {pdf} (SHA-256: {approval_marker.sha256_file(pdf)}). "
        "La entrega a ~/Documents es una fase separada: ejecutá tools/deliver_report.py."
    ) in lines
    assert "RUBRIC FINDINGS" not in out and "HALLAZGOS" not in out


def test_unresolved_citation_is_a_draft_warning_and_the_route_advances(tmp_path: Path, capsys) -> None:
    folder = planned_folder(tmp_path, body=BODY + "\nIncorrecta [@missing].\n")
    verification = _verification(folder, requirements=REQUIREMENTS)
    assert content_check.main([str(folder), "--verification", str(verification)]) == 0
    capsys.readouterr()
    status = doc_status.derive(folder)
    draft = next(phase for phase in status.phases if phase.name == "draft")
    # warn-only-gates S2: the body-check FAIL is a warning in the draft detail.
    assert draft.state == doc_status.DONE and draft.blocked_reason == ""
    assert status.next_token != "draft"
    assert draft.detail.startswith("warning: body_check_failed: body check fails: ")
    assert "citations_resolve" in draft.detail and "missing" in draft.detail


def test_missing_sources_still_stop_research(tmp_path: Path) -> None:
    from conftest import _body, _report, _rubric
    folder = tmp_path / "wf"
    _report(folder)
    _rubric(folder)
    _body(folder, "# Informe\n\nNo se dispone de evidencia suficiente.\n")
    status = doc_status.derive(folder)
    research = next(p for p in status.phases if p.name == "research")
    assert research.state == doc_status.CURRENT
    assert status.next_token == "research"


def test_v1_publishes_only_with_a_current_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    folder, pdf = _v1(tmp_path, monkeypatch, capsys, requirements=FOUND_ONLY)
    assert not (folder / "approval.yml").exists()
    assert doc_status.derive(folder).next_token == "deliver"
    documents = tmp_path / "docs"
    assert deliver_report.main([str(folder), "--documents-root", str(documents)]) == 0
    assert len(list(documents.rglob("*.pdf"))) == 1
    capsys.readouterr()
    (folder / "body.md").write_text("# Changed\n\nChanged content.\n")
    # warn-only-gates L3: without approval.yml the generated identity is the integrity anchor.
    assert deliver_report.main([str(folder), "--documents-root", str(documents)]) == 1
    err = capsys.readouterr().err
    assert err.startswith(f"DELIVERY REFUSED: {publish_pdf.GENERATION_REFUSAL}\n")
    assert len(list(documents.rglob("*.pdf"))) == 1


def test_publication_warns_on_unresolved_rubric_failures_without_an_accepted_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    folder, _ = _v1(tmp_path, monkeypatch, capsys)
    err = _deliver_warned(folder, tmp_path / "docs", capsys)
    assert err == (
        "warning: Hay fallas de rúbrica sin resolver y sin brecha aceptada "
        "(missing: Includes a network diagram; missing: Lists recommendations). "
        "Corregí el informe o, solo si el usuario lo decide, registrá la brecha parcial con "
        "accepted_gaps.py; el PDF se entrega igual.\n"
    )


def test_publication_warns_on_a_needs_person_partial_until_a_person_accepts_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    # faster-verify-loop S5: needs_person only labels the partial; it never accepts it.
    gap = "the ADR must be versioned in the repository; only the student can push it"
    partial = {"criterion": "metodologia", "requirement": "Includes a network diagram", "status": "partial",
               "location": "Metodologia", "evidence": "Se configuro la topologia", "gap": gap}
    folder, _ = _v1(tmp_path, monkeypatch, capsys, requirements=[*FOUND_ONLY, partial],
                    needs_person=[{"item": "G26", "reason": gap}])
    err = _deliver_warned(folder, tmp_path / "docs", capsys)
    assert err == (
        "warning: Hay fallas de rúbrica sin resolver y sin brecha aceptada "
        "(partial: Includes a network diagram). "
        "Corregí el informe o, solo si el usuario lo decide, registrá la brecha parcial con "
        "accepted_gaps.py; el PDF se entrega igual.\n"
    )
    assert accepted_gaps.main(["accept", str(folder), "--by", "Ana Perez", "--requirement",
                               "Includes a network diagram", "--reason", "pushed by the student"]) == 0
    capsys.readouterr()
    documents = tmp_path / "docs"
    assert deliver_report.main([str(folder), "--documents-root", str(documents)]) == 0
    assert capsys.readouterr().err == ""  # the accepted gap leaves nothing to warn about
    assert len(list(documents.rglob("*.pdf"))) == 1


def test_publication_warns_on_unresolved_citations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    folder, _ = _v1(tmp_path, monkeypatch, capsys, body=BODY + "\nIncorrecta [@missing].\n",
                    requirements=FOUND_ONLY)
    err = _deliver_warned(folder, tmp_path / "docs", capsys)
    assert err == (
        "warning: Hay citas sin resolver en body.md (5/6 cited keys resolve to bib entries; "
        "unresolved: missing). Corregí las citas y volvé a verificar y generar antes de publicar; "
        "el PDF se entrega igual.\n"
    )


def test_publication_warns_without_the_human_final_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    folder, pdf = _v1(tmp_path, monkeypatch, capsys, requirements=FOUND_ONLY, review=False)
    err = _deliver_warned(folder, tmp_path / "docs", capsys)
    assert err == (
        f"warning: falta final-review.yml en {folder}: falta la revisión humana final "
        f"de {pdf.name}. Ejecutá primero la fase review; el PDF se entrega igual.\n"
    )
    assert not (folder / "final-review.yml").exists()


def test_publishing_refuses_without_approval_or_generated_artifact_identity(tmp_path: Path, capsys) -> None:
    from conftest import _body, _report
    folder = tmp_path / "wf"
    _report(folder)
    _body(folder)
    pdf = _pdf(folder)
    _validation(folder, pdf=pdf)
    _final_review(folder, pdf=pdf)
    documents = tmp_path / "docs"
    assert deliver_report.main([str(folder), "--documents-root", str(documents)]) == 1
    assert capsys.readouterr().err.startswith(
        f"DELIVERY REFUSED: no hay approval.yml ni build/generation.yml en {folder}: falta la "
        "aprobación humana del cuerpo y la identidad del PDF generado."
    )
    assert not documents.exists()


def test_express_option_never_forges_approval(tmp_path: Path, capsys) -> None:
    from conftest import _report, _body
    folder = tmp_path / "wf"
    report = _report(folder, route="business")
    report.write_text(report.read_text() + "flow: express\n")
    _body(folder)
    assert approval_marker.main(["approve", str(folder), "--express"]) == 1
    assert "approval" in capsys.readouterr().err.lower()
    assert not (folder / "approval.yml").exists()


def test_publication_gate_refuses_an_unmapped_guide_inventory(tmp_path: Path) -> None:
    from test_doc_status_inventory import ALL_MAPPED, CRITERIA, verified_with_guide

    assert publish_pdf._content_refusal(verified_with_guide(tmp_path / "mapped", ALL_MAPPED)) is None
    refusal = publish_pdf._content_refusal(verified_with_guide(tmp_path / "unmapped", CRITERIA))
    assert refusal is not None
    assert refusal.startswith("La guía tiene ítems sin criterio ni entrada not_applicable en rubric.yml: G5")
    assert refusal.endswith(". No se publica nada.")
