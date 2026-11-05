"""Static contract: the rubric is present at every point and the final table is graded by a tool."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "skills" / "academic-report-flow"
REFS = SKILL_ROOT / "references"


def flat(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_plan_and_draft_run_the_rubric_trace() -> None:
    content = flat(REFS / "content.md")
    assert "rubric_trace.py" in content
    assert "--section" in content


def test_approval_packet_shows_weight_and_trace() -> None:
    approval = flat(REFS / "approval.md")
    assert "weight" in approval and "trace" in approval


def test_validate_reruns_the_rubric_checks_on_the_typeset_body_and_pdf_text() -> None:
    production = flat(REFS / "production.md")
    assert "body.typeset.md" in production and "PDF text" in production
    assert "rubric_grade.py" in production


def test_review_presents_the_grade_table_with_the_pdf_and_only_the_tool_scores() -> None:
    delivery = flat(REFS / "delivery.md")
    assert "rubric-grade.md" in delivery and "rubric_grade.py" in delivery
    assert "mechanical estimate" in delivery
    assert "never the delivery folder" in delivery
    assert "never blocks" in delivery  # informational: the flow has no score gate
    production = flat(REFS / "production.md")
    assert "never scores" in production


def test_skill_md_names_the_grade_table_in_the_contract_and_stays_concise() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "rubric-grade.md" in skill
    assert len(skill.split()) < 1100
