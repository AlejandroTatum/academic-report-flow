"""The approval packet shows weight and trace per rubric criterion (skill-rubric-improvements T3, S1)."""
from __future__ import annotations

from pathlib import Path

import pytest

import approval_packet
from approval_marker import DRAFT_DIR_ENV
from test_rubric_trace import CRITERIA, planned_folder, verified_folder


@pytest.fixture(autouse=True)
def isolated_drafts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DRAFT_DIR_ENV, str(tmp_path / "system-tmp"))


def test_packet_lists_weight_sections_and_trace_per_criterion(tmp_path: Path) -> None:
    text = approval_packet.render(verified_folder(tmp_path))
    block = text.split("## Rubric trace", 1)[1]
    assert "| Rubric criterion | Weight | Sections | Checks | Requirements | Status |" in block
    objetivo = next(line for line in block.splitlines() if line.startswith("| objetivo "))
    assert "| 40 |" in objetivo and "Objetivos" in objetivo and "cumple" in objetivo
    meto = next(line for line in block.splitlines() if line.startswith("| metodologia "))
    assert "| 30 |" in meto and "1/2" in meto and "falta" in meto
    assert "uncovered: 2/3" in block


def test_the_existing_verify_table_is_unchanged(tmp_path: Path) -> None:
    text = approval_packet.render(verified_folder(tmp_path))
    assert ("| Criterion | Status | Found |\n|---|---|---|\n| objetivo | cumple | 1/1 |\n"
            "| metodologia | falta | 1/2 |\n| conclusiones | falta | 2/3 |") in text
    assert text.index("## Verify") < text.index("## Rubric trace")


def test_packet_without_a_verification_still_traces_the_rubric(tmp_path: Path) -> None:
    text = approval_packet.render(planned_folder(tmp_path))
    assert "## Verify: absent" in text
    assert "| objetivo " in text.split("## Rubric trace", 1)[1]
    assert "uncovered: 0/3" in text


def test_packet_without_a_valid_rubric_is_unchanged(tmp_path: Path) -> None:
    folder = planned_folder(tmp_path)
    (folder / "rubric.yml").unlink()
    assert "Rubric trace" not in approval_packet.render(folder)


def test_packet_marks_equal_weights(tmp_path: Path) -> None:
    unweighted = tuple({k: v for k, v in c.items() if k != "weight"} for c in CRITERIA)
    text = approval_packet.render(planned_folder(tmp_path, unweighted))
    assert "equal weights" in text.split("## Rubric trace", 1)[1]
