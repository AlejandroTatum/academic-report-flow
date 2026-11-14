"""warn-only-gates S2: ``VALIDATION FAILED`` from validate_report.py warns, never blocks.

The validation findings are written to the quality report and printed on
stderr as ``warning: VALIDATION FAILED: ...``; the CLI exits 0. A missing or
invalid report.yml (nothing to validate) still fails.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import validate_report


def _run(folder: Path, errors: list[str]) -> None:
    report = folder / "backups" / "quality_report.md"
    config = SimpleNamespace(quality_report_path=report)

    def fake_validate(_config: object) -> SimpleNamespace:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("# quality\n", encoding="utf-8")
        return SimpleNamespace(errors=errors, warnings=[])

    with (
        patch.object(sys, "argv", ["validate_report.py", str(folder)]),
        patch("validate_report.load_report_config", return_value=config),
        patch("validate_report.validate", side_effect=fake_validate),
    ):
        validate_report.main()


def test_validation_failure_warns_exits_zero_and_keeps_the_quality_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "wf"
    folder.mkdir()

    _run(folder, ["La tabla 1 no cabe"])  # no SystemExit: exit 0

    report = folder / "backups" / "quality_report.md"
    captured = capsys.readouterr()
    assert captured.err == f"warning: VALIDATION FAILED:\n- La tabla 1 no cabe\n\nReporte: {report}\n"
    assert "VALIDATION PASSED" not in captured.out
    assert report.is_file()


def test_missing_report_yml_still_fails(tmp_path: Path) -> None:
    with patch.object(sys, "argv", ["validate_report.py", str(tmp_path / "missing")]):
        with pytest.raises(SystemExit) as exc:
            validate_report.main()
    assert exc.value.code not in (0, None)
