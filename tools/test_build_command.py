"""`build.py`: one command chains typeset, generate and validate (odd/tasks/build-command.md S1-S7).

The LaTeX build and the validators are stubbed exactly as ``test_report_v1_flow``
stubs them, so the chain is exercised through ``build.main`` without a compile.
"""
from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path

import pytest
import yaml

import approval_marker
import build
import build_report_auto
import doc_status
import typeset
from conftest import _approval, _declared_format, _pdf
from test_rubric_trace import BODY, listing, planned_folder

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_MD = ROOT / "skills" / "academic-report-flow" / "references" / "production.md"
PORTAL_MD = ROOT / "docs" / "portal" / "mejoras-skill.qmd"
NO_COLUMN_NAMES = BODY + "\n- Router; 3; activo\n- Switch; 2; activo\n"


class _Validation:
    def __init__(self, errors: list[str] | None = None) -> None:
        self.errors = list(errors or [])
        self.warnings: list[str] = []
        self.findings: list[str] = []


def _folder(tmp_path: Path, body: str = BODY, name: str = "wf") -> Path:
    folder = planned_folder(tmp_path / name, body=body)
    _declared_format(folder, "libre")
    return folder


def _stub_build(monkeypatch: pytest.MonkeyPatch, validation: _Validation | None = None) -> list[Path]:
    """Record every backend build; the PDF it writes is the fixture PDF."""
    calls: list[Path] = []

    def backend(config, args) -> None:
        calls.append(config.folder)
        _pdf(config.folder)

    monkeypatch.setattr(build_report_auto, "build_backend", backend)
    monkeypatch.setattr(build_report_auto, "validate", lambda config: validation or _Validation())
    return calls


def _phases(folder: Path) -> list[tuple[str, str]]:
    path = folder / "timings.yml"
    entries = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else []
    return [(entry["phase"], entry["tool"]) for entry in entries or []]


def _validate_line(folder: Path) -> str:
    return (
        f"left for validate: inspect every page of {folder / 'final' / 'report.pdf'} and record "
        f"{folder / 'validation.yml'}; build.py never writes it"
    )


# S2 -------------------------------------------------------------------------


def test_typeset_step_prints_exactly_what_typeset_auto_prints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    twin = _folder(tmp_path, name="twin")
    assert typeset.main(["auto", str(twin)]) == 0
    expected = capsys.readouterr().out.replace(str(twin), "<folder>")
    folder = _folder(tmp_path)
    _stub_build(monkeypatch)

    assert build.main([str(folder)]) == 0

    out = capsys.readouterr().out
    typeset_part = out.split("step 1/2: typeset\n", 1)[1].split("step 2/2: generate and validate\n", 1)[0]
    assert typeset_part.replace(str(folder), "<folder>") == expected
    assert (folder / "body.typeset.md").read_bytes() == (twin / "body.typeset.md").read_bytes()


def test_failing_typeset_check_builds_nothing_and_says_to_run_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path, NO_COLUMN_NAMES)
    calls = _stub_build(monkeypatch)

    assert build.main([str(folder)]) == 1

    output = capsys.readouterr()
    assert "  left for you: line 13: table without column names: name its 3 columns" in output.out
    assert "  [FAIL] table_headers: line 13: table without column names" in output.out
    assert "step 2/2" not in output.out
    assert output.err == (
        f"build stopped: typeset is not finished. Finish {folder / 'body.typeset.md'} "
        f"(never body.md), then run build.py {folder} again; nothing was built.\n"
    )
    assert calls == []
    assert not (folder / "final").exists() and not (folder / "build").exists()
    assert _phases(folder) == [("typeset", "typeset.py")]


def test_refused_bind_writes_nothing_and_builds_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    assert typeset.main(["bind", str(folder)]) == 0
    (folder / "body.md").write_text(BODY.replace("tres routers", "cuatro routers"), encoding="utf-8")
    capsys.readouterr()
    before = listing(folder)
    calls = _stub_build(monkeypatch)

    assert build.main([str(folder)]) == 1

    output = capsys.readouterr()
    assert output.err.startswith("typeset not bound: the body.md edit is not in body.typeset.md (missing: ")
    assert output.err.endswith(
        f"build stopped: typeset is not finished. Finish {folder / 'body.typeset.md'} "
        f"(never body.md), then run build.py {folder} again; nothing was built.\n"
    )
    assert output.out == "step 1/2: typeset\n"
    assert calls == []
    assert listing(folder) == before


def test_typeset_step_is_skipped_when_the_report_does_not_use_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    _approval(folder)  # legacy: no `typeset: required`, nothing bound
    assert not typeset.typeset_in_use(folder)
    calls = _stub_build(monkeypatch)

    assert build.main([str(folder)]) == 0

    out = capsys.readouterr().out
    assert out.startswith(
        "step 1/2: typeset skipped: this report renders body.md (approval.yml predates typeset)\n"
        "step 2/2: generate and validate\n"
    )
    assert calls == [folder]
    assert not (folder / "body.typeset.md").exists()
    assert _phases(folder) == [("generate", "build_report_auto.py")]


# S3 -------------------------------------------------------------------------


def test_generate_step_runs_build_report_auto_and_keeps_its_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    calls = _stub_build(monkeypatch)

    assert build.main([str(folder)]) == 0

    out = capsys.readouterr().out
    pdf = folder / "final" / "report.pdf"
    generate_part = out.split("step 2/2: generate and validate\n", 1)[1].splitlines()
    assert generate_part == [
        "Tipo: ensayo | backend: latex | output: pdf",
        "VALIDATION PASSED",
        f"PDF GENERADO Y VALIDADO: {pdf} (SHA-256: {approval_marker.sha256_file(pdf)}). "
        "La entrega a ~/Documents es una fase separada: ejecutá tools/deliver_report.py.",
        f"Reporte: {folder / 'backups' / 'quality_report.md'}",
        _validate_line(folder),
    ]
    assert calls == [folder]
    assert approval_marker.draft_record_path(pdf).is_file()


def test_failed_validation_exits_like_build_report_auto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    _stub_build(monkeypatch, _Validation(errors=["La tabla 1 no cabe"]))

    assert build.main([str(folder)]) == 1

    output = capsys.readouterr()
    assert output.err == (
        "VALIDATION FAILED:\n- La tabla 1 no cabe\n\n"
        f"Reporte: {folder / 'backups' / 'quality_report.md'}\n"
    )
    assert "left for validate" not in output.out
    assert not (folder / "build" / "generation.yml").exists()


def test_build_offers_no_option_that_skips_a_gate(capsys: pytest.CaptureFixture[str]) -> None:
    for option in ("--no-approval-check", "--validate-only", "--tex-only"):
        with pytest.raises(SystemExit) as exc:
            build.main([option, "wf"])
        assert exc.value.code == 2
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        build.main(["--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "--no-approval-check" not in help_text and "--validate-only" not in help_text


# S4 -------------------------------------------------------------------------


def test_successful_build_leaves_validation_to_the_validate_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    _stub_build(monkeypatch)

    assert build.main([str(folder)]) == 0

    out = capsys.readouterr().out
    assert out.splitlines()[-1] == _validate_line(folder)
    assert "VISUAL_PASS" not in out
    for name in ("validation.yml", "approval.yml", "final-review.yml"):
        assert not (folder / name).exists(), name
    assert (folder / "body.md").read_text(encoding="utf-8") == BODY


# S5 -------------------------------------------------------------------------


def test_each_step_records_its_existing_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    _stub_build(monkeypatch)

    assert build.main([str(folder)]) == 0

    assert _phases(folder) == [("typeset", "typeset.py"), ("generate", "build_report_auto.py")]


# S6 -------------------------------------------------------------------------


def _build_command(folder: Path) -> str:
    return shlex.join([sys.executable, str(ROOT / "tools" / "build.py"), str(folder)])


def test_typeset_and_generate_guidance_name_the_single_command(tmp_path: Path) -> None:
    folder = tmp_path / "wf con espacios"
    command = _build_command(folder)

    typeset_guidance = doc_status._guidance("typeset", folder)
    generate_guidance = doc_status._guidance("generate", folder)

    assert generate_guidance == f"build with {command}, then re-run doc_status"
    assert f"run {command}" in typeset_guidance
    assert "build_report_auto.py" not in generate_guidance
    assert "typeset.py check" not in typeset_guidance and "run typeset.py" not in typeset_guidance
    for hand_work in ("left for you", "table column names", "formulas as math", "fixed headings",
                      "never in " + str(folder / "body.md"), "keep every word and [@key]"):
        assert hand_work in typeset_guidance, hand_work


def test_existing_commands_keep_working(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _folder(tmp_path)
    assert typeset.main(["auto", str(folder)]) == 0
    assert typeset.main(["check", str(folder)]) == 0
    assert typeset.main(["bind", str(folder)]) == 0
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        sys_argv = sys.argv
        sys.argv = ["build_report_auto.py", "--help"]
        try:
            build_report_auto.main()
        finally:
            sys.argv = sys_argv
    assert exc.value.code == 0
    assert "--no-approval-check" in capsys.readouterr().out


# S7 -------------------------------------------------------------------------


def test_help_docstring_and_docs_describe_the_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        build.main(["--help"])
    help_text = re.sub(r"\s+", " ", capsys.readouterr().out)
    for phrase in ("typeset.py auto", "build_report_auto.py", "validation.yml", "folder"):
        assert phrase in help_text, phrase
    assert "typeset.py auto" in build.__doc__ and "build_report_auto.py" in build.__doc__

    production = re.sub(r"\s+", " ", PRODUCTION_MD.read_text(encoding="utf-8"))
    assert '"$REPORT_PYTHON" "$REPORT_AUTOMATION_ROOT/tools/build.py" "$REPORT_CONTENT_ROOT/reports/<work-folder>/"' in production
    portal = PORTAL_MD.read_text(encoding="utf-8")
    assert "`tools/build.py`" in portal


def test_first_build_stops_once_for_items_the_checks_do_not_cover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    built = _stub_build(monkeypatch)
    folder = _folder(tmp_path, BODY + "\nEl error es e = |x1 - x0| / |x1|.\n")

    assert build.main([str(folder)]) == 1

    captured = capsys.readouterr()
    assert "left for you: " in captured.out and "possible formula: write it as math" in captured.out
    assert (
        f"build stopped: typeset left items for you (listed above). Review them in "
        f"{folder / 'body.typeset.md'} (never body.md), then run build.py {folder} again; nothing was built."
    ) in captured.err
    assert built == []
    assert not (folder / "build").exists()

    assert build.main([str(folder)]) == 0

    assert built != []
    assert "build stopped" not in capsys.readouterr().err


def test_refused_bind_says_the_body_could_not_be_bound(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _folder(tmp_path)
    (folder / "body.md").unlink()

    assert build.main([str(folder)]) == 1

    err = capsys.readouterr().err
    assert "build stopped: typeset could not bind body.md (see the message above); nothing was built." in err
    assert "Finish" not in err


def test_build_stops_once_when_auto_formats_a_copy_that_bind_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    built = _stub_build(monkeypatch)
    body = BODY + "\nVer https://example.org/datos\n\nEl error es e = |x1 - x0| / |x1|.\n"
    folder = _folder(tmp_path, body)
    assert typeset.main(["bind", str(folder)]) == 0
    capsys.readouterr()

    assert build.main([str(folder)]) == 1

    assert "build stopped: typeset left items for you (listed above)." in capsys.readouterr().err
    assert built == []

    assert build.main([str(folder)]) == 0

    assert built != []
