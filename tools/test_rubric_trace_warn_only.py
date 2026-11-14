"""warn-only-gates S2: uncovered rubric criteria warn; rubric_trace still prints the trace and exits 0.

Usage and missing-input errors keep exiting 2.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import rubric_trace
from test_rubric_trace import planned_folder


def test_uncovered_criteria_warn_and_exit_0(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = planned_folder(tmp_path, body=None)
    assert rubric_trace.main([str(folder)]) == 0
    captured = capsys.readouterr()
    assert "uncovered: 3/3" in captured.out and "Uncovered:" in captured.out
    assert captured.err.splitlines() == [
        "warning: rubric trace: 3 uncovered criteria (objetivo, metodologia, conclusiones); "
        "see Uncovered above. The flow continues."
    ]


def test_covered_rubric_prints_no_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = planned_folder(tmp_path)
    assert rubric_trace.main([str(folder)]) == 0
    assert capsys.readouterr().err == ""


def test_missing_rubric_still_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "empty"
    folder.mkdir()
    assert rubric_trace.main([str(folder)]) == 2
    assert capsys.readouterr().err.startswith("rubric trace input error:")


def test_unknown_section_still_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = planned_folder(tmp_path)
    assert rubric_trace.main([str(folder), "--section", "Nope"]) == 2
    assert "no criterion maps to section 'Nope'" in capsys.readouterr().err
