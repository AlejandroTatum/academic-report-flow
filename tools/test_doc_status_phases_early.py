"""Early-phase tests for ``tools/doc_status.py`` (slice 2a).

Slice 2a ships the phase vocabulary, the value dataclasses and the
intake/research/plan derivations; ``derive``/renderers/CLI land in slices
2b/2c. These tests therefore call the three early handlers directly with a
throwaway ``ReportConfig`` and assert their raw ``done|pending|blocked`` token,
detail and blocked reason -- nothing here depends on a route projection that does
not exist yet. Artifact shapes come from ``tools/conftest.py``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import doc_status
from conftest import (
    _body,
    _choose_format,
    _config,
    _evidence_matrix,
    _evidence_yml,
    _report,
    _rubric,
    _skip_research,
    _sources_bib,
)


def _early_phases(folder: Path) -> list[doc_status.PhaseState]:
    """Return the intake/research/plan handler results for ``folder``."""
    config = _config(folder)
    return [
        doc_status._phase_intake(folder, config, None),
        doc_status._phase_research(folder, config, None),
        doc_status._phase_plan(folder, config, None),
    ]


# ---------------------------------------------------------------------------
# 2.1 intake
# ---------------------------------------------------------------------------


def test_intake_missing_report_yml_is_pending_not_blocked(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    phase = doc_status._phase_intake(folder, _config(folder), None)

    assert phase.name == "intake"
    assert phase.state == doc_status.PENDING
    assert phase.blocked_reason == ""
    assert phase.detail == "report.yml missing"


def test_missing_report_yml_leaves_intake_as_route_focus_and_later_phases_pending(
    tmp_path: Path,
) -> None:
    """Missing ``report.yml`` means intake is the route focus and later phases wait.

    Slice 2a has no projection yet, so this asserts the raw states that slice 2c
    turns into ``current`` for the first phase and ``pending`` for the rest.
    """
    states = _early_phases(tmp_path / "wf")

    assert [phase.name for phase in states] == list(doc_status.PHASES[:3])
    assert states[0].state == doc_status.PENDING
    assert all(phase.state == doc_status.PENDING for phase in states[1:])
    assert all(phase.blocked_reason == "" for phase in states)


def test_intake_unknown_route_is_blocked(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder, route="galactic")

    phase = doc_status._phase_intake(folder, _config(folder), None)

    assert phase.state == doc_status.BLOCKED
    assert phase.blocked_reason == "unknown_route"
    assert "galactic" in phase.detail


def test_intake_missing_title_is_pending(tmp_path: Path) -> None:
    """new-report-flow T5: intake needs identity, not the whole route metadata."""
    folder = tmp_path / "wf"
    _report(folder, title=None)

    phase = doc_status._phase_intake(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert phase.blocked_reason == ""
    assert "title" in phase.detail


def test_intake_missing_student_is_pending(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder, student=None)

    phase = doc_status._phase_intake(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert "student" in phase.detail


def test_intake_placeholder_title_is_pending(tmp_path: Path) -> None:
    """A bracket template in place of a real title is not an identified report."""
    folder = tmp_path / "wf"
    _report(folder, title="'[Nombre del estudiante]'")

    phase = doc_status._phase_intake(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert "placeholder" in phase.detail
    assert "title" in phase.detail


def test_intake_placeholder_student_is_pending(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder, student="'XXX'")

    phase = doc_status._phase_intake(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert "placeholder" in phase.detail


def test_intake_subject_and_teacher_are_no_longer_required(tmp_path: Path) -> None:
    """new-report-flow T5: subject/teacher belong to the format phase now."""
    folder = tmp_path / "wf"
    _report(folder, subject=None, teacher=None)

    phase = doc_status._phase_intake(folder, _config(folder), None)

    assert phase.state == doc_status.DONE


def test_intake_unknown_format_is_blocked(tmp_path: Path) -> None:
    """A declared ``format:`` must be one the format table recognises."""
    folder = tmp_path / "wf"
    _report(folder)
    _choose_format(folder, "apa")

    phase = doc_status._phase_intake(folder, _config(folder), None)

    assert phase.state == doc_status.BLOCKED
    assert phase.blocked_reason == "unknown_format"
    assert "apa" in phase.detail


def test_intake_chosen_format_needs_no_format_metadata_yet(tmp_path: Path) -> None:
    """TRIANGULATE: APE identification fields are the format phase's business."""
    folder = tmp_path / "wf"
    _report(folder)
    _choose_format(folder, "ape", cycle=None)

    phase = doc_status._phase_intake(folder, _config(folder), None)

    assert phase.state == doc_status.DONE


def test_intake_complete_is_done(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)

    phase = doc_status._phase_intake(folder, _config(folder), None)

    assert phase.state == doc_status.DONE
    assert "route=academic" in phase.detail


def test_intake_route_alias_uses_the_mapped_route_and_its_own_metadata(tmp_path: Path) -> None:
    """TRIANGULATE: route ``b`` maps to project; intake only needs title/student."""
    folder = tmp_path / "wf"
    _report(folder, route="b", subject=None, teacher=None)

    phase = doc_status._phase_intake(folder, _config(folder), None)

    assert phase.state == doc_status.DONE
    assert "route=project" in phase.detail


# ---------------------------------------------------------------------------
# 2.3 research
# ---------------------------------------------------------------------------


def test_research_five_eligible_entries_is_done(tmp_path: Path) -> None:
    """new-report-flow T2: research is done only with >= 5 eligible sources."""
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)

    phase = doc_status._phase_research(folder, _config(folder), None)

    assert phase.state == doc_status.DONE
    assert "5/5" in phase.detail


def test_research_four_eligible_entries_is_pending_with_count(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder, count=4)

    phase = doc_status._phase_research(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert phase.blocked_reason == ""
    assert phase.detail == "sources.bib has 4/5 book or paper sources"


def test_research_missing_sources_bib_reports_zero_of_five(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)

    phase = doc_status._phase_research(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert phase.detail == "sources.bib has 0/5 book or paper sources"


def test_research_evidence_matrix_alone_no_longer_satisfies(tmp_path: Path) -> None:
    """A non-empty matrix is still evidence work, but never the phase artifact."""
    folder = tmp_path / "wf"
    _report(folder)
    _evidence_matrix(folder)

    phase = doc_status._phase_research(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert "sources.bib" in phase.detail


def test_research_skipped_in_report_yml_is_no_longer_accepted(tmp_path: Path) -> None:
    """new-report-flow T2: the recorded skip decision is ignored, and named."""
    folder = tmp_path / "wf"
    _report(folder)
    _skip_research(folder)

    phase = doc_status._phase_research(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert "no longer accepted" in phase.detail


def test_research_skip_value_case_variants_stay_pending(tmp_path: Path) -> None:
    """TRIANGULATE: ``research: '  SKIPPED  '`` is ignored exactly like the rest."""
    folder = tmp_path / "wf"
    _report(folder)
    _skip_research(folder, value="'  SKIPPED  '")

    phase = doc_status._phase_research(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING


def test_research_valid_evidence_yml_still_validates_on_top_of_sources(
    tmp_path: Path,
) -> None:
    """#11: once evidence.yml exists it must validate, even with five sources."""
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _evidence_yml(folder)

    phase = doc_status._phase_research(folder, _config(folder), None)

    assert phase.state == doc_status.DONE
    assert "research/evidence.yml validated" in phase.detail


def test_research_invalid_evidence_yml_keeps_the_phase_pending(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _evidence_yml(folder, text="claims: []\n")

    phase = doc_status._phase_research(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert "evidence.yml invalid" in phase.detail


# ---------------------------------------------------------------------------
# 2.5 plan
# ---------------------------------------------------------------------------


def test_plan_valid_rubric_is_done(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _rubric(folder)

    phase = doc_status._phase_plan(folder, _config(folder), None)

    assert phase.name == "plan"
    assert phase.state == doc_status.DONE
    assert phase.detail.startswith("rubric.yml valid (2 criteria, 0 with checks); ")


def test_plan_missing_rubric_is_pending(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)

    phase = doc_status._phase_plan(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert phase.blocked_reason == ""
    assert phase.detail == "rubric.yml missing"


def test_plan_schema_invalid_rubric_is_blocked(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _rubric(folder, criteria=())

    phase = doc_status._phase_plan(folder, _config(folder), None)

    assert phase.state == doc_status.BLOCKED
    assert phase.blocked_reason == "rubric_malformed"


def test_plan_unparsable_rubric_is_blocked(tmp_path: Path) -> None:
    """TRIANGULATE: a bad plan is named, never silently treated as absent."""
    folder = tmp_path / "wf"
    _report(folder)
    (folder / "rubric.yml").write_text("schema: [unclosed\n", encoding="utf-8")

    phase = doc_status._phase_plan(folder, _config(folder), None)

    assert phase.state == doc_status.BLOCKED
    assert phase.blocked_reason == "rubric_malformed"


def test_plan_derivation_never_repairs_the_rubric(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    rubric = _rubric(folder, criteria=())
    before = rubric.read_bytes()

    doc_status._phase_plan(folder, _config(folder), None)

    assert rubric.read_bytes() == before


# ---------------------------------------------------------------------------
# 2.6 draft
# ---------------------------------------------------------------------------


def test_draft_non_empty_is_done(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    _body(folder)

    phase = doc_status._phase_draft(folder, _config(folder), None)

    assert phase.state == doc_status.DONE


def test_draft_whitespace_only_is_pending(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _body(folder, "   \n\t\n")

    phase = doc_status._phase_draft(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert phase.blocked_reason == ""
    assert phase.detail == "body.md empty"


def test_draft_missing_is_pending(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)

    phase = doc_status._phase_draft(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert phase.detail == "body.md missing"


def test_draft_unreadable_is_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _body(folder)
    original = Path.read_text

    def denied(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "body.md":
            raise PermissionError("denied")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", denied)
    phase = doc_status._phase_draft(folder, _config(folder), None)

    assert phase.state == doc_status.BLOCKED
    assert phase.blocked_reason == "draft_unreadable"
    assert phase.state != doc_status.DONE
