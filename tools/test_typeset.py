"""Typeset phase (issue #96, odd/tasks/plain-text-draft.md S4-S6).

After approval the plain-text ``body.md`` is formatted only in
``body.typeset.md``, bound to the approved bytes by ``typeset.yml``. Builds
render the typeset body while that binding is current; approvals recorded
before this change need no typeset.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

import approval_marker
import build_report_auto
import doc_status
import typeset
from conftest import DEFAULT_BODY, _approval, _choose_format, _config, _mtime, _pdf, _report, _sources_bib
from report_config import ReportConfig, read_yaml

T0 = 1_700_000_000.0
FORMATTED = "# Informe\n\nCuerpo del documento con fuentes [@key1], [@key2], [@key3], [@key4] y [@key5]; $e_a$.\n"


def _approved(tmp_path: Path, body: str = DEFAULT_BODY) -> Path:
    """A work folder whose current body.md was approved under the new contract."""
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    (folder / "body.md").write_text(body, encoding="utf-8")
    approval_marker.record_approval(folder, "Ana")
    return folder


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check(folder: Path) -> dict[str, dict]:
    return {item["check"]: item for item in typeset.check_results(folder)}


def test_record_approval_writes_typeset_required(tmp_path: Path) -> None:
    folder = _approved(tmp_path)

    assert read_yaml(folder / "approval.yml")["typeset"] == "required"
    assert approval_marker.approval_state(folder).state == "current"


def test_bind_refuses_without_approval_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    (folder / "body.md").write_text(DEFAULT_BODY, encoding="utf-8")
    before = sorted(p.name for p in folder.iterdir())

    assert typeset.main(["bind", str(folder)]) == 1

    err = capsys.readouterr().err
    assert "typeset not bound: body.md is not approved (approval.yml missing)" in err
    assert sorted(p.name for p in folder.iterdir()) == before


def test_bind_copies_the_approved_body_and_records_its_hash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _approved(tmp_path)

    assert typeset.main(["bind", str(folder)]) == 0

    assert (folder / "body.typeset.md").read_text(encoding="utf-8") == DEFAULT_BODY
    binding = read_yaml(folder / "typeset.yml")
    assert binding["schema"] == "academic.typeset/v1"
    assert binding["body_sha256"] == _sha(folder / "body.md")
    assert f"bound {folder / 'body.typeset.md'} to body.md" in capsys.readouterr().out


def test_bind_keeps_existing_typeset_text_and_rebinds(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    (folder / "body.typeset.md").write_text(FORMATTED, encoding="utf-8")

    assert typeset.main(["bind", str(folder)]) == 0

    assert (folder / "body.typeset.md").read_text(encoding="utf-8") == FORMATTED
    assert read_yaml(folder / "typeset.yml")["body_sha256"] == _sha(folder / "body.md")


def test_check_passes_a_bound_formatted_body(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _approved(tmp_path)
    (folder / "body.typeset.md").write_text(FORMATTED, encoding="utf-8")
    typeset.bind(folder)

    assert typeset.main(["check", str(folder)]) == 0
    assert all(item["ok"] for item in typeset.check_results(folder))
    assert "[ok] citations_match" in capsys.readouterr().out


def test_check_fails_when_body_changed_since_bind(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    typeset.bind(folder)
    (folder / "body.md").write_text(DEFAULT_BODY + "\nOtra linea.\n", encoding="utf-8")

    check = _check(folder)["binding"]

    assert check["ok"] is False
    assert "body.md changed since typeset" in check["detail"]


def test_check_applies_rendering_rules_to_the_typeset_body(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    (folder / "body.typeset.md").write_text(DEFAULT_BODY + "\nVelocidad 3 m/s\u00b2.\n", encoding="utf-8")
    typeset.bind(folder)

    check = _check(folder)["body_format"]

    assert check["ok"] is False and "line 5" in check["detail"] and "m/s$^2$" in check["detail"]


def test_check_requires_the_same_citations(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    (folder / "body.typeset.md").write_text(
        "# Informe\n\nCuerpo con [@key1], [@key2], [@key3], [@key4] y [@nueva].\n", encoding="utf-8"
    )
    typeset.bind(folder)

    check = _check(folder)["citations_match"]

    assert check["ok"] is False
    assert "missing: key5" in check["detail"] and "added: nueva" in check["detail"]


def test_check_enforces_fixed_format_headings_in_the_typeset_body(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    _choose_format(folder, "ape")
    typeset.bind(folder)

    check = _check(folder)["ape_structure"]

    assert check["ok"] is False


def _ape_typeset(tmp_path: Path, titles: tuple[str, ...]) -> Path:
    folder = _approved(tmp_path)
    _choose_format(folder, "ape")
    (folder / "body.typeset.md").write_text(
        "".join(f"# {title}\n\nTexto con [@key1].\n\n" for title in titles), encoding="utf-8"
    )
    typeset.bind(folder)
    return folder


def test_check_names_the_expected_ape_heading_when_a_title_is_wrong(tmp_path: Path) -> None:
    from validate_report import APE_BODY_HEADINGS

    titles = tuple("Materiales y Herramientas" if t.startswith("Materiales") else t for t in APE_BODY_HEADINGS)

    check = _check(_ape_typeset(tmp_path, titles))["ape_structure"]

    assert check["ok"] is False
    assert "Materiales, Reactivos, Equipos y Herramientas" in check["detail"]


def test_check_passes_the_correct_ape_headings(tmp_path: Path) -> None:
    from validate_report import APE_BODY_HEADINGS

    assert _check(_ape_typeset(tmp_path, APE_BODY_HEADINGS))["ape_structure"]["ok"] is True


def test_body_path_resolves_to_a_current_typeset_body(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    (folder / "body.typeset.md").write_text(FORMATTED, encoding="utf-8")
    typeset.bind(folder)

    assert _config(folder).body_path == folder / "body.typeset.md"

    (folder / "body.md").write_text(DEFAULT_BODY + "\nCambio.\n", encoding="utf-8")
    assert _config(folder).body_path == folder / "body.md"


def test_explicit_body_key_still_wins(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    typeset.bind(folder)

    config = ReportConfig(folder=folder, raw={**read_yaml(folder / "report.yml"), "body": "otro.md"})

    assert config.body_path == folder / "otro.md"


def test_phase_order_puts_typeset_between_format_and_generate() -> None:
    phases = doc_status.PHASES
    assert phases.index("format") + 1 == phases.index("typeset") == phases.index("generate") - 1


def test_phase_typeset_legacy_approval_is_done(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _approval(folder)

    phase = doc_status._phase_typeset(folder, _config(folder), None)

    assert phase.state == doc_status.DONE
    assert "legacy approval" in phase.detail


def test_phase_typeset_pending_until_bound_then_done(tmp_path: Path) -> None:
    folder = _approved(tmp_path)

    pending = doc_status._phase_typeset(folder, _config(folder), None)
    assert pending.state == doc_status.PENDING
    assert pending.detail == "body.typeset.md missing"
    guidance = doc_status._guidance("typeset", folder)
    assert "typeset.py" in guidance and "bind" in guidance and "never in" in guidance

    typeset.bind(folder)
    done = doc_status._phase_typeset(folder, _config(folder), None)
    assert done.state == doc_status.DONE


def test_phase_typeset_pending_with_failures(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    typeset.bind(folder)
    (folder / "body.md").write_text(DEFAULT_BODY + "\nCambio.\n", encoding="utf-8")

    phase = doc_status._phase_typeset(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert "binding: body.md changed since typeset" in phase.detail


def test_generate_pending_when_typeset_is_newer_than_the_pdf(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    typeset.bind(folder)
    _mtime(folder / "report.yml", T0)
    _mtime(folder / "approval.yml", T0 + 60)
    _pdf(folder, mtime=T0 + 120)
    _mtime(folder / "body.typeset.md", T0 + 180)

    phase = doc_status._phase_generate(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert "older than body.typeset.md" in phase.detail


def test_final_build_refuses_without_a_current_typeset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _approved(tmp_path)
    monkeypatch.setattr(sys, "argv", ["build_report_auto.py", str(folder)])
    monkeypatch.setattr(build_report_auto, "build_with_records", lambda *a: pytest.fail("built"))

    with pytest.raises(SystemExit) as exc:
        build_report_auto.main()

    assert "TYPESET REQUIRED" in str(exc.value)
    assert "body.typeset.md missing" in str(exc.value)


def test_build_gate_open_for_legacy_and_bound_typesets(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    _report(legacy)
    _approval(legacy)
    assert typeset.build_gate(legacy) is None

    folder = _approved(tmp_path)
    typeset.bind(folder)
    assert typeset.build_gate(folder) is None


PREVIEW_LINE = (
    "PREVIEW FINDINGS: el borrador es texto plano; el formato se corrige en "
    "body.typeset.md después de la aprobación, nunca en body.md."
)


class _Validation:
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        self.warnings: list[str] = []


def _run_build(
    folder: Path,
    monkeypatch: pytest.MonkeyPatch,
    flags: list[str],
    errors: list[str],
    build_error: BaseException | None = None,
) -> None:
    config = _config(folder)
    monkeypatch.setattr(sys, "argv", ["build_report_auto.py", str(folder), *flags])
    monkeypatch.setattr(build_report_auto, "load_report_config", lambda _f: config)
    monkeypatch.setattr(build_report_auto, "validate", lambda _c: _Validation(errors))
    monkeypatch.setattr(build_report_auto, "sha256_file", lambda _p: "h")

    def fake_build(_config: ReportConfig, _args: object) -> None:
        if build_error:
            raise build_error

    monkeypatch.setattr(build_report_auto, "build_backend", fake_build)
    build_report_auto.main()


def test_preview_build_reports_validation_errors_as_findings_and_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    (folder / "body.md").write_text(DEFAULT_BODY, encoding="utf-8")
    before = (folder / "body.md").read_bytes()

    _run_build(folder, monkeypatch, ["--no-approval-check"], ["La tabla 1 no cabe", "Figura sin pie"])

    out = capsys.readouterr().out
    assert PREVIEW_LINE in out.splitlines()
    assert "- La tabla 1 no cabe" in out
    assert "- Figura sin pie" in out
    assert "VALIDATION FAILED" not in out
    assert (folder / "body.md").read_bytes() == before


def test_preview_build_failure_still_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    (folder / "body.md").write_text(DEFAULT_BODY, encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        _run_build(
            folder, monkeypatch, ["--no-approval-check"], ["x"], build_error=SystemExit("latex failed")
        )

    assert str(exc.value) == "latex failed"


def test_final_build_validation_errors_still_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _approved(tmp_path)
    typeset.bind(folder)

    with pytest.raises(SystemExit) as exc:
        _run_build(folder, monkeypatch, [], ["La tabla 1 no cabe"])

    assert str(exc.value).startswith("VALIDATION FAILED:\n- La tabla 1 no cabe")
    assert PREVIEW_LINE not in capsys.readouterr().out


def test_approval_guidance_is_content_review_not_layout_repair() -> None:
    text = doc_status._GUIDANCE["approval"]

    assert "fix layout defects" not in text
    assert "content review" in text
    assert "body.typeset.md" in text
