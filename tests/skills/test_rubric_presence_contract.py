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


def test_optional_packet_shows_the_rubric_trace() -> None:
    approval = flat(REFS / "approval.md")
    assert "rubric trace" in approval


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


def test_plan_maps_every_guide_inventory_item_or_waives_it_with_a_reason() -> None:
    content = flat(REFS / "content.md")
    for token in ("--inventory", "not_applicable:", "covers:", "guide_inventory_unmapped"):
        assert token in content, token
    data = flat(REFS / "data.md")
    assert "--inventory" in data and "heuristic" in data


def test_verification_has_a_partial_state_that_never_scores() -> None:
    content = flat(REFS / "content.md")
    assert "found|partial|missing" in content and "gap" in content
    assert "0.5" in flat(REFS / "delivery.md")


def test_approval_gate_blocks_on_unmapped_inventory_not_on_a_score() -> None:
    approval = flat(REFS / "approval.md")
    assert "guide_inventory_unmapped" in approval
    assert "never a score" in approval


def test_plan_keeps_guide_criteria_apart_from_the_teacher_s_grading_rubric() -> None:
    content = flat(REFS / "content.md")
    assert "`origin: guide`" in content and "`origin: teacher`" in content
    assert "`levels:` copied verbatim" in content
    assert "`teacher_rubric: none`" in content
    assert "warning: guide-only plan, no teacher rubric" in content
    assert "it never blocks" in content
    data = flat(REFS / "data.md")
    assert "`teacher rubric: not received`" in data and "only warns" in data


def test_course_memory_feeds_the_plan_and_records_the_grade() -> None:
    content = flat(REFS / "content.md")
    assert "tools/course_memory.py" in content
    assert "`origin: teacher` block" in content and "relay every `warning:` line" in content
    data = flat(REFS / "data.md")
    assert "academic-sources/<course-slug>/rubrics/" in data and "academic.course-rubric/v1" in data
    assert "`ai_declaration: include|omit`" in data
    delivery = flat(REFS / "delivery.md")
    assert "--add-delivery" in delivery and "feedback.yml" in delivery
    for text in (content, data, delivery):
        assert "never blocks" in text
