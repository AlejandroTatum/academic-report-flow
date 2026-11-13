"""warn-only-gates S3: the skill docs describe quality checks as warnings, never blocks."""
from __future__ import annotations

from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "academic-report-flow"


def _read(name: str) -> str:
    return " ".join((SKILL_DIR / name).read_text(encoding="utf-8").split())


def test_skill_md_says_quality_checks_warn_and_never_block() -> None:
    skill = _read("SKILL.md")
    assert "obey their blocks" not in skill
    assert "earliest failed gate" not in skill
    assert "relay their non-blocking warnings" in skill
    assert "Stop only on a hard failure" in skill
    assert "it refuses unresolved rubric failures" not in skill


def test_content_md_names_the_warning_codes_and_exit_zero() -> None:
    content = _read("references/content.md")
    assert "it blocks on a malformed rubric" not in content
    assert "exits 1 on any FAIL" not in content
    assert "keeps `next: draft`" not in content
    for literal in (
        "`warning: rubric_malformed`",
        "`warning: guide_inventory_unmapped`",
        "`warning: body_check_failed: <checks>`",
        "the publisher warns while any stays unmapped",
        "`warning: body_check_failed: body check fails: ...`",
    ):
        assert literal in content, literal


def test_delivery_md_warns_on_quality_gaps_and_keeps_the_hard_refusals() -> None:
    delivery = _read("references/delivery.md")
    assert "These checks warn, never block" in delivery
    assert "PDF ENTREGADO CON ADVERTENCIAS" in delivery
    assert "Delivery refuses (exit 1, nothing created) only when there is nothing to deliver or nothing readable" in delivery
    assert "the user's explicit approve, a human decision" in delivery
    assert "refuses an absent, stale or malformed marker" not in delivery
    assert "neither `approval.yml` nor `build/generation.yml`" in delivery
    assert "`el PDF se entrega igual`" in delivery


def test_production_md_never_says_the_publisher_refuses_a_quality_gap() -> None:
    production = _read("references/production.md")
    for stale in ("refused by the publisher", "the publisher no longer refuses", "the publisher needs it current",
                  "after the draft passes the body check", "still fails the build"):
        assert stale not in production, stale


def test_t6_quality_checks_read_as_warnings_and_approval_stays_a_block() -> None:
    production = _read("references/production.md")
    assert "a visible blocking defect fails the artifact" not in production
    assert "Blocking defects:" not in production
    assert "Defects to report and fix (warnings; they never block delivery):" in production
    content = _read("references/content.md")
    assert "must be covered before the next section" not in content
    assert "uncovered (exit 1)" not in content
    assert "`warning: rubric trace: <n> uncovered criteria (<ids>)`" in content
    assert "`warning: verify_sources: <n> of <m> entries failed`" in content
    delivery = _read("references/delivery.md")
    assert "a present but stale or malformed `approval.yml` always refuses, whatever `build/generation.yml` holds" in delivery
    assert "whose `build/generation.yml` is not current for the PDF" in delivery
    visual = " ".join((SKILL_DIR.parent / "academic-visual-builder" / "SKILL.md").read_text(encoding="utf-8").split())
    assert "Stop on missing metadata" not in visual
    assert "stop on failure" not in visual
    assert "`warning: VALIDATION FAILED`" in visual
    assert "`warning: print size check: FAIL ...`" in visual
