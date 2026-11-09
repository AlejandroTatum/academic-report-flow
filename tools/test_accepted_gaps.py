"""accepted_gaps.py: the human waiver of named ``partial`` requirements (accepted-partial-gaps T1, S2-S5)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import accepted_gaps
import approval_packet
import content_check
import doc_status
import rubric_grade
from conftest import _verification
from test_rubric_trace import CRITERIA, REQUIREMENTS, planned_folder

PARTIAL = {"criterion": "metodologia", "requirement": "Includes a network diagram", "status": "partial",
           "location": "Metodologia", "evidence": "Se configuro la topologia",
           "gap": "describes the topology but shows no diagram"}
OTHER_PARTIAL = {"criterion": "metodologia", "requirement": "Describes the topology", "status": "partial",
                 "location": "Metodologia", "evidence": "Se configuro la topologia",
                 "gap": "names the routers but not their addresses"}
FOUND = [r for r in REQUIREMENTS if r["status"] == "found" and r["requirement"] != OTHER_PARTIAL["requirement"]]
REASON = "the teacher's lab has no diagram tool; she agreed to a verbal description"


@pytest.fixture(autouse=True)
def isolated_drafts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPORT_DRAFT_DIR", str(tmp_path / "system-tmp"))


def verified(tmp_path: Path, requirements: list[dict], criteria: tuple[dict, ...] = CRITERIA) -> Path:
    """A planned folder with a recorded verification of ``requirements``."""
    folder = planned_folder(tmp_path, criteria)
    content_check.main([str(folder), "--verification", str(_verification(folder, requirements=requirements))])
    return folder


def partial_only(tmp_path: Path) -> Path:
    """Every requirement found except one partial: only the human can close the gap."""
    return verified(tmp_path, [*FOUND, PARTIAL])


def two_partials(tmp_path: Path) -> Path:
    return verified(tmp_path, [*[r for r in FOUND if r["requirement"] != "Describes the topology"],
                               PARTIAL, OTHER_PARTIAL])


def accept(folder: Path, requirement: str = PARTIAL["requirement"], *, by: str = "Ana Perez",
           reason: str = REASON, extra: list[str] | None = None) -> int:
    return accepted_gaps.main(["accept", str(folder), "--by", by, "--requirement", requirement,
                               "--reason", reason, *(extra or [])])


def listing(folder: Path) -> dict[str, bytes]:
    return {str(p.relative_to(folder)): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def marker(folder: Path) -> dict:
    return yaml.safe_load((folder / "content-check.yml").read_text(encoding="utf-8"))


def waiver(folder: Path) -> dict:
    return yaml.safe_load((folder / "accepted-gaps.yml").read_text(encoding="utf-8"))


def rewrite(path: Path, edit) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    edit(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


# --- regression: no waiver, nothing changes ---------------------------------


def test_a_partial_without_a_waiver_still_fails(tmp_path: Path) -> None:
    folder = partial_only(tmp_path)
    assert content_check.content_check_state(folder) == "fail"
    assert marker(folder)["result"] == "fail"
    assert accepted_gaps.accepted_gaps_state(folder).state == "absent"


# --- S2: the writer ----------------------------------------------------------


def test_a_waiver_of_the_only_partial_passes_without_rewriting_the_check(tmp_path: Path) -> None:
    folder = partial_only(tmp_path)
    before = (folder / "content-check.yml").read_bytes()
    assert accept(folder) == 0
    assert (folder / "content-check.yml").read_bytes() == before
    assert content_check.content_check_state(folder) == "pass"
    record = next(r for r in marker(folder)["requirements"] if r["status"] == "partial")
    assert record["requirement"] == PARTIAL["requirement"]
    meto = next(c for c in marker(folder)["criteria"] if c["id"] == "metodologia")
    assert meto["status"] == "falta"
    assert marker(folder)["result"] == "fail"


def test_the_waiver_records_who_why_and_the_bindings(tmp_path: Path) -> None:
    folder = partial_only(tmp_path)
    assert accept(folder) == 0
    data = waiver(folder)
    assert data["schema"] == "academic.accepted-gaps/v1"
    assert data["accepted_by"] == "Ana Perez" and data["accepted_at"]
    assert data["gaps"] == [{"criterion": "metodologia", "requirement": PARTIAL["requirement"],
                             "gap": PARTIAL["gap"], "reason": REASON, "accepted_by": "Ana Perez"}]
    for key in ("body_sha256", "rubric_sha256", "bib_sha256", "requirements_sha256"):
        assert key in data


def test_a_second_call_appends_and_a_repeated_one_replaces_the_reason(tmp_path: Path) -> None:
    folder = two_partials(tmp_path)
    assert accept(folder) == 0
    assert content_check.content_check_state(folder) == "fail"
    assert accept(folder, OTHER_PARTIAL["requirement"], by="Luis", reason="out of scope") == 0
    assert accept(folder, by="Ana Perez", reason="new reason") == 0
    gaps = {g["requirement"]: g for g in waiver(folder)["gaps"]}
    assert set(gaps) == {PARTIAL["requirement"], OTHER_PARTIAL["requirement"]}
    assert gaps[PARTIAL["requirement"]]["reason"] == "new reason"
    assert gaps[OTHER_PARTIAL["requirement"]]["accepted_by"] == "Luis"
    assert content_check.content_check_state(folder) == "pass"


@pytest.mark.parametrize("requirement, fragment", [
    ("Lists recommendations", "missing"),
    ("States the goal", "found"),
    ("includes a network diagram", "no requirement"),
    ("Includes a network", "no requirement"),
])
def test_a_requirement_that_is_not_partial_is_refused_and_nothing_is_written(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], requirement: str, fragment: str) -> None:
    folder = verified(tmp_path, [*[r for r in REQUIREMENTS if r["status"] == "found"], PARTIAL,
                                 {"criterion": "conclusiones", "requirement": "Lists recommendations",
                                  "status": "missing", "location": "", "evidence": ""}])
    before = listing(folder)
    assert accept(folder, requirement) == 1
    assert fragment in capsys.readouterr().err
    assert listing(folder) == before
    assert content_check.content_check_state(folder) == "fail"


@pytest.mark.parametrize("by, reason, fragment", [("", REASON, "--by"), ("   ", REASON, "--by"),
                                                  ("Ana Perez", "", "--reason"), ("Ana Perez", "  ", "--reason")])
def test_a_blank_name_or_reason_is_refused(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], by: str, reason: str, fragment: str) -> None:
    folder = partial_only(tmp_path)
    before = listing(folder)
    assert accept(folder, by=by, reason=reason) == 1
    assert fragment in capsys.readouterr().err
    assert listing(folder) == before


def test_a_criterion_that_does_not_own_the_requirement_is_refused(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = partial_only(tmp_path)
    before = listing(folder)
    assert accept(folder, extra=["--criterion", "objetivo"]) == 1
    assert "objetivo" in capsys.readouterr().err
    assert listing(folder) == before
    assert accept(folder, extra=["--criterion", "metodologia"]) == 0


def test_without_a_content_check_nothing_is_accepted(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = planned_folder(tmp_path)
    before = listing(folder)
    assert accept(folder) == 1
    assert "absent" in capsys.readouterr().err
    assert listing(folder) == before


def test_a_stale_content_check_accepts_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = partial_only(tmp_path)
    (folder / "body.md").write_text((folder / "body.md").read_text(encoding="utf-8") + "\n## Nueva\n\nOtra linea.\n",
                                    encoding="utf-8")
    before = listing(folder)
    assert accept(folder) == 1
    assert "stale" in capsys.readouterr().err
    assert listing(folder) == before


def test_a_malformed_content_check_accepts_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = partial_only(tmp_path)
    (folder / "content-check.yml").write_text("{ not: [valid", encoding="utf-8")
    before = listing(folder)
    assert accept(folder) == 1
    assert "malformed" in capsys.readouterr().err
    assert listing(folder) == before


# --- S3/S4: the verdict never trusts a waiver blindly ------------------------


def test_a_waiver_naming_another_requirement_leaves_the_check_failing(tmp_path: Path) -> None:
    folder = two_partials(tmp_path)
    assert accept(folder, OTHER_PARTIAL["requirement"]) == 0
    assert content_check.content_check_state(folder) == "fail"


@pytest.mark.parametrize("name, edit", [
    ("body", lambda f: (f / "body.md").write_text(
        (f / "body.md").read_text(encoding="utf-8") + "\nOtra linea.\n", encoding="utf-8")),
    ("rubric", lambda f: (f / "rubric.yml").write_text(
        (f / "rubric.yml").read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")),
    ("bib", lambda f: (f / "sources.bib").write_text(
        (f / "sources.bib").read_text(encoding="utf-8") + "\n% edited\n", encoding="utf-8")),
])
def test_editing_an_input_after_the_waiver_makes_it_stale(tmp_path: Path, name: str, edit) -> None:
    folder = partial_only(tmp_path)
    assert accept(folder) == 0
    edit(folder)
    assert accepted_gaps.accepted_gaps_state(folder).state == "stale"
    assert content_check.content_check_state(folder) != "pass"


@pytest.mark.parametrize("key", ["body_sha256", "rubric_sha256", "bib_sha256", "requirements_sha256"])
def test_a_waiver_bound_to_other_bytes_is_ignored_while_the_check_is_current(tmp_path: Path, key: str) -> None:
    folder = partial_only(tmp_path)
    assert accept(folder) == 0
    rewrite(folder / "accepted-gaps.yml", lambda d: d.__setitem__(key, "0" * 64))
    assert accepted_gaps.accepted_gaps_state(folder).state == "stale"
    assert content_check.content_check_state(folder) == "fail"


def test_tampering_with_the_recorded_requirements_voids_the_waiver(tmp_path: Path) -> None:
    folder = partial_only(tmp_path)
    assert accept(folder) == 0
    rewrite(folder / "content-check.yml", lambda d: next(
        r for r in d["requirements"] if r["status"] == "partial").__setitem__("gap", "nothing is missing"))
    assert content_check.content_check_state(folder) == "fail"


@pytest.mark.parametrize("drop", ["accepted_by", "accepted_at", "schema", "gaps"])
def test_a_forged_waiver_missing_top_level_fields_does_not_pass(tmp_path: Path, drop: str) -> None:
    folder = partial_only(tmp_path)
    assert accept(folder) == 0
    rewrite(folder / "accepted-gaps.yml", lambda d: d.pop(drop))
    assert accepted_gaps.accepted_gaps_state(folder).state == "malformed"
    assert content_check.content_check_state(folder) == "fail"


@pytest.mark.parametrize("drop", ["reason", "requirement", "criterion", "gap"])
def test_a_forged_waiver_gap_missing_fields_does_not_pass(tmp_path: Path, drop: str) -> None:
    folder = partial_only(tmp_path)
    assert accept(folder) == 0
    rewrite(folder / "accepted-gaps.yml", lambda d: d["gaps"][0].pop(drop))
    assert accepted_gaps.accepted_gaps_state(folder).state == "malformed"
    assert content_check.content_check_state(folder) == "fail"


def test_a_blank_reason_in_the_file_does_not_pass(tmp_path: Path) -> None:
    folder = partial_only(tmp_path)
    assert accept(folder) == 0
    rewrite(folder / "accepted-gaps.yml", lambda d: d["gaps"][0].__setitem__("reason", "  "))
    assert content_check.content_check_state(folder) == "fail"


def test_an_unreadable_waiver_is_malformed_not_a_crash(tmp_path: Path) -> None:
    folder = partial_only(tmp_path)
    (folder / "accepted-gaps.yml").write_bytes(b"\xff\xfe{ not: [valid")
    assert accepted_gaps.accepted_gaps_state(folder).state == "malformed"
    assert accepted_gaps.waived_requirements(folder, marker(folder)["requirements"]) == frozenset()
    assert content_check.content_check_state(folder) == "fail"


def test_a_waiver_copied_into_the_content_check_is_not_trusted(tmp_path: Path) -> None:
    folder = partial_only(tmp_path)

    def forge(data: dict) -> None:
        data["result"] = "pass"
        data["accepted_gaps"] = [{"criterion": "metodologia", "requirement": PARTIAL["requirement"],
                                  "reason": "forged"}]
        for record in data["criteria"]:
            record["status"] = "cumple"

    rewrite(folder / "content-check.yml", forge)
    assert content_check.content_check_state(folder) == "fail"


def test_a_missing_requirement_cannot_be_waived_by_a_hand_written_file(tmp_path: Path) -> None:
    missing = {"criterion": "conclusiones", "requirement": "Lists recommendations", "status": "missing",
               "location": "", "evidence": ""}
    folder = verified(tmp_path, [*[r for r in REQUIREMENTS if r["status"] == "found"], missing])
    assert content_check.content_check_state(folder) == "fail"
    requirements = marker(folder)["requirements"]
    (folder / "accepted-gaps.yml").write_text(yaml.safe_dump({
        "schema": accepted_gaps.SCHEMA, "accepted_at": "2026-11-08T10:00:00Z", "accepted_by": "Ana Perez",
        "body_sha256": accepted_gaps.sha256_file(folder / "body.md"),
        "rubric_sha256": accepted_gaps.sha256_file(folder / "rubric.yml"),
        "bib_sha256": accepted_gaps.sha256_file(folder / "sources.bib"),
        "requirements_sha256": accepted_gaps.requirements_digest(requirements),
        "gaps": [{"criterion": "conclusiones", "requirement": "Lists recommendations",
                  "gap": "none", "reason": "forged"}]}), encoding="utf-8")
    assert content_check.content_check_state(folder) == "fail"


def test_a_mechanical_failure_is_not_waived(tmp_path: Path) -> None:
    broken = tuple({**c, "checks": [{"type": "contains", "section": c["section"], "text": "inexistente"}]}
                   for c in CRITERIA)
    folder = verified(tmp_path, [*FOUND, PARTIAL], criteria=broken)
    assert accept(folder) == 0
    assert content_check.content_check_state(folder) == "fail"


def test_rerunning_the_check_with_the_same_matrix_keeps_the_waiver_and_records_pass(tmp_path: Path) -> None:
    folder = partial_only(tmp_path)
    assert accept(folder) == 0
    assert content_check.main([str(folder), "--verification", str(folder / "verification.yml")]) == 0
    assert marker(folder)["result"] == "pass"
    assert content_check.content_check_state(folder) == "pass"
    assert any(r["status"] == "partial" for r in marker(folder)["requirements"])


def test_rerunning_the_check_with_a_changed_matrix_drops_the_waiver(tmp_path: Path) -> None:
    folder = partial_only(tmp_path)
    assert accept(folder) == 0
    other = {**PARTIAL, "gap": "a different gap"}
    path = _verification(folder, requirements=[*FOUND, other])
    assert content_check.main([str(folder), "--verification", str(path)]) == 1
    assert marker(folder)["result"] == "fail"
    assert content_check.content_check_state(folder) == "fail"


# --- S5: consumers -----------------------------------------------------------


def test_doc_status_verify_is_done_and_names_the_accepted_gaps(tmp_path: Path) -> None:
    folder = partial_only(tmp_path)
    assert doc_status._phase_verify(folder, None, None).state == doc_status.BLOCKED
    assert accept(folder) == 0
    phase = doc_status._phase_verify(folder, None, None)
    assert phase.state == doc_status.DONE
    assert "1 accepted gap" in phase.detail and "Ana Perez" in phase.detail


def test_verify_guidance_names_accepted_gaps_only_when_partials_alone_block(tmp_path: Path) -> None:
    folder = partial_only(tmp_path)
    guidance = doc_status._guidance("verify", folder, blocked_reason="content_check_failed")
    assert "accepted_gaps.py" in guidance
    assert "never run it yourself" in guidance
    missing = {"criterion": "conclusiones", "requirement": "Lists recommendations", "status": "missing",
               "location": "", "evidence": ""}
    folder = verified(tmp_path / "m", [*[r for r in REQUIREMENTS if r["status"] == "found"], PARTIAL, missing])
    assert "accepted_gaps.py" not in doc_status._guidance("verify", folder, blocked_reason="content_check_failed")


def test_the_approval_packet_lists_the_accepted_gap_and_never_claims_cumple(tmp_path: Path) -> None:
    folder = partial_only(tmp_path)
    assert accept(folder) == 0
    text = approval_packet.render(folder)
    section = text.split("## Rubric trace")[0]
    assert "Accepted gaps" in section
    assert PARTIAL["requirement"] in section and REASON in section and "Ana Perez" in section
    assert "| metodologia | falta | " in section
    assert "| metodologia | cumple |" not in text


def test_the_approval_packet_without_a_waiver_has_no_accepted_gaps_listing(tmp_path: Path) -> None:
    assert "Accepted gaps" not in approval_packet.render(partial_only(tmp_path))


def test_rubric_grade_output_is_the_same_with_and_without_the_waiver(tmp_path: Path) -> None:
    folder = partial_only(tmp_path)
    assert rubric_grade.main([str(folder)]) == 0
    before = (folder / "rubric-grade.yml").read_bytes(), (folder / "rubric-grade.md").read_bytes()
    assert accept(folder) == 0
    assert rubric_grade.main([str(folder)]) == 0
    assert ((folder / "rubric-grade.yml").read_bytes(), (folder / "rubric-grade.md").read_bytes()) == before


def test_a_bounded_edit_after_accepting_stales_instead_of_failing(tmp_path: Path) -> None:
    folder = partial_only(tmp_path)
    assert accept(folder) == 0
    assert content_check.content_check_state(folder) == "pass"
    body = folder / "body.md"
    body.write_text(body.read_text(encoding="utf-8").rstrip("\n") + " Fin.\n", encoding="utf-8")

    assert content_check.content_check_state(folder) == "stale"
    assert doc_status._phase_verify(folder, None, None).blocked_reason == "content_check_stale"
