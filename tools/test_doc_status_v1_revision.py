"""After a v1 with a failing validation, doc_status routes to review for a revision (S2).

The validation failure stays visible (validate ``blocked`` ``validation_failed``)
and delivery stays blocked, but the human is pointed to reviewing v1 and asking
for a revision (v2/v3) instead of a dead end at validate. Reports without a
current v1, or with a passing validation, route as before.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import deliver_report
from conftest import _body, _final_review, _pdf, _report, _validation
from test_report_v1_flow import FOUND_ONLY, _v1

TOOLS = Path(__file__).resolve().parent

REVISION_DETAIL = "v1 failed validation: review it and request a revision (v2/v3); publication stays blocked"


def _revision_guidance(folder: Path, pdf: Path) -> str:
    return (
        f"v1 failed validation ({folder / 'validation.yml'} records result: fail) and publication stays "
        f"blocked: ask the user to review {pdf} with its findings and to request a revision (v2/v3) "
        f"that resolves them; apply it in {folder / 'body.md'}, rebuild and re-validate, then re-run "
        "doc_status; a final review recorded now does not open delivery"
    )


def _cli(folder: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOLS / "doc_status.py"), str(folder), *extra],
        capture_output=True, text=True, check=False,
    )


def _payload(stdout: str) -> dict:
    block = stdout.split("```json\n", 1)[1].split("\n```", 1)[0]
    return json.loads(block)


def _states(payload: dict) -> dict[str, tuple[str, str, str]]:
    return {p["name"]: (p["state"], p["detail"], p["blockedReason"]) for p in payload["phases"]}


def test_failed_validation_after_v1_routes_to_review_for_a_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    folder, pdf = _v1(tmp_path, monkeypatch, capsys)  # rubric findings, final review recorded
    _validation(folder, pdf=pdf, result="fail", reason="rubric findings")
    folder = folder.resolve()

    machine = _cli(folder, "--json")
    assert machine.returncode == 0
    payload = _payload(machine.stdout)
    states = _states(payload)
    assert payload["next"] == "review" and payload["current"] == "review"
    assert states["generate"][0] == "done"
    assert states["validate"] == ("blocked", "validation.yml recorded result: fail", "validation_failed")
    assert states["review"] == ("current", REVISION_DETAIL, "")
    assert states["deliver"] == ("pending", "waiting for an earlier phase", "")
    assert payload["blockedReasons"] == ["validation_failed"]
    guidance = _revision_guidance(folder, pdf.resolve())
    assert payload["gate"].startswith("review pending - " + guidance + "; open the PDF for the user")
    assert "\nnext: review\n" in machine.stdout

    human = _cli(folder)
    assert human.returncode == 0
    lines = human.stdout.splitlines()
    assert "- validate: blocked - validation.yml recorded result: fail" in lines
    assert f"- review: current - {REVISION_DETAIL}" in lines
    assert "- deliver: pending" in lines
    assert any(line.startswith("**Next**: review - " + guidance + "; open the PDF") for line in lines)
    assert "Route: " in human.stdout and "> [review] >" in human.stdout
    assert human.stdout.split("## Document Workflow Status", 1)[0] == machine.stderr

    documents = tmp_path / "docs"
    assert deliver_report.main([str(folder), "--documents-root", str(documents)]) == 1
    assert capsys.readouterr().err.startswith(
        "DELIVERY REFUSED: validation.yml no registra result: pass (registró: fail)."
    )
    assert not documents.exists()


def test_without_a_generated_v1_a_failed_validation_still_blocks_at_validate(tmp_path: Path) -> None:
    folder = (tmp_path / "wf").resolve()
    _report(folder)
    _body(folder)
    pdf = _pdf(folder)
    _validation(folder, pdf=pdf, result="fail")
    _final_review(folder, pdf=pdf)

    payload = _payload(_cli(folder, "--json").stdout)
    states = _states(payload)
    assert payload["next"] != "review"
    assert states["review"] == ("pending", "waiting for an earlier phase", "")
    assert REVISION_DETAIL not in json.dumps(payload)
    assert "request a revision" not in payload["gate"]


def test_passing_validation_after_v1_routes_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    folder, pdf = _v1(tmp_path, monkeypatch, capsys, requirements=FOUND_ONLY, review=False)
    folder = folder.resolve()

    payload = _payload(_cli(folder, "--json").stdout)
    states = _states(payload)
    assert payload["next"] == "review"
    assert states["validate"] == ("done", f"validation.yml passes for {pdf.name}", "")
    assert states["review"][0] == "current" and states["review"][1] != REVISION_DETAIL
    assert payload["blockedReasons"] == []
    assert payload["gate"].startswith(f"review pending - ask the user to review {pdf.resolve()}, then record ")

    _final_review(folder, pdf=pdf)
    assert _payload(_cli(folder, "--json").stdout)["next"] == "deliver"
