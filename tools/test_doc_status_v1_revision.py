"""After a v1 with a failing validation, doc_status asks for a review with its findings (S2).

warn-only-gates S2: the validation failure is a warning (validate ``done`` with
``warning: validation_failed``), never a block. The human reviews v1 with its
findings and either asks for a revision (v2/v3) or records the review to continue.
Reports without a current v1, or with a passing validation, route as before.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import deliver_report
import doc_status
from conftest import _body, _config, _final_review, _pdf, _report, _validation
from test_report_v1_flow import FOUND_ONLY, _v1

TOOLS = Path(__file__).resolve().parent

VALIDATION_WARNING = "warning: validation_failed: validation.yml recorded result: fail"


def _revision_guidance(folder: Path, pdf: Path) -> str:
    return (
        f"warning: v1 failed validation ({folder / 'validation.yml'} records result: fail): ask the user "
        f"to review {pdf} with its findings and either request a revision (v2/v3) that resolves them "
        f"(apply it in {folder / 'body.md'}, rebuild and re-validate, then re-run doc_status) or record "
        f"{folder / 'final-review.yml'} to continue with v1 as it stands"
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


def test_failed_validation_after_v1_is_a_warning_and_review_offers_a_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    folder, pdf = _v1(tmp_path, monkeypatch, capsys, review=False)  # rubric findings, no final review
    _validation(folder, pdf=pdf, result="fail", reason="rubric findings")
    folder = folder.resolve()

    machine = _cli(folder, "--json")
    assert machine.returncode == 0
    payload = _payload(machine.stdout)
    states = _states(payload)
    assert payload["next"] == "review" and payload["current"] == "review"
    assert states["generate"][0] == "done"
    assert states["validate"] == ("done", VALIDATION_WARNING, "")
    assert states["review"][0] == "current"
    assert states["deliver"] == ("pending", "waiting for an earlier phase", "")
    assert payload["blockedReasons"] == []
    guidance = _revision_guidance(folder, pdf.resolve())
    assert payload["gate"].startswith("review pending - " + guidance + "; open the PDF for the user")
    assert "\nnext: review\n" in machine.stdout

    human = _cli(folder)
    assert human.returncode == 0
    lines = human.stdout.splitlines()
    assert f"- validate: done - {VALIDATION_WARNING}" in lines
    assert any(line.startswith("**Next**: review - " + guidance + "; open the PDF") for line in lines)
    assert "Route: " in human.stdout and "> [review] >" in human.stdout
    assert human.stdout.split("## Document Workflow Status", 1)[0] == machine.stderr

    # Recording the review continues with v1 as it stands.
    _final_review(folder, pdf=pdf)
    assert _payload(_cli(folder, "--json").stdout)["next"] == "deliver"

    documents = tmp_path / "docs"
    assert deliver_report.main([str(folder), "--documents-root", str(documents)]) == 1
    assert capsys.readouterr().err.startswith(
        "DELIVERY REFUSED: validation.yml no registra result: pass (registró: fail)."
    )
    assert not documents.exists()


def test_without_a_generated_v1_a_failed_validation_is_a_warning_without_revision_guidance(tmp_path: Path) -> None:
    folder = (tmp_path / "wf").resolve()
    _report(folder)
    _body(folder)
    pdf = _pdf(folder)
    _validation(folder, pdf=pdf, result="fail")
    _final_review(folder, pdf=pdf)

    config = _config(folder)
    validate = doc_status._phase_validate(folder, config, None)
    assert (validate.state, validate.detail, validate.blocked_reason) == ("done", VALIDATION_WARNING, "")
    assert doc_status._phase_review(folder, config, None).state == "done"
    assert "request a revision" not in doc_status._guidance("review", folder, config)


def test_passing_validation_after_v1_routes_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    folder, pdf = _v1(tmp_path, monkeypatch, capsys, requirements=FOUND_ONLY, review=False)
    folder = folder.resolve()

    payload = _payload(_cli(folder, "--json").stdout)
    states = _states(payload)
    assert payload["next"] == "review"
    assert states["validate"] == ("done", f"validation.yml passes for {pdf.name}", "")
    assert states["review"][0] == "current"
    assert "request a revision" not in payload["gate"]
    assert payload["blockedReasons"] == []
    assert payload["gate"].startswith(f"review pending - ask the user to review {pdf.resolve()}, then record ")

    _final_review(folder, pdf=pdf)
    assert _payload(_cli(folder, "--json").stdout)["next"] == "deliver"
