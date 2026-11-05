"""Review guidance presents the rubric grade table with the PDF (skill-rubric-improvements T3, S2)."""
from __future__ import annotations

import shlex
import sys
from pathlib import Path

import doc_status
from conftest import _config, _report, _rubric


def test_review_guidance_runs_and_presents_the_grade_table_when_a_rubric_exists(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _rubric(folder)
    guidance = doc_status._guidance("review", folder, _config(folder))
    command = shlex.join([sys.executable, str(doc_status.ROOT / "tools" / "rubric_grade.py"), str(folder)])
    assert command in guidance
    assert "rubric-grade.md" in guidance
    assert "mechanical estimate" in guidance
    assert "pdf_viewer.py" in guidance  # the existing PDF handoff stays


def test_review_guidance_is_unchanged_without_a_rubric(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    guidance = doc_status._guidance("review", folder, _config(folder))
    assert "rubric_grade" not in guidance and "rubric-grade" not in guidance
