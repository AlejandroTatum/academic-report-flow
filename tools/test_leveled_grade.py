"""Leveled grade: the teacher rubric graded by levels, apart from guide coverage (guide-vs-teacher-rubric T4, S7, S2)."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

import leveled_grade
import rubric_grade
from test_rubric_trace import CRITERIA, planned_folder, verified_folder

LEVELS = [{"points": p, "descriptor": d} for p, d in
          ((4, "Analisis completo"), (3, "Analisis con detalle"), (2, "Analisis parcial"), (1, "Sin analisis"))]
TEACHER = (
    {"id": "analisis", "title": "Analisis de resultados", "section": "Conclusiones", "origin": "teacher",
     "weight": 6, "levels": LEVELS},
    {"id": "diagrama", "title": "Diagrama de red", "section": "Metodologia", "origin": "teacher",
     "weight": 4, "levels": LEVELS},
)
PLAN = CRITERIA + TEACHER
NO_FILE = ("warning: no leveled-grade.yml: run the independent strict grader "
           "(teacher criteria with levels and the body only) before review")


def _grade(folder: Path, entries: list[dict], body_sha256: str | None = None) -> None:
    sha = body_sha256 or hashlib.sha256((folder / "body.md").read_bytes()).hexdigest()
    data = {"schema": "academic.leveled-grade/v1", "grader": "strict-grader", "body_sha256": sha, "criteria": entries}
    (folder / "leveled-grade.yml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _entry(cid: str, points: object, missing: str = "") -> dict:
    return {"id": cid, "points": points, "descriptor": "Analisis completo", "evidence": "El enlace opera", "missing": missing}


def test_no_teacher_criteria_means_no_leveled_grade_and_no_warning(tmp_path: Path) -> None:
    assert leveled_grade.evaluate(planned_folder(tmp_path)) == (None, [])


def test_missing_file_is_a_warning(tmp_path: Path) -> None:
    folder = planned_folder(tmp_path, PLAN)
    before = sorted(p.name for p in folder.iterdir())
    assert leveled_grade.evaluate(folder) == (None, [NO_FILE])
    assert sorted(p.name for p in folder.iterdir()) == before  # never writes


def test_a_valid_grade_gives_the_weighted_total_and_its_tenth(tmp_path: Path) -> None:
    folder = planned_folder(tmp_path, PLAN)
    _grade(folder, [_entry("analisis", 4), _entry("diagrama", 4)])
    result, lines = leveled_grade.evaluate(folder)
    assert lines == []
    assert (result["score"], result["total"], result["weights"]) == (10, 10, "rubric")
    assert [(r["id"], r["points"], r["top"]) for r in result["criteria"]] == [("analisis", 4, 4), ("diagrama", 4, 4)]


def test_low_levels_warn_and_one_below_the_top_is_a_note(tmp_path: Path) -> None:
    folder = planned_folder(tmp_path, PLAN)
    _grade(folder, [_entry("analisis", 2, "no compara con la teoria"), _entry("diagrama", 3, "sin direcciones IP")])
    result, lines = leveled_grade.evaluate(folder)
    assert lines == [
        "warning: analisis at level 2 of 4; missing for the top level: no compara con la teoria",
        "note: diagrama at level 3 of 4; missing for the top level: sin direcciones IP",
    ]
    assert (result["score"], result["total"]) == (6, 10)  # 6 * 2/4 + 4 * 3/4


def test_stale_body_unknown_id_and_points_off_the_levels_warn(tmp_path: Path) -> None:
    folder = planned_folder(tmp_path, PLAN)
    _grade(folder, [_entry("analisis", 3.5), _entry("diagrama", 4), _entry("extra", 4)], body_sha256="0" * 64)
    result, lines = leveled_grade.evaluate(folder)
    assert lines == [
        "warning: leveled-grade.yml is stale: body.md changed since the grader read it; re-run the independent strict grader",
        "warning: leveled-grade.yml grades extra, not a teacher criterion with levels; ignored",
        "warning: analisis points 3.5 are not one of its levels (4, 3, 2, 1); counted as 0",
    ]
    assert (result["score"], result["total"]) == (4, 10)


def test_a_criterion_left_ungraded_and_a_malformed_file_warn(tmp_path: Path) -> None:
    folder = planned_folder(tmp_path, PLAN)
    _grade(folder, [_entry("diagrama", 4)])
    assert leveled_grade.evaluate(folder)[1] == ["warning: analisis not graded in leveled-grade.yml; counted as 0"]
    (folder / "leveled-grade.yml").write_text("schema: nope\n", encoding="utf-8")
    assert leveled_grade.evaluate(folder) == (
        None, ["warning: leveled-grade.yml malformed: schema must be 'academic.leveled-grade/v1'; no leveled grade"])


def test_rubric_grade_renders_coverage_and_the_leveled_grade_apart(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = verified_folder(tmp_path, PLAN)
    _grade(folder, [_entry("analisis", 2, "no compara"), _entry("diagrama", 3, "sin IP")])
    assert rubric_grade.main([str(folder)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "## Guide coverage" in lines and "## Teacher rubric (leveled)" in lines
    assert "Coverage: 75.00 / 100.00 (75.0%)" in lines  # teacher criteria never enter coverage
    assert "| Analisis de resultados (analisis) | 6 | 2/4 | Analisis completo | no compara |" in lines
    assert "Leveled grade: 6.00 / 10.00 (6.0/10)" in lines
    assert "warning: analisis at level 2 of 4; missing for the top level: no compara" in lines
    assert "note: diagrama at level 3 of 4; missing for the top level: sin IP" in lines
    grade = yaml.safe_load((folder / "rubric-grade.yml").read_text(encoding="utf-8"))
    assert [c["id"] for c in grade["criteria"]] == ["objetivo", "metodologia", "conclusiones"]
    assert grade["leveled"]["score"] == 6.0 and grade["leveled"]["out_of_10"] == 6.0


def test_rubric_grade_without_the_file_warns_and_still_exits_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = verified_folder(tmp_path, PLAN)
    assert rubric_grade.main([str(folder)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert NO_FILE in lines and not any(line.startswith("Leveled grade:") for line in lines)


def test_a_legacy_plan_keeps_its_numbers_and_has_no_leveled_grade(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = verified_folder(tmp_path)
    assert rubric_grade.main([str(folder)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert "Coverage: 75.00 / 100.00 (75.0%)" in lines
    assert "No teacher criteria in rubric.yml: guide coverage only, no leveled grade." in lines
    assert not any(line.startswith(("warning:", "Score:")) for line in lines)
    grade = yaml.safe_load((folder / "rubric-grade.yml").read_text(encoding="utf-8"))
    assert (grade["score"], grade["total"], grade["percentage"], grade["leveled"]) == (75.0, 100.0, 75.0, None)
