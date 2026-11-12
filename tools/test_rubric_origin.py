"""Guide criteria versus the teacher's grading rubric (guide-vs-teacher-rubric T1, S1-S4).

``rubric.yml`` tells the two lists apart: a criterion may carry ``origin: guide|teacher``
and a teacher criterion may carry its ``levels``. A plan without a teacher criterion is
reported as guide-only by ``doc_status``; that report is a warning and never changes the
phase state (S2).
"""
from __future__ import annotations

from pathlib import Path

import pytest

import doc_status
import rubric_plan
from conftest import DEFAULT_RUBRIC_CRITERIA, RUBRIC_SCHEMA, _config, _report, _rubric, _yaml

LEVELS = [
    {"points": 4, "descriptor": "Reflexion profunda y fundamentada"},
    {"points": 3, "descriptor": "Reflexion adecuada"},
    {"points": 2, "descriptor": "Reflexion superficial"},
    {"points": 1, "descriptor": "Sin reflexion"},
]
TEACHER = {
    "id": "docente-ambiental",
    "title": "Responsabilidad ambiental y etica",
    "section": "Reflexion",
    "origin": "teacher",
    "weight": 20,
    "levels": LEVELS,
}
GUIDE = {"id": "objetivo", "title": "Objetivo claro", "section": "Objetivos", "origin": "guide"}


def _data(*criteria: dict, **top: object) -> dict:
    return {"schema": RUBRIC_SCHEMA, "source": "guia y rubrica", "criteria": [dict(c) for c in criteria], **top}


def _write(folder: Path, data: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "rubric.yml").write_text(_yaml(data), encoding="utf-8")


def test_validate_accepts_origin_and_teacher_levels() -> None:
    assert rubric_plan.validate_rubric(_data(GUIDE, TEACHER)) == []


def _check(data: dict) -> tuple[list[str], list[str]]:
    """S2: a mistyped new key is a warning, never a schema error."""
    return rubric_plan.validate_rubric(data), rubric_plan.rubric_warnings(data)


def test_an_unknown_origin_is_a_warning_not_an_error() -> None:
    assert _check(_data({**GUIDE, "origin": "docente"})) == (
        [], ["rubric.yml criterion 1 origin must be 'guide' or 'teacher'"]
    )


def test_levels_on_a_criterion_that_is_not_the_teacher_s_are_a_warning() -> None:
    assert _check(_data({**GUIDE, "levels": LEVELS})) == ([], ["rubric.yml criterion 1 levels need origin: teacher"])


def test_malformed_levels_are_warnings_and_count_as_no_levels() -> None:
    single = _data({**TEACHER, "levels": LEVELS[:1]})
    shape = _data({**TEACHER, "levels": [{"points": 4}, {"points": 0, "descriptor": "x"}]})
    repeated = _data({**TEACHER, "levels": [LEVELS[0], LEVELS[0]]})

    assert _check(single) == (
        [], ["rubric.yml criterion 1 levels must be a list of at least 2 {points, descriptor} mappings"]
    )
    assert _check(shape) == ([], [
        "rubric.yml criterion 1 level 1 descriptor must be a non-empty string",
        "rubric.yml criterion 1 level 2 points must be a number greater than 0",
    ])
    assert _check(repeated) == ([], ["rubric.yml criterion 1 levels repeat points 4"])
    for data in (single, shape, repeated):
        assert rubric_plan.criterion_levels(data["criteria"][0]) == []
    assert rubric_plan.criterion_levels({**TEACHER, "levels": "x"}) == []
    assert rubric_plan.criterion_levels(TEACHER) == LEVELS
    assert rubric_plan.rubric_warnings(_data(GUIDE, TEACHER)) == []
    assert rubric_plan.rubric_warnings("not a mapping") == []


def test_a_teacher_rubric_value_other_than_none_is_a_warning() -> None:
    assert _check(_data(GUIDE, teacher_rubric="none")) == ([], [])
    assert _check(_data(GUIDE, teacher_rubric="pending")) == (
        [], ["rubric.yml teacher_rubric must be 'none' (the user confirmed there is no teacher rubric)"]
    )


def test_a_plan_with_mistyped_new_keys_stays_valid_and_the_cli_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, _data({**GUIDE, "origin": "docente"}, {**TEACHER, "levels": LEVELS[:1]}, teacher_rubric="x"))

    assert rubric_plan.rubric_state(tmp_path) == "valid"
    assert rubric_plan.main([str(tmp_path)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "warning: rubric.yml teacher_rubric must be 'none' (the user confirmed there is no teacher rubric)",
        "warning: rubric.yml criterion 1 origin must be 'guide' or 'teacher'",
        "warning: rubric.yml criterion 2 levels must be a list of at least 2 {points, descriptor} mappings",
        "rubric.yml OK",
    ]


def test_teacher_rubric_status_names_the_three_cases(tmp_path: Path) -> None:
    legacy, graded, confirmed = tmp_path / "legacy", tmp_path / "graded", tmp_path / "confirmed"
    _rubric(legacy)
    _write(graded, _data(GUIDE, TEACHER))
    _write(confirmed, _data(GUIDE, teacher_rubric="none"))

    assert rubric_plan.teacher_rubric_status(legacy) == "guide_only"
    assert rubric_plan.teacher_rubric_status(graded) == "teacher"
    assert rubric_plan.teacher_rubric_status(confirmed) == "none_confirmed"
    assert rubric_plan.teacher_rubric_status(tmp_path / "absent") == ""
    assert [c["id"] for c in rubric_plan.teacher_criteria(graded)] == ["docente-ambiental"]


def test_a_teacher_criterion_wins_over_a_stale_none_marker(tmp_path: Path) -> None:
    _write(tmp_path, _data(TEACHER, teacher_rubric="none"))

    assert rubric_plan.teacher_rubric_status(tmp_path) == "teacher"


def test_legacy_rubric_stays_valid_and_keeps_its_criteria(tmp_path: Path) -> None:
    """S4: a plan written before ``origin`` existed still loads exactly as before."""
    _rubric(tmp_path)

    assert rubric_plan.rubric_state(tmp_path) == "valid"
    assert rubric_plan.load_rubric(tmp_path) == [dict(c) for c in DEFAULT_RUBRIC_CRITERIA]


def _plan(folder: Path) -> doc_status.PhaseState:
    _report(folder)
    return doc_status._phase_plan(folder, _config(folder), None)


def test_plan_warns_that_a_plan_is_guide_only_and_stays_done(tmp_path: Path) -> None:
    _rubric(tmp_path)

    phase = _plan(tmp_path)

    assert phase.state == doc_status.DONE and phase.blocked_reason == ""
    assert phase.detail == (
        "rubric.yml valid (2 criteria, 0 with checks); warning: guide-only plan, no teacher rubric "
        "(add the teacher's criteria with origin: teacher, or record teacher_rubric: none once the user "
        "confirms there is none)"
    )


def test_plan_reports_the_teacher_criteria_and_their_levels(tmp_path: Path) -> None:
    data = _data(GUIDE, TEACHER, {k: v for k, v in TEACHER.items() if k != "levels"} | {"id": "docente-teoria"})
    _write(tmp_path, data)

    phase = _plan(tmp_path)

    assert phase.state == doc_status.DONE
    assert phase.detail == (
        "rubric.yml valid (3 criteria, 0 with checks); teacher rubric: 2 criteria, 1 with levels; "
        "warning: teacher criteria without levels: docente-teoria"
    )


def test_plan_reports_a_confirmed_absence_without_a_warning(tmp_path: Path) -> None:
    _write(tmp_path, _data(GUIDE, teacher_rubric="none"))

    phase = _plan(tmp_path)

    assert phase.state == doc_status.DONE
    assert phase.detail == "rubric.yml valid (1 criterion, 0 with checks); no teacher rubric (confirmed by the user)"


def test_plan_with_malformed_levels_is_done_and_warns_in_its_detail(tmp_path: Path) -> None:
    _write(tmp_path, _data(GUIDE, {**TEACHER, "levels": LEVELS[:1]}))

    phase = _plan(tmp_path)

    assert phase.state == doc_status.DONE and phase.blocked_reason == ""
    assert phase.detail == (
        "rubric.yml valid (2 criteria, 0 with checks); teacher rubric: 1 criterion, 0 with levels; "
        "warning: teacher criteria without levels: docente-ambiental; "
        "warning: rubric.yml criterion 2 levels must be a list of at least 2 {points, descriptor} mappings"
    )
