"""The ``partial`` requirement state: found|partial|missing with the gap written (T4, S5)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import approval_packet
import content_check
import rubric_grade
import rubric_trace
from conftest import _verification
from test_rubric_trace import BODY, CRITERIA, REQUIREMENTS, planned_folder

PARTIAL = {"criterion": "metodologia", "requirement": "Includes a network diagram", "status": "partial",
           "location": "Metodologia", "evidence": "Se configuro la topologia",
           "gap": "describes the topology but shows no diagram"}


def requirements_with_partial() -> list[dict]:
    return [PARTIAL if r["requirement"] == PARTIAL["requirement"] else r for r in REQUIREMENTS]


def verified_with_partial(tmp_path: Path) -> Path:
    folder = planned_folder(tmp_path)
    path = _verification(folder, requirements=requirements_with_partial())
    content_check.main([str(folder), "--verification", str(path)])
    return folder


@pytest.fixture(autouse=True)
def isolated_drafts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPORT_DRAFT_DIR", str(tmp_path / "system-tmp"))


def marker(folder: Path) -> dict:
    return yaml.safe_load((folder / "content-check.yml").read_text(encoding="utf-8"))


def test_partial_round_trips_with_its_gap_and_keeps_the_criterion_falta(tmp_path: Path) -> None:
    data = marker(verified_with_partial(tmp_path))
    record = next(r for r in data["requirements"] if r["status"] == "partial")
    assert record["gap"] == PARTIAL["gap"] and record["evidence"] == PARTIAL["evidence"]
    meto = next(c for c in data["criteria"] if c["id"] == "metodologia")
    assert meto["status"] == "falta" and "1 partial" in meto["note"]
    assert data["result"] == "fail"
    assert content_check.content_check_state(tmp_path / "wf") == "fail"


def test_partial_without_a_gap_or_a_quote_is_a_usage_error(tmp_path: Path) -> None:
    folder = planned_folder(tmp_path)
    for broken in ({**PARTIAL, "gap": ""}, {k: v for k, v in PARTIAL.items() if k != "gap"},
                   {**PARTIAL, "evidence": ""}):
        path = _verification(folder, requirements=[broken])
        assert content_check.main([str(folder), "--verification", str(path)]) == 2


def test_partial_with_a_quote_absent_from_the_body_is_downgraded_to_missing(tmp_path: Path) -> None:
    folder = planned_folder(tmp_path)
    path = _verification(folder, requirements=[{**PARTIAL, "evidence": "texto que no esta"}])
    content_check.main([str(folder), "--verification", str(path)])
    record = marker(folder)["requirements"][0]
    assert record["status"] == "missing"
    assert any("downgraded to missing" in f for f in marker(folder)["findings"])


def test_old_verification_without_partial_loads_with_unchanged_verdicts(tmp_path: Path) -> None:
    folder = planned_folder(tmp_path)
    path = _verification(folder, requirements=REQUIREMENTS)
    assert content_check.main([str(folder), "--verification", str(path)]) == 0
    data = marker(folder)
    assert [(c["id"], c["status"]) for c in data["criteria"]] == [
        ("objetivo", "cumple"), ("metodologia", "falta"), ("conclusiones", "falta")]
    assert all("gap" not in r for r in data["requirements"])
    assert not any("partial" in c["note"] for c in data["criteria"])


def test_an_existing_marker_without_partial_keeps_its_state(tmp_path: Path) -> None:
    folder = planned_folder(tmp_path)
    ok = [r for r in REQUIREMENTS if r["status"] == "found"]
    content_check.main([str(folder), "--verification", str(_verification(folder, requirements=ok))])
    assert content_check.content_check_state(folder) == "pass"


def test_the_brief_offers_partial_and_asks_for_the_gap(tmp_path: Path) -> None:
    brief = content_check.verify_brief(planned_folder(tmp_path))
    assert "found|partial|missing" in brief and "gap" in brief


def test_a_partial_carried_by_an_incremental_check_keeps_its_gap(tmp_path: Path) -> None:
    folder = verified_with_partial(tmp_path)
    carried = content_check._carried_requirements(
        folder, content_check.rubric_plan.load_rubric(folder), marker(folder)["rubric_sha256"],
        (folder / "body.md").read_text(encoding="utf-8"), {"objetivo"})
    kept = [r for r in carried if r["status"] == "partial"]
    assert kept and kept[0]["gap"] == PARTIAL["gap"]


def test_grade_counts_the_partial_end_to_end_at_half(tmp_path: Path) -> None:
    folder = verified_with_partial(tmp_path)
    assert rubric_grade.main([str(folder)]) == 0
    grade = yaml.safe_load((folder / "rubric-grade.yml").read_text(encoding="utf-8"))
    meto = next(c for c in grade["criteria"] if c["id"] == "metodologia")
    assert meto["score"] == 22.5 and meto["partial"] == 1
    assert PARTIAL["gap"] in meto["gap"]


def test_trace_shows_the_partial_and_its_gap(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = verified_with_partial(tmp_path)
    assert rubric_trace.main([str(folder)]) == 0  # warn-only-gates S2: uncovered criteria warn
    captured = capsys.readouterr()
    out = captured.out
    assert (
        "warning: rubric trace: 2 uncovered criteria (metodologia, conclusiones); "
        "see Uncovered above. The flow continues."
    ) in captured.err.splitlines()
    row = next(line for line in out.splitlines() if line.startswith("| metodologia "))
    assert "(+1 partial)" in row
    assert "requirement partial: Includes a network diagram" in out and PARTIAL["gap"] in out


def test_packet_lists_partial_requirements_with_the_gap(tmp_path: Path) -> None:
    text = approval_packet.render(verified_with_partial(tmp_path))
    assert "| metodologia | falta | 1/2 |" in text
    assert PARTIAL["gap"] in text.split("## Rubric trace")[0]
