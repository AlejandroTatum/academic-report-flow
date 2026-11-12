"""Plan for the top level and the guide-vs-rubric conflict list (guide-vs-teacher-rubric T3, S6, S2).

``rubric_conflicts`` reads ``rubric.yml`` and the declared guide, prints each teacher
criterion's top-level descriptor as the target the draft must evidence, and warns
about criteria with no planned evidence, rubric-only terms the guide never asks for
and criteria without levels. It never writes and always exits 0.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import rubric_conflicts

GUIDE = "Simular la topologia de red con herramientas tecnologicas y documentar la configuracion.\n"
TOOLS = {
    "id": "herramientas",
    "title": "Uso de herramientas tecnologicas",
    "section": "Procedimiento",
    "origin": "teacher",
    "weight": 2,
    "levels": [
        {"points": 2, "descriptor": "Usa Packet Tracer para simular la topologia"},
        {"points": 1, "descriptor": "Usa una herramienta sin documentar"},
    ],
    "covers": ["G1"],
}
TOP = "herramientas: top level 2 of 2: Usa Packet Tracer para simular la topologia"
RUBRIC_ONLY = (
    "warning: herramientas: rubric-only: the guide never mentions packet, tracer; "
    "the teacher scores it, so plan evidence for it anyway"
)


def _without_covers() -> dict:
    return {key: value for key, value in TOOLS.items() if key != "covers"}


def _folder(tmp_path: Path, criteria: list[dict], guide: str | None = GUIDE) -> Path:
    folder = tmp_path / "ape-1"
    folder.mkdir()
    report = "subject: Redes\n"
    if guide is not None:
        (folder / "guia.md").write_text(guide, encoding="utf-8")
        report += "guide: guia.md\n"
    (folder / "report.yml").write_text(report, encoding="utf-8")
    plan = {"schema": "academic.rubric/v1", "source": "Rubrica U1", "criteria": criteria}
    (folder / "rubric.yml").write_text(yaml.safe_dump(plan, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return folder


def _snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}


def _cli(capsys: pytest.CaptureFixture[str], folder: Path) -> list[str]:
    before = _snapshot(folder.parent)
    assert rubric_conflicts.main([str(folder)]) == 0
    assert _snapshot(folder.parent) == before
    return capsys.readouterr().out.splitlines()


def test_packet_tracer_in_the_top_descriptor_is_rubric_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _folder(tmp_path, [TOOLS])
    expected = ["rubric_conflicts: 1 teacher criterion; the draft must evidence each top level", TOP, RUBRIC_ONLY]
    assert rubric_conflicts.conflicts(folder) == expected
    assert _cli(capsys, folder) == expected


def test_no_planned_evidence_and_no_levels_warn(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bare = {**_without_covers(), "checks": [{"type": "heading_present", "section": "Procedimiento"}]}
    flat = {"id": "informe", "title": "Documentar la configuracion", "section": "Resultados", "origin": "teacher"}
    guide_row = {"id": "g-paso", "title": "Paso del simulador Packet Tracer", "section": "Procedimiento"}
    lines = _cli(capsys, _folder(tmp_path, [bare, flat, guide_row]))
    assert lines == [
        "rubric_conflicts: 2 teacher criteria; the draft must evidence each top level",
        TOP,
        "warning: herramientas: no evidence planned for the top level; "
        "add deliverables: with checks, covers: or a non-heading check",
        RUBRIC_ONLY,
        "warning: informe: no levels; copy the teacher's levels into rubric.yml to plan for the top level",
    ]


def test_evidence_and_guide_terms_present_reports_no_conflict(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    checked = {**_without_covers(), "checks": [{"type": "contains", "text": "Packet Tracer"}]}
    lines = _cli(capsys, _folder(tmp_path, [checked], guide=GUIDE + "Use Packet Tracer.\n"))
    assert lines == [
        "rubric_conflicts: 1 teacher criterion; the draft must evidence each top level",
        TOP,
        "rubric_conflicts: no guide-vs-rubric conflicts",
    ]


def test_accents_case_and_plurals_fold_before_comparing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    accented = {**TOOLS, "title": "Uso de Herramientas Tecnológicas"}
    guide = "Simular la TOPOLOGÍA con una herramienta tecnológica, en Packet Tracer.\n"
    assert _cli(capsys, _folder(tmp_path, [accented], guide=guide))[-1] == "rubric_conflicts: no guide-vs-rubric conflicts"


def test_no_guide_declared_skips_the_term_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    lines = _cli(capsys, _folder(tmp_path, [TOOLS], guide=None))
    assert lines == [
        "rubric_conflicts: no guide declared in report.yml; rubric-only terms not checked",
        "rubric_conflicts: 1 teacher criterion; the draft must evidence each top level",
        TOP,
        "rubric_conflicts: no guide-vs-rubric conflicts",
    ]


def test_guide_only_absent_or_malformed_plan_is_one_line(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    line = "rubric_conflicts: no teacher criteria in rubric.yml (absent, malformed or guide-only); nothing to compare"
    folder = _folder(tmp_path, [{"id": "g1", "title": "Paso", "section": "Procedimiento"}])
    assert _cli(capsys, folder) == [line]
    (folder / "rubric.yml").write_text("criteria: [", encoding="utf-8")
    assert _cli(capsys, folder) == [line]
    (folder / "rubric.yml").unlink()
    assert _cli(capsys, folder) == [line]


def test_usage_error_still_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert rubric_conflicts.main([]) == 0
    assert capsys.readouterr().out.splitlines() == ["usage: rubric_conflicts.py <work-folder>"]
