"""Tests for ``tools/timings.py``: informational per-phase timings in ``timings.yml`` (S7).

The tools that run the phases record start, end and duration in the work folder
(never the delivery folder). The record is append-only and informational: a
malformed or unwritable ``timings.yml`` is ignored with a warning and never
changes a tool's exit code or output.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

import approval_marker
import content_check
import doc_status
import draft_pdf
import timings
import typeset
import validate_report
from conftest import _body, _report, _sources_bib
from test_draft_pdf import AA_BODY, _aa_folder

TOOLS = Path(__file__).resolve().parent


@pytest.fixture(autouse=True)
def isolated_drafts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    drafts = tmp_path / "system-tmp"
    monkeypatch.setenv(approval_marker.DRAFT_DIR_ENV, str(drafts))
    return drafts


@pytest.fixture
def compiled(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_compile(config) -> None:
        config.pdf_path.parent.mkdir(parents=True, exist_ok=True)
        config.pdf_path.write_bytes(b"%PDF-1.4\n%%EOF\n")

    monkeypatch.setattr(draft_pdf, "compile_latex", fake_compile)


def _entries(folder: Path) -> list[dict]:
    return yaml.safe_load((folder / timings.TIMINGS_NAME).read_text(encoding="utf-8"))


def _write(folder: Path, rows: list[tuple[str, float]]) -> None:
    entries = [
        {"phase": phase, "tool": "t.py", "start": "2026-11-05T10:00:00+00:00",
         "end": "2026-11-05T10:00:01+00:00", "duration_seconds": seconds}
        for phase, seconds in rows
    ]
    (folder / timings.TIMINGS_NAME).write_text(yaml.safe_dump(entries, sort_keys=False), encoding="utf-8")


# -- recording ---------------------------------------------------------------


def test_timed_writes_start_end_and_duration_in_the_work_folder(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    folder.mkdir()

    with timings.timed(folder, "verify", "content_check.py"):
        pass

    (entry,) = _entries(folder)
    assert entry["phase"] == "verify" and entry["tool"] == "content_check.py"
    assert entry["start"] <= entry["end"]
    assert isinstance(entry["duration_seconds"], float) and entry["duration_seconds"] >= 0


def test_timed_records_a_failing_run_and_keeps_its_exception(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    folder.mkdir()

    with pytest.raises(SystemExit):
        with timings.timed(folder, "generate", "build_report_auto.py"):
            raise SystemExit("boom")

    assert _entries(folder)[0]["outcome"] == "error"


def test_timed_appends_across_runs_keeping_earlier_entries(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    folder.mkdir()
    with timings.timed(folder, "draft", "content_check.py"):
        pass
    first = _entries(folder)[0]

    with timings.timed(folder, "verify", "content_check.py"):
        pass

    entries = _entries(folder)
    assert [entry["phase"] for entry in entries] == ["draft", "verify"]
    assert entries[0] == first


def test_timed_never_creates_a_missing_work_folder(tmp_path: Path) -> None:
    folder = tmp_path / "missing"

    with timings.timed(folder, "draft", "content_check.py"):
        pass

    assert not folder.exists()


def test_malformed_timings_are_ignored_with_a_warning_and_left_untouched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "wf"
    folder.mkdir()
    (folder / timings.TIMINGS_NAME).write_text("{ not: [valid yaml", encoding="utf-8")

    with timings.timed(folder, "draft", "content_check.py"):
        pass

    assert (folder / timings.TIMINGS_NAME).read_text(encoding="utf-8") == "{ not: [valid yaml"
    err = capsys.readouterr().err
    assert "timings" in err and "ignor" in err


def test_unwritable_timings_never_break_the_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "wf"
    (folder / timings.TIMINGS_NAME).mkdir(parents=True)

    with timings.timed(folder, "draft", "content_check.py"):
        pass

    assert "timings" in capsys.readouterr().err


# -- the instrumented tools --------------------------------------------------


def test_draft_pdf_records_its_build_in_the_work_folder_not_the_delivery_folder(
    tmp_path: Path, compiled: None, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _aa_folder(tmp_path)
    delivery = tmp_path / "Documents" / "entrega"

    assert draft_pdf.main([str(folder), "--no-open"]) == 0

    (entry,) = _entries(folder)
    assert entry["phase"] == "approval" and entry["tool"] == "draft_pdf.py"
    assert entry["duration_seconds"] >= 0
    assert not delivery.exists()
    assert not list(approval_marker.draft_preview_dir(folder).glob(timings.TIMINGS_NAME))
    assert "Draft PDF:" in capsys.readouterr().out


def test_draft_pdf_appends_one_entry_per_run(tmp_path: Path, compiled: None) -> None:
    folder = _aa_folder(tmp_path)

    draft_pdf.main([str(folder), "--no-open"])
    draft_pdf.main([str(folder), "--no-open"])

    assert [entry["phase"] for entry in _entries(folder)] == ["approval", "approval"]


def test_draft_pdf_output_and_exit_code_ignore_malformed_timings(
    tmp_path: Path, compiled: None, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _aa_folder(tmp_path)
    draft_pdf.main([str(folder), "--no-open"])
    clean = capsys.readouterr().out
    (folder / timings.TIMINGS_NAME).write_text("- [oops", encoding="utf-8")

    code = draft_pdf.main([str(folder), "--no-open"])

    captured = capsys.readouterr()
    assert code == 0 and captured.out == clean
    assert "timings" in captured.err


def test_content_check_body_check_records_the_draft_phase(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _body(folder, AA_BODY)

    content_check.main([str(folder), "--body-check"])

    assert [(e["phase"], e["tool"]) for e in _entries(folder)] == [("draft", "content_check.py")]


def test_content_check_verification_records_the_verify_phase(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _body(folder, AA_BODY)

    content_check.main([str(folder), "--verification", str(folder / "verification.yml")])

    assert _entries(folder)[0]["phase"] == "verify"


def test_content_check_verify_brief_is_not_timed(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _body(folder, AA_BODY)

    content_check.main([str(folder), "--verify-brief"])

    assert not (folder / timings.TIMINGS_NAME).exists()


def test_typeset_check_records_the_typeset_phase(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _body(folder, AA_BODY)

    typeset.main(["check", str(folder)])

    assert _entries(folder)[0]["phase"] == "typeset"


def test_validate_report_records_the_validate_phase(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    folder.mkdir()
    config = SimpleNamespace(quality_report_path=folder / "q.md")
    result = SimpleNamespace(errors=[], warnings=[])

    with (
        patch.object(sys, "argv", ["validate_report.py", str(folder)]),
        patch("validate_report.load_report_config", return_value=config),
        patch("validate_report.validate", return_value=result),
    ):
        validate_report.main()

    assert [(e["phase"], e["tool"]) for e in _entries(folder)] == [("validate", "validate_report.py")]


def _run_build(folder: Path, flags: list[str], tmp_path: Path) -> None:
    import build_report_auto

    config = SimpleNamespace(
        backend="latex", folder=tmp_path / "elsewhere", raw={}, output_format="docx",
        quality_report_path=folder / "q.md", pdf_path=folder / "r.pdf",
        publication_category="x", document_slug="y", type="essay",
    )
    result = SimpleNamespace(errors=[], warnings=[])
    with (
        patch.object(sys, "argv", ["build_report_auto.py", str(folder), *flags]),
        patch("build_report_auto.load_report_config", return_value=config),
        patch("build_report_auto.build_backend"),
        patch("build_report_auto.validate", return_value=result),
    ):
        build_report_auto.main()


def test_build_report_auto_records_generate_and_validate_only_records_validate(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    folder.mkdir()

    _run_build(folder, ["--no-approval-check"], tmp_path)
    _run_build(folder, ["--validate-only"], tmp_path)

    assert [(e["phase"], e["tool"]) for e in _entries(folder)] == [
        ("generate", "build_report_auto.py"),
        ("validate", "build_report_auto.py"),
    ]


# -- reading -----------------------------------------------------------------


def test_summary_lists_phases_slowest_first(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "wf"
    folder.mkdir()
    _write(folder, [("verify", 40.0), ("approval", 5.5), ("generate", 90.25), ("verify", 20.0)])

    assert timings.main([str(folder)]) == 0

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    phases = [line.split()[0] for line in lines if line.split()[0] in {"verify", "approval", "generate"}]
    assert phases == ["generate", "verify", "approval"]
    verify = next(line for line in lines if line.startswith("verify"))
    assert "60.0" in verify and "2" in verify.split()


def test_summary_with_no_timings_says_so_and_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "wf"
    folder.mkdir()

    assert timings.main([str(folder)]) == 0
    assert "no timings" in capsys.readouterr().out.lower()


def test_summary_of_malformed_timings_warns_and_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "wf"
    folder.mkdir()
    (folder / timings.TIMINGS_NAME).write_text("- [oops", encoding="utf-8")

    assert timings.main([str(folder)]) == 0
    captured = capsys.readouterr()
    assert "no timings" in captured.out.lower() and "ignor" in captured.err


def test_summary_skips_entries_without_a_numeric_duration(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "wf"
    folder.mkdir()
    (folder / timings.TIMINGS_NAME).write_text(
        "- phase: verify\n  duration_seconds: 3.0\n- phase: draft\n  duration_seconds: soon\n- just text\n",
        encoding="utf-8",
    )

    assert timings.main([str(folder)]) == 0
    out = capsys.readouterr().out
    assert "verify" in out and "draft" not in out


def test_summary_rejects_a_missing_folder(tmp_path: Path) -> None:
    assert timings.main([str(tmp_path / "nope")]) == 2


def test_timings_cli_runs_as_a_script(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    folder.mkdir()
    _write(folder, [("verify", 1.0)])

    done = subprocess.run(
        [sys.executable, str(TOOLS / "timings.py"), str(folder)], capture_output=True, text=True, check=False
    )

    assert done.returncode == 0 and "verify" in done.stdout


# -- doc_status is unchanged by timings --------------------------------------


def test_timings_file_does_not_change_the_doc_status_route(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    before = doc_status.render_machine(doc_status.derive(folder))
    _write(folder, [("verify", 1.0)])

    assert doc_status.render_machine(doc_status.derive(folder)) == before


def test_verify_guidance_says_it_runs_in_parallel_with_the_draft_build() -> None:
    template = doc_status._GUIDANCE["verify"]
    assert "parallel" in template and "{draft_command}" in template
    assert "parallel" in doc_status._GUIDANCE["approval"]
