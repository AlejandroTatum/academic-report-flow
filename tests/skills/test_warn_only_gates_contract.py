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
