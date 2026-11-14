"""rubric.yml ``needs_person``: requirements only a person can close (faster-verify-loop S5).

The plan marks them up front; the brief tells the verifier to report each as
``partial`` with the recorded reason as ``gap``; the ``--verification`` output and
the ``doc_status`` verify detail label such a partial as waiting for a person.
Nothing else changes: the criterion stays ``falta``, the verdict ``fail``, and
only ``accepted_gaps.py`` (a person) closes it.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import accepted_gaps
import content_check
import doc_status
import rubric_plan
from conftest import _verification
from test_accepted_gaps import FOUND, OTHER_PARTIAL, PARTIAL
from test_rubric_trace import CRITERIA, planned_folder

GAP = "the ADR must be versioned in the repository; only the student can push it"
PERSON = {"item": "G26", "reason": GAP}
NEEDS_PERSON_PARTIAL = {**PARTIAL, "gap": GAP}
BRIEF_BLOCK = (
    "Items only a person can close (rubric needs_person): when body.md only states the plan for one "
    "of them, report its requirement as partial with the recorded reason, verbatim, as gap; do not "
    "spend a finding or a prose_findings entry on it.\n"
    f"- G26: {GAP}\n"
)
LABEL = f"waiting for a person: Includes a network diagram (gap: {GAP})"


@pytest.fixture(autouse=True)
def isolated_drafts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPORT_DRAFT_DIR", str(tmp_path / "system-tmp"))


def _with_rubric_keys(folder: Path, **keys: object) -> Path:
    path = folder / "rubric.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.update(keys)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return folder


def _planned(tmp_path: Path, **keys: object) -> Path:
    folder = planned_folder(tmp_path, CRITERIA)
    return _with_rubric_keys(folder, **keys) if keys else folder


FAILED_WARNING = "warning: content_check_failed: content-check.yml recorded result: fail"


def _check(
    folder: Path, requirements: list[dict], capsys: pytest.CaptureFixture[str]
) -> tuple[int, list[str], list[str]]:
    capsys.readouterr()
    code = content_check.main([str(folder), "--verification", str(_verification(folder, requirements=requirements))])
    captured = capsys.readouterr()
    return code, captured.out.splitlines(), captured.err.splitlines()


# --- the plan ---------------------------------------------------------------


def test_needs_person_entries_validate_and_load(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _planned(tmp_path, needs_person=[PERSON])
    assert rubric_plan.main([str(folder)]) == 0
    assert capsys.readouterr().out == "rubric.yml OK\n"
    assert rubric_plan.load_needs_person(folder) == [PERSON]


@pytest.mark.parametrize(("value", "error"), [
    ("G26", "rubric.yml needs_person must be a list of {item, reason} mappings"),
    (["G26"], "rubric.yml needs_person 1 must be a mapping with item and reason"),
    ([{"item": "G26"}], "rubric.yml needs_person 1 reason must be a non-empty string"),
    ([{"item": "G26", "reason": "  "}], "rubric.yml needs_person 1 reason must be a non-empty string"),
    ([{"item": "G26", "reason": GAP, "owner": "Ana"}], "rubric.yml needs_person 1 unexpected key 'owner'"),
])
def test_malformed_needs_person_entries_are_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], value: object, error: str
) -> None:
    folder = _planned(tmp_path, needs_person=value)
    # warn-only-gates S2: a malformed rubric is a warning on stderr, exit 0.
    assert rubric_plan.main([str(folder)]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"warning: rubric_malformed:\n- {error}\n"
    assert rubric_plan.rubric_state(folder) == "malformed"


def test_an_item_cannot_be_both_needs_person_and_not_applicable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _planned(tmp_path, needs_person=[PERSON], not_applicable=[{"item": "g26", "reason": "no aplica"}])
    assert rubric_plan.main([str(folder)]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "warning: rubric_malformed:\n- rubric.yml needs_person 1 item 'G26' is also listed under not_applicable\n")


def test_a_rubric_without_needs_person_is_unchanged(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _planned(tmp_path)
    assert rubric_plan.main([str(folder)]) == 0
    assert capsys.readouterr().out == "rubric.yml OK\n"
    assert rubric_plan.load_needs_person(folder) == []
    brief = content_check.verify_brief(folder)
    assert "needs_person" not in brief and "waiting for a person" not in brief


# --- the brief --------------------------------------------------------------


def test_the_brief_lists_needs_person_items(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _planned(tmp_path, needs_person=[PERSON])
    assert content_check.main([str(folder), "--verify-brief"]) == 0
    assert BRIEF_BLOCK in capsys.readouterr().out


def test_the_since_brief_lists_needs_person_items(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _planned(tmp_path, needs_person=[PERSON])
    previous = _verification(folder, requirements=[*FOUND, NEEDS_PERSON_PARTIAL])
    assert content_check.main([str(folder), "--verify-brief", "--since", str(previous)]) == 0
    out = capsys.readouterr().out
    assert "Incremental re-verify" in out
    assert BRIEF_BLOCK in out


# --- the labels -------------------------------------------------------------


def test_the_verification_output_labels_the_partial_waiting_for_a_person(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _planned(tmp_path, needs_person=[PERSON])
    code, out, err = _check(folder, [*FOUND, NEEDS_PERSON_PARTIAL], capsys)
    assert (code, err) == (0, [FAILED_WARNING])
    assert out[0] == "content check: fail"
    assert out.count(f"  {LABEL}") == 1


def test_a_fixable_partial_is_not_labelled(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _planned(tmp_path, needs_person=[PERSON])
    found = [r for r in FOUND if r["requirement"] != OTHER_PARTIAL["requirement"]]
    code, out, err = _check(folder, [*found, NEEDS_PERSON_PARTIAL, OTHER_PARTIAL], capsys)
    assert (code, err) == (0, [FAILED_WARNING])
    assert [line for line in out if "waiting for a person" in line] == [f"  {LABEL}"]
    verify = doc_status._phase_verify(folder, None, None)
    assert verify.state == doc_status.DONE
    assert verify.detail == (
        "rubric findings (not a compliance pass): partial: Describes the topology; " + LABEL)


def test_doc_status_labels_the_partial_waiting_for_a_person(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _planned(tmp_path, needs_person=[PERSON])
    _check(folder, [*FOUND, NEEDS_PERSON_PARTIAL], capsys)
    verify = doc_status._phase_verify(folder, None, None)
    assert (verify.state, verify.detail) == (doc_status.DONE, "rubric findings (not a compliance pass): " + LABEL)


def test_without_needs_person_the_same_partial_reads_as_today(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _planned(tmp_path)
    code, out, err = _check(folder, [*FOUND, NEEDS_PERSON_PARTIAL], capsys)
    assert (code, err) == (0, [FAILED_WARNING])
    assert not [line for line in out if "waiting for a person" in line]
    verify = doc_status._phase_verify(folder, None, None)
    assert verify.detail == "rubric findings (not a compliance pass): partial: Includes a network diagram"


# --- nothing else changes ---------------------------------------------------


def test_a_needs_person_partial_still_fails_until_a_person_accepts_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _planned(tmp_path, needs_person=[PERSON])
    _check(folder, [*FOUND, NEEDS_PERSON_PARTIAL], capsys)
    marker = yaml.safe_load((folder / "content-check.yml").read_text(encoding="utf-8"))
    assert marker["result"] == "fail"
    assert next(c for c in marker["criteria"] if c["id"] == "metodologia")["status"] == "falta"
    assert content_check.content_check_state(folder) == "fail"
    assert not (folder / "accepted-gaps.yml").exists()

    assert accepted_gaps.main(["accept", str(folder), "--by", "Ana Perez", "--requirement",
                               PARTIAL["requirement"], "--reason", "pushed by the student"]) == 0
    assert content_check.content_check_state(folder) == "pass"
    assert yaml.safe_load((folder / "content-check.yml").read_text(encoding="utf-8")) == marker
