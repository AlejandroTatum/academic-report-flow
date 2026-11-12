"""Static contract: the plan aims at the teacher's top level and lists guide-vs-rubric conflicts (S6, S2)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTENT = ROOT / "skills" / "academic-report-flow" / "references" / "content.md"


def _plan_section() -> str:
    text = CONTENT.read_text(encoding="utf-8")
    plan = text.split("## Plan", 1)[1].split("\n## ", 1)[0]
    return re.sub(r"\s+", " ", plan)


def test_plan_turns_each_top_level_descriptor_into_evidence() -> None:
    plan = _plan_section()
    assert "top-level descriptor" in plan
    assert "even when the guide never asks for it" in plan
    assert "`deliverables:`" in plan and "`covers:`" in plan


def test_plan_runs_rubric_conflicts_before_drafting_and_never_blocks() -> None:
    plan = _plan_section()
    assert "tools/rubric_conflicts.py" in plan
    assert "before drafting" in plan
    assert "guide-vs-rubric conflict list" in plan
    assert "the draft continues either way" in plan
