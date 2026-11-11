"""Static contract: the skill describes the v1 flow, the editorial pass and table/figure rules.

T1 removed the draft approval from generation (typeset/build) and made rubric
content checks findings for v1 while publication keeps its gates. These tests
read the skill and portal text as data so the instructions cannot drift back to
the old approval gate, and they pin the editorial (S3) and visual (S4) rules.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "skills" / "academic-report-flow"
REFS = SKILL_ROOT / "references"
PORTAL = ROOT / "docs" / "portal"


def _flat(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8")).lower()


def _skill_texts() -> dict[str, str]:
    files = [SKILL_ROOT / "SKILL.md", *sorted(REFS.glob("*.md"))]
    return {path.name: _flat(path) for path in files}


def _draft_section() -> str:
    return _flat(REFS / "content.md").split("## draft", 1)[1]


# --- S1/S2: v1 flow wording -------------------------------------------------


def test_no_skill_text_keeps_the_draft_approval_gate() -> None:
    stale = (
        "draft approval plus format",
        "draft approval + format",
        "generation happens only after this approval",
        "generation starts only after the one human approval",
        "so approval is never offered early",
        "never build the final artifact before approval",
        "never build before approval is done",
        "approval_marker.py approve <folder> --express",
        "approval gate stays closed",
        "keeps approval blocked",
    )
    for name, text in _skill_texts().items():
        for phrase in stale:
            assert phrase not in text, f"{name} still states the old gate: {phrase!r}"


def test_skill_states_v1_without_draft_approval_and_versions_after_review() -> None:
    skill = _flat(SKILL_ROOT / "SKILL.md")
    for phrase in (
        "no draft approval",
        "v1",
        "v2",
        "formatted version",
        "explicit instruction",
        "generation is not a compliance claim",
    ):
        assert phrase in skill, phrase


def test_approval_reference_is_a_legacy_phase_that_never_waits() -> None:
    approval = _flat(REFS / "approval.md")
    assert "never waits" in approval
    assert "legacy" in approval
    assert "never record a new `approval.yml`" in approval
    assert "--express` refuses" in approval


def test_format_phase_stays_after_verify_and_before_typeset() -> None:
    approval = _flat(REFS / "approval.md")
    assert "before v1" in approval
    assert "after verify" in approval and "before `typeset`" in approval


def test_body_check_rubric_failures_are_v1_findings_and_publication_conditions() -> None:
    draft = _draft_section()
    assert "every rubric check green" not in draft
    for phrase in (
        "`rubric_checks`",
        "`eligible_sources_cited`",
        "never stop v1",
        "publication condition",
    ):
        assert phrase in draft, phrase


def test_verify_findings_are_reported_without_blocking_v1() -> None:
    production = _flat(REFS / "production.md")
    assert "a recorded `fail` blocks the route" not in production
    for phrase in ("never a compliance claim", "rubric findings", "technical"):
        assert phrase in production, phrase


def test_generation_prints_findings_and_validation_still_fails_on_them() -> None:
    production = _flat(REFS / "production.md")
    assert "rubric findings" in production
    assert "validate_report.py` still fails" in production


def test_publication_keeps_its_guards_and_waits_for_an_explicit_instruction() -> None:
    delivery = _flat(REFS / "delivery.md")
    for phrase in (
        "explicit instruction",
        "build/generation.yml",
        "unresolved rubric failure",
        "accepted gap",
        "unresolved citation",
        "final-review.yml",
    ):
        assert phrase in delivery, phrase


def test_express_flow_no_longer_records_an_automatic_approval() -> None:
    data = _flat(REFS / "data.md")
    assert "--express` refuses" in data
    assert "re-runs `--express`" not in data


def test_portal_describes_v1_without_draft_approval() -> None:
    decisions = _flat(PORTAL / "decisiones-usuario.qmd")
    assert "aprobación del borrador + formato" not in decisions
    assert "sin aprobación del borrador" in decisions
    assert "v1" in decisions and "v2" in decisions


# --- S3: editorial pass ------------------------------------------------------


def test_editorial_pass_runs_before_v1_and_is_not_a_gate() -> None:
    draft = _draft_section()
    assert "editorial pass" in draft
    assert "before v1" in draft
    assert "not an approval gate" in draft


def test_editorial_prose_is_direct_and_explains_the_actual_work() -> None:
    draft = _draft_section()
    for phrase in (
        "direct academic prose",
        "technical precision",
        "explains the actual work",
        "rather than narrating rubric compliance",
    ):
        assert phrase in draft, phrase


def test_editorial_pass_requires_concrete_referents() -> None:
    draft = _draft_section()
    assert "concrete referents" in draft
    assert "name the exact document, component or result" in draft


def test_each_paragraph_adds_new_information() -> None:
    draft = _draft_section()
    assert "each paragraph adds new information" in draft
    assert "necessary explanation" in draft


def test_explicit_assignment_word_limits_are_kept_without_invented_quotas() -> None:
    draft = _draft_section()
    assert "explicit word limits of the assignment" in draft
    assert "including a minimum" in draft
    assert "never invent a word quota" in draft


# --- S4: tables and figures --------------------------------------------------


def _visual() -> str:
    return _flat(REFS / "visual-directions.md")


def test_visuals_show_the_projects_actual_data_not_generic_templates() -> None:
    visual = _visual()
    assert "## tables and figures" in visual
    assert "actual data, components or relationships" in visual
    assert "never a generic" in visual


def test_visuals_have_informative_titles_units_and_source() -> None:
    visual = _visual()
    assert "informative title" in visual
    assert "units" in visual and "source" in visual and "when applicable" in visual


def test_visuals_never_invent_measurements_or_force_a_count() -> None:
    visual = _visual()
    assert "never invent measurements" in visual
    assert "no quota" in visual


def test_prose_interprets_visuals_instead_of_repeating_them() -> None:
    visual = _visual()
    assert "prose interprets" in visual
    assert "never repeats the cells" in visual


def test_draft_points_to_the_table_and_figure_rules() -> None:
    assert "visual-directions.md" in _draft_section()
