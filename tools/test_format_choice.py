"""Tests for the `format:` choice in report.yml (new-report-flow T4).

After content approval the user picks exactly one format per document:
``ape`` (the teacher's Word replica), ``aa`` (the current academic route,
unchanged) or ``libre`` (a user-specified format with a required
``format_spec:`` description). Every format keeps IEEE citations and always
builds a PDF through the existing LaTeX pipeline.

These tests pin:
  1. format parsing (case-insensitive; absent = not chosen yet, still valid);
  2. an unknown value fails loudly, like an unknown route;
  3. per-format required metadata, with placeholder values ("X", "XXX",
     "00X", "[...]") counting as missing for the APE fields;
  4. template mapping: ape -> ape-report.tex, aa -> aa-report.tex,
     acd -> acd-report.tex, libre -> plain-report.tex, an explicit
     `template:` key always wins.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import build_latex_report  # noqa: E402
import report_config  # noqa: E402
from report_config import (  # noqa: E402
    DEFAULT_FORMAT,
    FORMAT_REQUIRED_METADATA,
    ReportConfig,
    load_report_config,
    read_yaml,
    unknown_format_message,
)
from validate_report import metadata_validation  # noqa: E402

APE_TEMPLATE = ROOT / "templates" / "ape-report.tex"
UNL_TEMPLATE = ROOT / "templates" / "unl-report.tex"
AA_TEMPLATE = ROOT / "templates" / "aa-report.tex"
ACD_TEMPLATE = ROOT / "templates" / "acd-report.tex"
PLAIN_TEMPLATE = ROOT / "templates" / "plain-report.tex"

BASE_RAW = {
    "type": "technical_report",
    "backend": "latex",
    "output": "pdf",
    "pdf": "build/report.pdf",
    "body": "body.md",
}


def make_config(tmp_path: Path, raw: dict, metadata: dict | None = None) -> ReportConfig:
    folder = tmp_path / "r"
    folder.mkdir(parents=True, exist_ok=True)
    written = dict(BASE_RAW)
    written.update(raw)
    if metadata is not None:
        written["metadata"] = metadata
    (folder / "report.yml").write_text(yaml.safe_dump(written), encoding="utf-8")
    (folder / "body.md").write_text("# Contenido\n\nCuerpo.\n", encoding="utf-8")
    return ReportConfig.load(folder)


def make_config_unloaded(tmp_path: Path, raw: dict) -> ReportConfig:
    """A ReportConfig without load_report_config's loud unknown-format guard,
    for testing the property/validation behavior underneath the guard."""
    folder = tmp_path / "raw"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "report.yml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    (folder / "body.md").write_text("# Contenido\n\nCuerpo.\n", encoding="utf-8")
    return ReportConfig(folder=folder, raw=raw, academic_format=read_yaml(DEFAULT_FORMAT))


def format_metadata_errors(result) -> list[str]:
    """The format-specific metadata errors, excluding the body-structure
    findings a stub body.md always carries for `format: ape`."""
    return [
        error
        for error in result.errors
        if error.startswith("Metadata incompleta para el formato")
    ]


def rendered_template_name(config: ReportConfig) -> str:
    return build_latex_report.resolve_template(
        build_latex_report.template_key_for(config)
    ).name


def full_ape_metadata() -> dict:
    return {
        "title": "Simulación de una fila de espera",
        "subject": "Simulación",
        "teacher": "Ing. Docente",
        "student": "Estudiante Ejemplo",
        "date": "2026-10-01",
        "cycle": "Quinto",
        "unit": "Unidad 2",
        "learning_outcome": "Modela sistemas discretos",
        "practice_number": "3",
        "practice_type": "Experimental",
        "schedule": "Viernes 08:00-10:00",
        "place": "Laboratorio 2",
        "planned_time": "4 horas",
    }


# ---------------------------------------------------------------------------
# Format parsing
# ---------------------------------------------------------------------------


def test_absent_format_means_not_chosen_yet(tmp_path):
    """No `format:` key is a valid state: the flow is content-first."""
    config = make_config(tmp_path, {})
    assert config.format is None
    assert config.format_is_known is False


@pytest.mark.parametrize("written, expected", [
    ("ape", "ape"),
    ("AA", "aa"),
    ("  Libre ", "libre"),
])
def test_format_is_case_insensitive_and_trimmed(tmp_path, written, expected):
    config = make_config(tmp_path, {"format": written})
    assert config.format == expected
    assert config.format_is_known is True


def test_optional_format_hint_is_validated_without_choosing_format(tmp_path):
    config = ReportConfig(tmp_path, {"format_hint": "APE"})
    assert config.format is None
    assert config.format_hint == "ape"
    assert config.format_hint_is_known
    assert not ReportConfig(tmp_path, {"format_hint": "unknown"}).format_hint_is_known


def test_unknown_format_fails_loudly_on_load(tmp_path):
    """A typo must not silently pick a format, like an unknown route."""
    folder = tmp_path / "r"
    folder.mkdir(parents=True)
    raw = dict(BASE_RAW)
    raw["format"] = "revista"
    (folder / "report.yml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    (folder / "body.md").write_text("# x\n", encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        load_report_config(folder)
    assert "revista" in str(excinfo.value)
    assert unknown_format_message("revista") in str(excinfo.value)


def test_unknown_format_fails_required_metadata(tmp_path):
    config = make_config_unloaded(tmp_path, {**BASE_RAW, "format": "revista"})
    with pytest.raises(ValueError) as excinfo:
        _ = config.format_required_metadata
    assert "revista" in str(excinfo.value)


def test_unknown_format_is_a_metadata_error(tmp_path):
    config = make_config_unloaded(tmp_path, {**BASE_RAW, "format": "revista"})
    result = metadata_validation(config)
    assert any("revista" in error for error in result.errors)


# ---------------------------------------------------------------------------
# Per-format required metadata
# ---------------------------------------------------------------------------


def test_aa_requires_the_current_academic_metadata():
    assert FORMAT_REQUIRED_METADATA["aa"] == ("title", "subject", "teacher", "student", "date")


def test_ape_extends_aa_with_the_identification_fields():
    assert FORMAT_REQUIRED_METADATA["ape"] == (
        "title", "subject", "teacher", "student", "date",
        "cycle", "unit", "learning_outcome", "practice_number",
        "practice_type", "schedule", "place", "planned_time",
    )


def test_libre_requires_the_universal_metadata():
    assert FORMAT_REQUIRED_METADATA["libre"] == ("title", "student", "date")


def test_ape_metadata_completes_with_no_error(tmp_path):
    result = metadata_validation(make_config(tmp_path, {"format": "ape"}, full_ape_metadata()))
    assert format_metadata_errors(result) == []


def test_ape_missing_fields_are_reported(tmp_path):
    metadata = full_ape_metadata()
    del metadata["cycle"], metadata["place"]
    result = metadata_validation(make_config(tmp_path, {"format": "ape"}, metadata))
    assert any("cycle" in error and "place" in error for error in format_metadata_errors(result))


@pytest.mark.parametrize("field, value", [
    ("cycle", "X"),
    ("unit", "XXX"),
    ("practice_number", "00X"),
    ("learning_outcome", "[Resultado de aprendizaje]"),
])
def test_ape_placeholder_values_count_as_missing(tmp_path, field, value):
    metadata = full_ape_metadata()
    metadata[field] = value
    result = metadata_validation(make_config(tmp_path, {"format": "ape"}, metadata))
    assert any(
        field in error for error in format_metadata_errors(result)
    ), (
        f"placeholder value {value!r} in {field} must count as missing"
    )


def test_libre_requires_a_non_empty_format_spec(tmp_path):
    metadata = {"title": "T", "student": "S", "date": "2026"}
    result = metadata_validation(make_config(tmp_path, {"format": "libre"}, metadata))
    assert any("format_spec" in error for error in result.errors)

    result = metadata_validation(make_config(
        tmp_path, {"format": "libre", "format_spec": "Dos columnas, Arial 11"}, metadata
    ))
    assert not [error for error in result.errors if "format_spec" in error]

def test_spanish_aliases_resolve_to_the_canonical_ape_fields(tmp_path):
    metadata = {
        "titulo": "Título",
        "asignatura": "Simulación",
        "docente": "Ing. Docente",
        "estudiante": "Estudiante",
        "fecha": "2026-10-01",
        "ciclo": "Quinto",
        "unidad": "Unidad 2",
        "resultado_de_aprendizaje": "Modela sistemas discretos",
        "practica_nro": "3",
        "tipo_practica": "Experimental",
        "horario": "Viernes 08:00",
        "lugar": "Laboratorio 2",
        "tiempo_planificado": "4 horas",
    }
    config = make_config(tmp_path, {"format": "ape"}, metadata)
    assert config.format_required_metadata == FORMAT_REQUIRED_METADATA["ape"]
    result = metadata_validation(config)
    assert not [error for error in result.errors if "formato 'ape'" in error]


# ---------------------------------------------------------------------------
# Template mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fmt, template_name", [
    ("ape", APE_TEMPLATE.name),
    ("aa", AA_TEMPLATE.name),
    ("acd", ACD_TEMPLATE.name),
    ("libre", PLAIN_TEMPLATE.name),
])
def test_format_maps_to_its_template(tmp_path, fmt, template_name):
    assert rendered_template_name(make_config(tmp_path, {"format": fmt})) == template_name


def test_format_overrides_the_route_template_default(tmp_path):
    """`aa` on a non-academic route still gets its own template."""
    config = make_config(tmp_path, {"route": "technical", "format": "aa"})
    assert rendered_template_name(config) == AA_TEMPLATE.name


def test_explicit_unl_template_still_wins_for_aa(tmp_path):
    """The old AA look stays reachable with an explicit `template: unl`."""
    config = make_config(tmp_path, {"format": "aa", "template": "unl"})
    assert rendered_template_name(config) == UNL_TEMPLATE.name


def test_explicit_template_beats_the_format_default(tmp_path):
    """libre's template is a default: an explicit `template:` key may override."""
    config = make_config(tmp_path, {"format": "libre", "template": "unl"})
    assert rendered_template_name(config) == UNL_TEMPLATE.name
    config = make_config(tmp_path, {"format": "ape", "template": "plain"})
    assert rendered_template_name(config) == PLAIN_TEMPLATE.name
