"""Tests for the per-format fixed section structure (aa-acd-templates T1, S4/S6).

``format: ape`` already fixes the body's level-1 headings and their order.
``aa`` and ``acd`` get the same mechanism: one table of section specs per
format, one validator, active only for the formats the table names. Optional
sections may be absent; required ones must be present and in order. The
bibliography ("Referencias") is rendered by the template, never authored: it is
not required, but an authored one must keep its place.

Everything here goes through the public functions (``section_structure_validation``,
``metadata_validation``, ``content_check.body_check_results``) and asserts on the
errors they return.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import approval_marker  # noqa: E402
import content_check  # noqa: E402
import typeset  # noqa: E402
from conftest import _cited_body, _report, _rubric, _sources_bib  # noqa: E402
from report_config import ReportConfig  # noqa: E402
from validate_report import metadata_validation, section_structure_validation  # noqa: E402

AA_REQUIRED = ("Objetivo(s)", "Introducción", "Desarrollo", "Conclusiones")
AA_FULL = (*AA_REQUIRED, "Referencias", "Anexos", "Declaración de uso de IA")

ACD_REQUIRED = (
    "Objetivo(s)",
    "Síntesis de contenidos abordados",
    "Actividades desarrolladas en clase",
    "Análisis / reflexión",
    "Conclusiones",
)
ACD_FULL = (*ACD_REQUIRED, "Referencias", "Anexos")

APE_FULL = (
    "Objetivo(s) de la Práctica",
    "Materiales, Reactivos, Equipos y Herramientas",
    "Procedimiento / Metodología Ejecutada",
    "Resultados",
    "Preguntas de Control",
    "Conclusiones",
    "Recomendaciones",
    "Anexos",
)

REQUIRED = {"aa": AA_REQUIRED, "acd": ACD_REQUIRED}
FULL = {"aa": AA_FULL, "acd": ACD_FULL}


def body_of(headings: tuple[str, ...]) -> str:
    return "\n".join(f"# {heading}\n\nContenido de {heading}.\n" for heading in headings)


def make_config(tmp_path: Path, fmt: str | None, body: str, **extra: object) -> ReportConfig:
    folder = tmp_path / "r"
    folder.mkdir(parents=True, exist_ok=True)
    raw: dict[str, object] = {"type": "technical_report", "backend": "latex", "body": "body.md"}
    if fmt is not None:
        raw["format"] = fmt
    raw.update(extra)
    (folder / "report.yml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    (folder / "body.md").write_text(body, encoding="utf-8")
    # Built directly so these tests isolate the section check from the rest of
    # report.yml loading (output paths, bibliography, ...).
    return ReportConfig(folder=folder, raw=raw)


# ---------------------------------------------------------------------------
# AA and ACD: required, optional and ordered sections
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["aa", "acd"])
def test_required_sections_in_order_pass(tmp_path, fmt):
    config = make_config(tmp_path, fmt, body_of(REQUIRED[fmt]))
    assert section_structure_validation(config).errors == []


@pytest.mark.parametrize("fmt", ["aa", "acd"])
def test_every_section_in_order_passes(tmp_path, fmt):
    config = make_config(tmp_path, fmt, body_of(FULL[fmt]))
    assert section_structure_validation(config).errors == []


@pytest.mark.parametrize("fmt", ["aa", "acd"])
def test_optional_sections_may_be_absent(tmp_path, fmt):
    optional = [title for title in FULL[fmt] if title not in REQUIRED[fmt]]
    assert optional, "both formats carry optional sections"
    config = make_config(tmp_path, fmt, body_of(REQUIRED[fmt]))
    assert section_structure_validation(config).errors == []


@pytest.mark.parametrize("fmt", ["aa", "acd"])
def test_a_missing_required_section_is_named(tmp_path, fmt):
    for dropped in REQUIRED[fmt]:
        kept = tuple(title for title in REQUIRED[fmt] if title != dropped)
        config = make_config(tmp_path / dropped.split()[0], fmt, body_of(kept))
        errors = section_structure_validation(config).errors
        assert errors == [f"Faltan secciones del formato {fmt.upper()} en body.md: {dropped}"]


@pytest.mark.parametrize("fmt", ["aa", "acd"])
def test_all_missing_required_sections_are_reported_together(tmp_path, fmt):
    config = make_config(tmp_path, fmt, "# Objetivo(s)\n\nSolo esto.\n")
    errors = section_structure_validation(config).errors
    assert len(errors) == 1
    for title in REQUIRED[fmt][1:]:
        assert title in errors[0]


@pytest.mark.parametrize("fmt", ["aa", "acd"])
def test_wrong_order_is_reported_naming_the_section(tmp_path, fmt):
    required = list(REQUIRED[fmt])
    required[1], required[2] = required[2], required[1]
    config = make_config(tmp_path, fmt, body_of(tuple(required)))
    assert section_structure_validation(config).errors == [
        f"La sección '{REQUIRED[fmt][2]}' está fuera del orden requerido por el "
        f"formato {fmt.upper()} en body.md"
    ]


def test_optional_section_out_of_order_is_reported(tmp_path):
    """AA: "Anexos" before "Conclusiones" breaks the fixed order."""
    headings = ("Objetivo(s)", "Introducción", "Desarrollo", "Anexos", "Conclusiones")
    config = make_config(tmp_path, "aa", body_of(headings))
    errors = section_structure_validation(config).errors
    assert len(errors) == 1 and "fuera del orden" in errors[0]


def test_ai_declaration_must_follow_annexes(tmp_path):
    headings = (*AA_REQUIRED, "Declaración de uso de IA", "Anexos")
    config = make_config(tmp_path, "aa", body_of(headings))
    errors = section_structure_validation(config).errors
    assert len(errors) == 1 and "fuera del orden" in errors[0]


@pytest.mark.parametrize("fmt", ["aa", "acd"])
def test_headings_match_without_case_accents_or_extra_space(tmp_path, fmt):
    folded = tuple(title.upper().replace("Í", "I").replace("Á", "A").replace("Ó", "O")
                   for title in REQUIRED[fmt])
    config = make_config(tmp_path, fmt, body_of(folded))
    assert section_structure_validation(config).errors == []


def test_aa_development_subsections_are_free(tmp_path):
    body = (
        "# Objetivo(s)\n\no.\n\n# Introducción\n\ni.\n\n"
        "# Desarrollo\n\n## Cualquier tema\n\nt.\n\n### Más fino\n\nt.\n\n## Otro\n\nt.\n\n"
        "# Conclusiones\n\nc.\n"
    )
    config = make_config(tmp_path, "aa", body)
    assert section_structure_validation(config).errors == []


@pytest.mark.parametrize("fmt", ["aa", "acd"])
def test_subsection_headings_never_count_as_sections(tmp_path, fmt):
    """A level-2 heading with a section's name does not stand in for the level-1 one."""
    kept = REQUIRED[fmt][:-1]
    body = body_of(kept) + f"\n## {REQUIRED[fmt][-1]}\n\ntexto.\n"
    config = make_config(tmp_path, fmt, body)
    assert section_structure_validation(config).errors == [
        f"Faltan secciones del formato {fmt.upper()} en body.md: {REQUIRED[fmt][-1]}"
    ]


# ---------------------------------------------------------------------------
# Referencias: rendered by the template, like the APE bibliography
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["aa", "acd"])
def test_referencias_is_not_required_as_an_authored_heading(tmp_path, fmt):
    config = make_config(tmp_path, fmt, body_of(REQUIRED[fmt]))
    errors = section_structure_validation(config).errors
    assert not any("Referencias" in error for error in errors)


@pytest.mark.parametrize("fmt", ["aa", "acd"])
def test_an_authored_referencias_must_sit_between_conclusiones_and_annexes(tmp_path, fmt):
    early = list(REQUIRED[fmt])
    early.insert(1, "Referencias")
    config = make_config(tmp_path, fmt, body_of(tuple(early)))
    errors = section_structure_validation(config).errors
    assert len(errors) == 1 and "fuera del orden" in errors[0]


# ---------------------------------------------------------------------------
# Activation: only the formats the table names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", [None, "libre"])
def test_other_formats_keep_free_section_choice(tmp_path, fmt):
    config = make_config(tmp_path, fmt, "# Lo que quiera el autor\n\nContenido.\n")
    assert section_structure_validation(config).errors == []


def test_the_aa_list_is_not_applied_to_acd_and_vice_versa(tmp_path):
    config = make_config(tmp_path, "acd", body_of(AA_REQUIRED))
    errors = section_structure_validation(config).errors
    assert errors and "ACD" in errors[0] and "Introducción" not in errors[0]


# ---------------------------------------------------------------------------
# Final validation: surfaces through metadata_validation
# ---------------------------------------------------------------------------


def test_aa_structure_surfaces_through_metadata_validation(tmp_path):
    config = make_config(tmp_path, "aa", "# Objetivo(s)\n\nSolo esto.\n")
    errors = metadata_validation(config).errors
    assert any(error.startswith("Faltan secciones del formato AA en body.md") for error in errors)


def test_acd_structure_surfaces_through_metadata_validation(tmp_path):
    """End to end (aa-acd-templates T2): the `acd` key is registered, so the
    section check runs inside metadata_validation instead of an unknown-format stop."""
    config = make_config(tmp_path, "acd", "# Objetivo(s)\n\nSolo esto.\n")
    errors = metadata_validation(config).errors
    assert not any("Formato de documento desconocido" in error for error in errors)
    assert any(error.startswith("Faltan secciones del formato ACD en body.md") for error in errors)


def test_acd_loads_from_disk_and_validates_its_structure(tmp_path):
    folder = tmp_path / "loaded"
    folder.mkdir()
    (folder / "report.yml").write_text(yaml.safe_dump({
        "type": "technical_report", "backend": "latex", "output": "pdf",
        "pdf": "build/report.pdf", "body": "body.md", "format": "acd",
        "metadata": {
            "title": "Sesión", "subject": "Plataformas", "teacher": "Ing. Ríos",
            "student": "Camila", "date": "6 de octubre de 2026", "cycle": "Quinto",
            "unit": "Unidad 2", "learning_outcome": "Diseña APIs", "practice_number": "4",
            "schedule": "10:00", "place": "Lab 3", "planned_time": "2 horas",
        },
    }), encoding="utf-8")
    (folder / "body.md").write_text(body_of(ACD_FULL), encoding="utf-8")

    config = ReportConfig.load(folder)

    assert config.format == "acd"
    assert metadata_validation(config).errors == []
    (folder / "body.md").write_text(body_of(ACD_REQUIRED[:-1]), encoding="utf-8")
    assert any("Faltan secciones del formato ACD" in e for e in metadata_validation(config).errors)


def test_a_structured_aa_body_adds_no_structure_error_to_metadata_validation(tmp_path):
    config = make_config(tmp_path, "aa", body_of(AA_FULL))
    errors = metadata_validation(config).errors
    assert not any("secciones del formato" in error or "fuera del orden" in error for error in errors)


# ---------------------------------------------------------------------------
# Draft-time content check
# ---------------------------------------------------------------------------


def _verify_folder(folder: Path) -> Path:
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    _cited_body(folder)
    return folder


def structure_folder(tmp_path: Path, fmt: str, headings: tuple[str, ...]) -> Path:
    folder = _verify_folder(tmp_path / "wf")
    report = folder / "report.yml"
    report.write_text(report.read_text(encoding="utf-8") + f"format: {fmt}\n", encoding="utf-8")
    body = "".join(f"# {title}\n\nTexto con [@key1].\n\n" for title in headings)
    (folder / "body.md").write_text(body, encoding="utf-8")
    return folder


def structure_check(folder: Path, fmt: str) -> dict | None:
    """The fixed-heading check of the typeset body (issue #96: the plain draft is not checked)."""
    approval_marker.record_approval(folder, "Ana")
    shutil.copyfile(folder / "body.md", folder / "body.typeset.md")
    typeset.bind(folder)
    return {i["check"]: i for i in typeset.check_results(folder)}.get(f"{fmt}_structure")


@pytest.mark.parametrize("fmt", ["aa", "acd"])
def test_typeset_check_passes_a_correct_body(tmp_path, fmt):
    check = structure_check(structure_folder(tmp_path, fmt, FULL[fmt]), fmt)
    assert check is not None and check["ok"]


@pytest.mark.parametrize("fmt", ["aa", "acd"])
def test_typeset_check_names_the_missing_section(tmp_path, fmt):
    kept = REQUIRED[fmt][:-1]
    check = structure_check(structure_folder(tmp_path, fmt, kept), fmt)
    assert check is not None and not check["ok"]
    assert REQUIRED[fmt][-1] in check["detail"]


@pytest.mark.parametrize("fmt", ["aa", "acd"])
def test_typeset_check_flags_wrong_order(tmp_path, fmt):
    required = list(REQUIRED[fmt])
    required[1], required[2] = required[2], required[1]
    check = structure_check(structure_folder(tmp_path, fmt, tuple(required)), fmt)
    assert check is not None and not check["ok"]
    assert "fuera del orden" in check["detail"]


def test_draft_check_has_no_structure_entry_without_a_fixed_format(tmp_path):
    folder = _verify_folder(tmp_path / "wf")
    names = {item["check"] for item in content_check.body_check_results(folder)}
    assert not names & {"ape_structure", "aa_structure", "acd_structure"}


# ---------------------------------------------------------------------------
# APE regression (S6): headings, order, messages and omit semantics unchanged
# ---------------------------------------------------------------------------


def test_ape_full_body_passes(tmp_path):
    config = make_config(tmp_path, "ape", body_of(APE_FULL))
    assert section_structure_validation(config).errors == []


def test_ape_messages_are_unchanged(tmp_path):
    missing = make_config(tmp_path / "m", "ape", "# Objetivo(s) de la Práctica\n\no.\n\n# Anexos\n")
    assert section_structure_validation(missing).errors == [
        "Faltan secciones del formato APE en body.md: Materiales, Reactivos, Equipos y "
        "Herramientas, Procedimiento / Metodología Ejecutada, Resultados, "
        "Preguntas de Control, Conclusiones, Recomendaciones"
    ]
    swapped = list(APE_FULL)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    out_of_order = make_config(tmp_path / "o", "ape", body_of(tuple(swapped)))
    assert section_structure_validation(out_of_order).errors == [
        "La sección 'Materiales, Reactivos, Equipos y Herramientas' está fuera del orden requerido por el "
        "formato APE en body.md"
    ]


def test_ape_annexes_stay_required(tmp_path):
    config = make_config(tmp_path, "ape", body_of(APE_FULL[:-1]))
    assert section_structure_validation(config).errors == [
        "Faltan secciones del formato APE en body.md: Anexos"
    ]


def test_ape_omit_sections_semantics_are_unchanged(tmp_path):
    without_questions = tuple(t for t in APE_FULL if t != "Preguntas de Control")
    ok = make_config(tmp_path / "ok", "ape", body_of(without_questions),
                     ape_omit_sections=["Preguntas de Control"])
    assert section_structure_validation(ok).errors == []

    unknown = make_config(tmp_path / "bad", "ape", body_of(without_questions),
                          ape_omit_sections=["Marco Teórico"])
    assert "ape_omit_sections: 'Marco Teórico' no es una sección del formato APE" in (
        section_structure_validation(unknown).errors
    )

    malformed = make_config(tmp_path / "mal", "ape", body_of(APE_FULL), ape_omit_sections="Resultados")
    assert section_structure_validation(malformed).errors == [
        "ape_omit_sections debe ser una lista de títulos de sección"
    ]


def test_ape_omit_fields_are_still_validated(tmp_path):
    config = make_config(tmp_path, "ape", body_of(APE_FULL), ape_omit_fields=["title"])
    assert "ape_omit_fields: 'title' no es un campo omitible del formato APE" in (
        section_structure_validation(config).errors
    )


def test_ape_keeps_its_check_name_and_message(tmp_path):
    folder = structure_folder(tmp_path, "ape", APE_FULL)
    check = structure_check(folder, "ape")
    assert check is not None and check["ok"]
    assert check["detail"] == "fixed APE headings present and in order"


def test_ape_omit_sections_does_not_leak_into_aa(tmp_path):
    """``ape_omit_sections`` belongs to APE: an AA report neither reads nor validates it."""
    config = make_config(tmp_path, "aa", body_of(AA_REQUIRED), ape_omit_sections=["Marco Teórico"])
    assert section_structure_validation(config).errors == []
