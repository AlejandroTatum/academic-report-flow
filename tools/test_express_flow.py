"""Express flow (`flow: express`): one human gate, the final review.

Quick daily documents on the non-academic routes skip the draft approval
question: the agent records the approval itself with
``approval_marker.py approve --express`` and the user decides once, on the final
PDF. The academic route never accepts it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import approval_marker
import doc_status
from conftest import _body, _config, _report


def _express(folder: Path, route: str = "business", flow: str = "express") -> Path:
    path = _report(folder, route=route)
    path.write_text(path.read_text(encoding="utf-8") + f"flow: {flow}\n", encoding="utf-8")
    return path


def _phases(folder: Path) -> dict[str, doc_status.PhaseState]:
    return {phase.name: phase for phase in doc_status.derive(folder).phases}


def test_express_on_the_academic_route_blocks_intake(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _express(folder, route="academic")

    intake = _phases(folder)["intake"]

    assert intake.state == doc_status.BLOCKED
    assert intake.blocked_reason == "express_academic_route"
    assert intake.detail == "flow=express is not allowed on route=academic: university work keeps its gates"


def test_unknown_flow_blocks_intake(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _express(folder, flow="fast")

    intake = _phases(folder)["intake"]

    assert intake.state == doc_status.BLOCKED
    assert intake.blocked_reason == "unknown_flow"
    assert intake.detail == "flow=fast not recognized: use standard or express"


def test_standard_flow_and_absent_flow_keep_intake_done(tmp_path: Path) -> None:
    standard = tmp_path / "standard"
    _express(standard, flow="standard")
    absent = tmp_path / "absent"
    _report(absent, route="business")

    assert _phases(standard)["intake"].state == doc_status.DONE
    assert _phases(absent)["intake"].state == doc_status.DONE


def test_approve_express_records_a_current_marker(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "wf"
    _express(folder)
    _body(folder)

    code = approval_marker.main(["approve", str(folder), "--express"])

    out = capsys.readouterr()
    assert code == 0
    assert out.out == f"recorded {folder / 'approval.yml'}\n"
    assert out.err == ""
    marker = (folder / "approval.yml").read_text(encoding="utf-8")
    assert 'approved_by: "express flow (no draft gate)"' in marker
    assert "gate: express\n" in marker
    assert approval_marker.approval_state(folder).state == "current"
    assert doc_status._phase_approval(folder, _config(folder), None).state == doc_status.DONE


@pytest.mark.parametrize(
    ("route", "flow", "message"),
    [
        ("business", None, "approval not recorded: --express needs flow: express in report.yml\n"),
        ("business", "standard", "approval not recorded: --express needs flow: express in report.yml\n"),
        ("academic", "express", "approval not recorded: --express is not allowed on route=academic\n"),
    ],
)
def test_approve_express_is_refused_outside_the_express_flow(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], route: str, flow: str | None, message: str
) -> None:
    folder = tmp_path / "wf"
    if flow is None:
        _report(folder, route=route)
    else:
        _express(folder, route=route, flow=flow)
    _body(folder)

    code = approval_marker.main(["approve", str(folder), "--express"])

    out = capsys.readouterr()
    assert code == 1
    assert out.out == ""
    assert out.err == message
    assert not (folder / "approval.yml").exists()
    assert not (folder / "approved-body.md").exists()


def test_approve_needs_exactly_one_of_by_and_express(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _express(folder)
    _body(folder)

    with pytest.raises(SystemExit) as neither:
        approval_marker.main(["approve", str(folder)])
    with pytest.raises(SystemExit) as both:
        approval_marker.main(["approve", str(folder), "--by", "Ana", "--express"])

    assert neither.value.code == 2
    assert both.value.code == 2
    assert not (folder / "approval.yml").exists()


def test_approve_by_name_still_works(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder, route="business")
    _body(folder)

    assert approval_marker.main(["approve", str(folder), "--by", "Ana"]) == 0
    assert 'approved_by: "Ana"' in (folder / "approval.yml").read_text(encoding="utf-8")
    assert "gate: express" not in (folder / "approval.yml").read_text(encoding="utf-8")


def test_express_approval_guidance_never_asks_the_user(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _express(folder)
    _body(folder)

    guidance = doc_status._guidance("approval", folder, _config(folder))

    assert guidance.startswith("express flow: there is no draft gate; do not ask the user and do not build a preview; run ")
    assert "approval_marker.py" in guidance and f"approve {folder} --express" in guidance
    assert "ask_user_choice" not in guidance
    assert "the user sees the document once, at review" in guidance


def test_express_keeps_the_final_review_gate(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _express(folder)
    standard = tmp_path / "std"
    _report(standard, route="business")

    assert doc_status._guidance("review", folder, _config(folder)) == doc_status._guidance(
        "review", standard, _config(standard)
    ).replace(str(standard), str(folder))
