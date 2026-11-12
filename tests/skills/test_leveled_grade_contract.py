"""Static contract: guide coverage is not a grade; an independent strict grader levels the teacher rubric (T4, S7, S8, S2)."""
from __future__ import annotations

import re
from pathlib import Path

REFS = Path(__file__).resolve().parents[2] / "skills" / "academic-report-flow" / "references"


def flat(name: str) -> str:
    return re.sub(r"\s+", " ", (REFS / name).read_text(encoding="utf-8"))


def test_production_makes_the_strict_grader_a_fixed_step_with_a_narrow_view() -> None:
    production = flat("production.md")
    for phrase in ("independent strict grader", "fixed step", "only the teacher criteria with their levels and the body",
                   "no benefit of the doubt", "quotes the matched descriptor", "leveled-grade.yml",
                   "academic.leveled-grade/v1", "body_sha256", "missing for the top level"):
        assert phrase in production, phrase


def test_delivery_presents_coverage_and_the_leveled_grade_apart_and_never_blocks() -> None:
    delivery = flat("delivery.md")
    for phrase in ("guide coverage", "leveled grade", "/10", "never calls coverage a grade", "warning:", "note:",
                   "--predicted", "mean absolute difference", "orientative"):
        assert phrase in delivery, phrase
    assert "never blocks" in delivery
