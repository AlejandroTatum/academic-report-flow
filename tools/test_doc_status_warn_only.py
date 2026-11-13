"""Quality checks warn, never block (warn-only-gates S2).

A malformed rubric, a technical or malformed content check, a recorded
validation fail and a malformed final-review marker never make a phase
``blocked``: the code and message stay in the phase detail prefixed
``warning:`` and the route continues. Hard failures (an unreadable draft,
unrecognised config values) still block.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import content_check
import doc_status
from conftest import _body, _config, _final_review, _pdf, _report, _rubric, _sources_bib, _validation


def _warned(phase: doc_status.PhaseState, code: str, reason: str = "") -> None:
    assert phase.state != doc_status.BLOCKED
    assert phase.blocked_reason == reason
    assert phase.detail.startswith(f"warning: {code}: "), phase.detail


@pytest.mark.parametrize("text", ["schema: [unclosed\n", None])
def test_malformed_rubric_is_a_warning_and_the_plan_continues(tmp_path: Path, text: str | None) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    if text is None:
        _rubric(folder, criteria=())
    else:
        (folder / "rubric.yml").write_text(text, encoding="utf-8")

    phase = doc_status._phase_plan(folder, _config(folder), None)

    _warned(phase, "rubric_malformed")
    assert phase.state == doc_status.DONE
    assert phase.detail == "warning: rubric_malformed: rubric.yml malformed (run rubric_plan.py for the errors)"


def _failed_marker(folder: Path, mechanical: list[dict], monkeypatch: pytest.MonkeyPatch) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / content_check.CONTENT_CHECK_NAME).write_text(
        yaml.safe_dump({"mechanical": mechanical, "findings": [], "requirements": []}), encoding="utf-8"
    )
    monkeypatch.setattr(content_check, "content_check_state", lambda _folder: "fail")


def test_technical_content_check_failure_is_a_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "wf"
    _failed_marker(folder, [{"check": "citations_resolve", "ok": False, "detail": "[@nope] unresolved"}], monkeypatch)

    phase = doc_status._phase_verify(folder, None, None)

    _warned(phase, "content_check_failed")
    assert phase.state == doc_status.DONE
    assert phase.detail == (
        "warning: content_check_failed: content check technical failure: citations_resolve: [@nope] unresolved"
    )


def test_malformed_content_check_is_a_warning(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    _body(folder)
    (folder / "content-check.yml").write_text("result: [unclosed\n", encoding="utf-8")

    phase = doc_status._phase_verify(folder, None, None)

    # Like a stale marker, a malformed one waits for the verifier to run again.
    _warned(phase, "content_check_malformed", reason="content_check_malformed")
    assert phase.state == doc_status.PENDING
    assert phase.detail == (
        "warning: content_check_malformed: content-check.yml malformed; re-run the verifier and content_check.py"
    )


def test_recorded_validation_fail_is_a_warning(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    pdf = _pdf(folder)
    _validation(folder, pdf=pdf, result="fail")

    phase = doc_status._phase_validate(folder, _config(folder), None)

    _warned(phase, "validation_failed")
    assert phase.state == doc_status.DONE
    assert phase.detail == "warning: validation_failed: validation.yml recorded result: fail"


def test_malformed_final_review_is_a_warning_and_review_waits(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    pdf = _pdf(folder)
    (folder / "final-review.yml").write_text("schema: [unclosed\n", encoding="utf-8")

    phase = doc_status._phase_review(folder, _config(folder), None)

    _warned(phase, "final_review_marker_malformed")
    assert phase.state == doc_status.PENDING
    assert pdf.is_file()


def test_warned_phases_never_appear_as_blocked_reasons(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    _body(folder)
    (folder / "content-check.yml").write_text("result: [unclosed\n", encoding="utf-8")

    status = doc_status.derive(folder)

    assert status.blocked_reasons == ()
    verify = next(p for p in status.phases if p.name == "verify")
    assert verify.state == doc_status.CURRENT
    assert verify.detail.startswith("warning: content_check_malformed: ")
    assert status.gate.startswith("verify pending - ") and "content_check.py" in status.gate
    assert "content_check_malformed" in doc_status.render_machine(status)


def test_hard_failures_still_block(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder, route="galactic")

    phase = doc_status._phase_intake(folder, _config(folder), None)

    assert phase.state == doc_status.BLOCKED and phase.blocked_reason == "unknown_route"


def test_a_recorded_final_review_after_a_failed_validation_opens_delivery(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    pdf = _pdf(folder)
    _validation(folder, pdf=pdf, result="fail")
    _final_review(folder, pdf=pdf)
    config = _config(folder)

    assert doc_status._phase_validate(folder, config, None).state == doc_status.DONE
    assert doc_status._phase_review(folder, config, None).state == doc_status.DONE
