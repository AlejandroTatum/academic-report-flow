"""rubric_plan: every guide inventory item maps to a criterion or is not_applicable (T4, S5)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import rubric_plan
from conftest import _report, _rubric
from test_guide_facts_inventory import GUIDE

CRITERIA = (
    {"id": "diagrama", "title": "Diagrama", "section": "Desarrollo",
     "deliverables": ["G1 topology diagram", "G2 screenshots"],
     "checks": [{"type": "contains", "text": "topologia"}, {"type": "contains", "text": "captura"}]},
    {"id": "analisis", "title": "Analisis", "section": "Analisis", "covers": ["G3", "G4"]},
)
ALL_MAPPED = [*CRITERIA, {"id": "resto", "title": "Resto", "section": "Resto", "covers": ["G5", "G6", "G7"]}]


def folder_with_guide(tmp_path: Path, criteria: tuple | list = CRITERIA, **extra: object) -> Path:
    folder = tmp_path / "wf"
    _report(folder)
    (folder / "report.yml").write_text((folder / "report.yml").read_text() + "guide: guide.txt\n", encoding="utf-8")
    (folder / "guide.txt").write_text(GUIDE, encoding="utf-8")
    path = _rubric(folder, criteria=tuple(criteria))
    if extra:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data.update(extra)
        path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return folder


def test_unmapped_items_are_reported_with_id_kind_and_text(tmp_path: Path) -> None:
    problems = rubric_plan.inventory_problems(folder_with_guide(tmp_path))
    assert [p.split(":", 1)[0] for p in problems] == ["G5", "G6", "G7"]
    assert "justificar la elección" in problems[0] and "mandate" in problems[0]


def test_deliverable_and_covers_ids_map_items_and_not_applicable_needs_a_reason(tmp_path: Path) -> None:
    folder = folder_with_guide(
        tmp_path, CRITERIA, not_applicable=[{"item": "G5", "reason": "se justifica en la bibliografia"},
                                            {"item": "G6", "reason": "el enlace lo da el docente"},
                                            {"item": "G7", "reason": "formato fijado por la plantilla"}])
    assert rubric_plan.inventory_problems(folder) == []
    assert rubric_plan.rubric_state(folder) == "valid"


def test_not_applicable_without_a_reason_is_malformed(tmp_path: Path) -> None:
    for entry in ({"item": "G5"}, {"item": "G5", "reason": "  "}, {"reason": "x"}, "G5"):
        folder = folder_with_guide(tmp_path / str(abs(hash(str(entry)))), CRITERIA, not_applicable=[entry])
        assert rubric_plan.rubric_state(folder) == "malformed"


def test_an_item_can_be_named_by_its_exact_text(tmp_path: Path) -> None:
    folder = folder_with_guide(tmp_path, ALL_MAPPED[:2], not_applicable=[
        {"item": "El estudiante debe justificar la elección de las direcciones IP.", "reason": "no aplica"},
        {"item": "g6", "reason": "no aplica"}, {"item": "G7", "reason": "no aplica"}])
    assert rubric_plan.inventory_problems(folder) == []


def test_no_guide_or_no_valid_rubric_means_no_inventory_problems(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _rubric(folder)
    assert rubric_plan.inventory_problems(folder) == []
    assert rubric_plan.inventory_problems(tmp_path / "missing") == []


def test_cli_rejects_an_unmapped_item_and_accepts_the_mapped_rubric(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rubric_plan.main([str(folder_with_guide(tmp_path / "a"))]) == 1
    out = capsys.readouterr().out
    assert "guide_inventory_unmapped" in out and "G5" in out
    assert rubric_plan.main([str(folder_with_guide(tmp_path / "b", ALL_MAPPED))]) == 0
    assert "OK" in capsys.readouterr().out


def test_covers_must_be_a_list_of_non_empty_strings(tmp_path: Path) -> None:
    bad = ({"id": "x", "title": "X", "section": "X", "covers": "G1"},)
    assert rubric_plan.rubric_state(folder_with_guide(tmp_path, bad)) == "malformed"
