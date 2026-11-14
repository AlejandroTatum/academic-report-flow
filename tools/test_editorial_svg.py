"""Editorial technical figures: layouts, style tokens and the print-size check (#63)."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import editorial_svg
import pytest
import yaml

ACTOR_SPEC = {
    "kind": "actor_map",
    "title": "Sistema de prueba",
    "scope": "Alcance MVP",
    "steps": [["Asignación", "y aprobación"], ["Seguimiento", ""], ["Cierre", "final"]],
    "note": "Cada evidencia queda ligada a una actividad.",
    "top": [{"name": "Estudiante", "category": "principal", "lines": ["registra"], "link": "both"},
            {"name": "Tutor", "category": "secundario", "lines": ["revisa"]},
            {"name": "Coordinador", "category": "responsable", "lines": ["asigna"]}],
    "bottom": [{"name": "Dirección", "category": "externo", "lines": ["consulta"], "link": "from_system"},
               {"name": "Tutor externo", "category": "secundario", "lines": ["valida"]},
               {"name": "Entidad", "category": "externo", "lines": ["acepta"]}],
    "designates": {"top": True, "bottom": True},
    "services": [{"name": "SIAAF", "lines": ["datos"], "out_of_scope": True},
                 {"name": "Correo", "lines": ["alertas"], "link": "from_system"}],
}
CONCEPT_SPEC = {
    "kind": "concept_map",
    "center": {"title": "Spec-Driven Development", "subtitle": "flujo de GitHub Spec Kit"},
    "branches": [{"name": "Constitution", "link": "fija", "items": ["principios"]},
                 {"name": "Specify", "link": "describe", "items": ["qué y porqué", "historias"]},
                 {"name": "Clarify", "link": "resuelve", "items": ["ambigüedades"]},
                 {"name": "Plan", "link": "decide", "items": ["stack", "datos"]}],
}


def texts(svg: str) -> list[str]:
    return ["".join(e.itertext()) for e in ET.fromstring(svg).iter() if e.tag.endswith("text")]


def test_actor_map_renders_every_actor_step_and_service() -> None:
    svg = editorial_svg.render(ACTOR_SPEC)
    labels = texts(svg)
    for name in ("Sistema de prueba", "Estudiante", "Coordinador", "Dirección", "Entidad", "SIAAF", "Correo",
                 "Asignación", "Cierre", "designa", "fuera del alcance", "USUARIO PRINCIPAL", "ALCANCE MVP"):
        assert name in labels, name
    assert [label for label in labels if label in {"1", "2", "3"}] == ["1", "2", "3"]
    assert svg.count('stroke-dasharray="6 5"') >= 2  # SIAAF connector and the key line


def test_concept_map_labels_every_link() -> None:
    svg = editorial_svg.render(CONCEPT_SPEC)
    labels = texts(svg)
    for word in ("Spec-Driven Development", "FLUJO DE GITHUB SPEC KIT", "fija", "describe", "resuelve", "decide",
                 "Constitution", "Plan", "qué y porqué", "datos"):
        assert word in labels, word
    assert svg.count("<line ") == 4  # one labelled link per branch


def test_layouts_use_only_the_style_palette_and_fonts() -> None:
    allowed = {editorial_svg.INK, editorial_svg.MUTED, editorial_svg.HAIRLINE, editorial_svg.ACCENT,
               editorial_svg.PANEL, editorial_svg.LINE, "#FFFFFF", *(bar for _, bar in editorial_svg.CATEGORIES.values())}
    for spec in (ACTOR_SPEC, CONCEPT_SPEC):
        svg = editorial_svg.render(spec)
        assert set(re.findall(r"#[0-9A-Fa-f]{6}", svg)) <= allowed
        assert set(re.findall(r'font-family="([^"]+)"', svg)) <= {editorial_svg.SANS, editorial_svg.SERIF}
        assert not re.search(r'rx="(?:[3-9]|\d\d)', svg), "no rounded pill cards"


@pytest.mark.parametrize("spec", [ACTOR_SPEC, CONCEPT_SPEC], ids=["actor_map", "concept_map"])
def test_layouts_pass_the_print_size_check(spec) -> None:
    assert editorial_svg.check(editorial_svg.render(spec)) == []


def test_check_flags_text_below_the_print_minimum() -> None:
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="100" viewBox="0 0 1000 100">'
           '<text font-size="10">tiny</text><text font-size="20">fine</text></svg>')
    sizes = dict((label, size) for size, label in editorial_svg.printed_sizes(svg, 13.5))
    assert sizes["tiny"] == pytest.approx(10 * 13.5 / 2.54 * 72 / 1000)
    problems = editorial_svg.check(svg, 13.5, 5.5)
    assert len(problems) == 1 and "'tiny'" in problems[0]


@pytest.mark.parametrize("change, message", [
    ({"top": ACTOR_SPEC["top"][:2]}, "exactly 3 'top'"),
    ({"steps": [["solo"]]}, "2 to 6 'steps'"),
    ({"bottom": [*ACTOR_SPEC["bottom"][:2], {"name": "X", "category": "otro"}]}, "unknown category"),
    ({"kind": "radar"}, "unknown kind"),
])
def test_invalid_actor_specs_are_rejected(change, message) -> None:
    with pytest.raises(editorial_svg.SpecError, match=message):
        editorial_svg.render({**ACTOR_SPEC, **change})


def test_concept_map_limits() -> None:
    with pytest.raises(editorial_svg.SpecError, match="2 to 4 'branches'"):
        editorial_svg.render({**CONCEPT_SPEC, "branches": CONCEPT_SPEC["branches"][:1]})
    with pytest.raises(editorial_svg.SpecError, match="at most 5 'items'"):
        editorial_svg.render({**CONCEPT_SPEC, "branches": [{"name": "A", "link": "x", "items": list("abcdef")},
                                                           CONCEPT_SPEC["branches"][0]]})


def test_cli_render_and_check(tmp_path: Path, capsys) -> None:
    spec = tmp_path / "map.yml"
    spec.write_text(yaml.safe_dump(CONCEPT_SPEC, allow_unicode=True), encoding="utf-8")
    out = tmp_path / "out" / "map.svg"
    assert editorial_svg.main(["render", str(spec), "--out", str(out)]) == 0
    assert out.is_file() and f"rendered {out}" in capsys.readouterr().out
    assert editorial_svg.main(["check", str(out)]) == 0
    assert "print size check: PASS" in capsys.readouterr().out
    assert editorial_svg.main(["check", str(out), "--min-pt", "40"]) == 0  # warn-only-gates S2
    assert "warning: print size check: FAIL" in capsys.readouterr().err
    bad = tmp_path / "bad.yml"
    bad.write_text("kind: radar\n", encoding="utf-8")
    assert editorial_svg.main(["render", str(bad), "--out", str(out)]) == 2
    assert "unknown kind" in capsys.readouterr().err
