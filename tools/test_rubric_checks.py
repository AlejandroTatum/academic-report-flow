"""Behavior tests for planned, read-only rubric assertions."""
from pathlib import Path

import pytest

from rubric_checks import TOLERANCE_RULES, run_checks


def test_fenced_and_setext_sections_and_trailing_hashes(tmp_path: Path) -> None:
    body = """~~~md
# Fake
~~~
Real
====
needle
```md
# Fake two
```
# Next ###
other
"""
    checks = [
        {"type": "contains", "section": "Real", "text": "needle"},
        {"type": "heading_present", "section": "Fake"},
        {"type": "heading_present", "section": "Fake two"},
        {"type": "heading_present", "section": "Next"},
    ]
    assert [r.ok for r in run_checks(tmp_path, [{"id": "x", "checks": checks}], body)] == [True, False, False, True]


def test_thematic_break_after_blank_does_not_end_section(tmp_path: Path) -> None:
    body = '# First\nneedle\n\n---\nmore text\n# Second\nother'
    checks = [{'type': 'contains', 'section': 'First', 'text': 'more text'},
              {'type': 'heading_present', 'section': 'more text'}]
    assert [r.ok for r in run_checks(tmp_path, [{'id': 'x', 'checks': checks}], body)] == [True, False]
    assert run_checks(tmp_path, [{'id': 'x', 'checks': [
        {'type': 'heading_present', 'section': 'Actual'}]}], 'Actual\n---\nbody')[0].ok


def test_section_includes_its_subsections_until_a_same_level_heading(tmp_path: Path) -> None:
    # APE control questions are `##` headings under `# Preguntas de Control`.
    body = ("# Preguntas de Control\n\n## ¿Por qué estándares?\n\nRespuesta.\n\n"
            "![Mapa](figures/m.png)\n\n# Conclusiones\n\nfuera\n")
    checks = [{"type": "contains", "section": "Preguntas de Control", "text": "¿Por qué estándares?"},
              {"type": "figure_referenced", "section": "Preguntas de Control"},
              {"type": "contains", "section": "Preguntas de Control", "text": "fuera"},
              {"type": "contains", "section": "¿Por qué estándares?", "text": "Respuesta."}]
    assert [r.ok for r in run_checks(tmp_path, [{"id": "x", "checks": checks}], body)] == [True, True, False, True]


def test_unknown_runtime_check_fails_with_detail(tmp_path: Path) -> None:
    result, = run_checks(tmp_path, [{"id": "x", "checks": [{"type": "unknown", "section": "Missing"}]}], "")
    assert not result.ok and "unknown check type" in result.detail


BODY = """# Óbjetivos
Investigación aplicada y evaluación sistemática [@one] [@two].
1. Analyze data
2. Present findings
![Chart](chart.png)
<https://example.org/one> [Site](https://example.org/two)

# Conclusiones
La investigación y evaluación aportan resultados.
"""


@pytest.mark.parametrize("check,expected", [
    ({"type": "heading_present", "section": "OBJETIVOS"}, True),
    ({"type": "heading_present", "section": "Absent"}, False),
    ({"type": "contains", "section": "objetivos", "text": "INVESTIGACIÓN"}, True),
    ({"type": "contains", "text": "never"}, False),
    ({"type": "matches", "section": "Objetivos", "pattern": r"evaluación\s+sistemática"}, True),
    ({"type": "matches", "pattern": r"never\d+"}, False),
    ({"type": "ordered_list", "section": "Objetivos", "min_items": 2}, True),
    ({"type": "ordered_list", "section": "Conclusiones"}, False),
    ({"type": "min_citations", "section": "Objetivos", "count": 2}, True),
    ({"type": "min_citations", "section": "Conclusiones", "count": 1}, False),
    ({"type": "figure_referenced", "section": "Objetivos"}, True),
    ({"type": "figure_referenced", "section": "Conclusiones"}, False),
    ({"type": "link_present", "section": "Objetivos", "pattern": "example.org/two"}, True),
    ({"type": "link_present", "section": "Objetivos", "pattern": "other"}, False),
    ({"type": "keywords_from_section", "section": "Conclusiones", "from_section": "Objetivos"}, True),
    ({"type": "keywords_from_section", "section": "Conclusiones", "from_section": "Absent"}, False),
    ({"type": "contains", "section": "Absent", "text": "never"}, False),
])
def test_each_check_pass_and_fail(tmp_path: Path, check: dict, expected: bool) -> None:
    result, = run_checks(tmp_path, [{"id": "objective", "checks": [check]}], BODY)
    assert result.ok is expected, result.detail
    assert result.criterion_id == "objective"
    assert result.check_index == 1
    assert result.type == check["type"]


@pytest.mark.parametrize("guide,body,expected", [
    ("preparar el informe exacto", "Preparar el informe exacto", True),
    ("Preparar el informe exacto", "preparar el informe exacto", True),
    ("preparar el informe exacto", "Preparar el Informe exacto", False),
    ("preparar el informe exacto", "Preparar el reporte exacto", False),
])
def test_verbatim_allows_only_initial_case_difference(tmp_path: Path, guide: str, body: str, expected: bool) -> None:
    (tmp_path / "guide.md").write_text(guide)
    check = {"type": "verbatim_from_guide", "section": "Objetivos", "source": "guide.md",
             "text": "Preparar el informe exacto"}
    result, = run_checks(tmp_path, [{"id": "objective", "checks": [check]}], "# Objetivos\n" + body)
    assert result.ok is expected


def test_verbatim_requires_guide_and_section_and_normalizes_whitespace(tmp_path: Path) -> None:
    guide = tmp_path / "guide.md"
    guide.write_text("Exact phrase from guide", encoding="utf-8")
    check = {"type": "verbatim_from_guide", "section": "Objetivos", "source": "guide.md", "text": "Exact phrase from guide"}
    criterion = [{"id": "exact", "checks": [check]}]
    assert run_checks(tmp_path, criterion, "# Objetivos\nExact\n phrase from guide")[0].ok
    assert not run_checks(tmp_path, criterion, BODY)[0].ok
    guide.write_text("Different guide", encoding="utf-8")
    assert not run_checks(tmp_path, criterion, "# Objetivos\nExact phrase from guide")[0].ok
    assert not run_checks(tmp_path, criterion, "odd body without headings")[0].ok


def test_text_checks_ignore_the_bold_and_code_markers_typeset_adds(tmp_path: Path) -> None:
    (tmp_path / "guide.md").write_text("Definir el contrato OpenAPI del servicio", encoding="utf-8")
    checks = [
        {"type": "contains", "section": "Preguntas de Control", "text": "contrato OpenAPI"},
        {"type": "contains", "section": "Preguntas de Control", "text": "GET /api/v1/practicas/ lista"},
        {"type": "verbatim_from_guide", "section": "Preguntas de Control", "source": "guide.md",
         "text": "Definir el contrato OpenAPI del servicio"},
    ]
    body = (
        "# Preguntas de Control\n"
        "Definir el contrato **OpenAPI** del servicio: `GET /api/v1/practicas/` lista y *valida*.\n"
    )
    results = run_checks(tmp_path, [{"id": "preguntas-control", "checks": checks}], body)
    assert [result.ok for result in results] == [True, True, True]


def test_text_checks_still_fail_when_the_text_is_missing_around_markers(tmp_path: Path) -> None:
    (tmp_path / "guide.md").write_text("Definir el contrato OpenAPI del servicio", encoding="utf-8")
    checks = [
        {"type": "contains", "section": "Preguntas de Control", "text": "contrato OpenAPI"},
        {"type": "verbatim_from_guide", "section": "Preguntas de Control", "source": "guide.md",
         "text": "Definir el contrato OpenAPI del servicio"},
    ]
    body = "# Preguntas de Control\nDefinir el esquema **OpenAPI** del `servicio`.\n"
    results = run_checks(tmp_path, [{"id": "preguntas-control", "checks": checks}], body)
    assert [result.ok for result in results] == [False, False]
    assert "text 'contrato OpenAPI' missing" in results[0].detail


def test_tolerance_rules_constant_pins_the_check_tolerances() -> None:
    """The judge brief quotes this constant, so its prose cannot drift."""
    assert "verbatim_from_guide" in TOLERANCE_RULES
    assert "normalizes whitespace" in TOLERANCE_RULES
    assert "first letter" in TOLERANCE_RULES
    assert "contains is case-insensitive" in TOLERANCE_RULES
    assert "accent-insensitively" in TOLERANCE_RULES


def test_section_scope_warnings_flag_contains_scoped_to_a_missing_heading() -> None:
    from rubric_checks import section_scope_warnings

    body = "# Objetivo\ntexto\n"
    criteria = [{"id": "firmas", "checks": [
        {"type": "contains", "section": "Firmas", "text": "Representante"},
        {"type": "contains", "section": "Objetivo", "text": "texto"},
        {"type": "contains", "text": "texto"},
        {"type": "heading_present", "section": "Anexos"},
    ]}]

    warnings = section_scope_warnings(criteria, body)

    assert len(warnings) == 1
    assert "firmas" in warnings[0] and "Firmas" in warnings[0] and "document-wide" in warnings[0]


@pytest.mark.parametrize("check", [
    {"type": "contains", "section": "Renamed", "text": "investigación"},
    {"type": "matches", "section": "Renamed", "pattern": r"evaluación\s+sistemática"},
])
def test_text_check_with_missing_section_falls_back_to_document_wide(tmp_path: Path, check: dict) -> None:
    result, = run_checks(tmp_path, [{"id": "objective", "checks": [check]}], BODY)

    assert result.ok is True, result.detail
    assert "document-wide" in result.detail
