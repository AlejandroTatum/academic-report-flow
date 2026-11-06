"""Tests for the APE report template (new-report-flow T4).

`format: ape` renders a LaTeX replica of the teacher's Word template
"Actividad Práctico-Experimental Reporte técnico (estudiante)": no cover page,
a header with the faculty logo and "FEIRNNR - Carrera de Computación" on every
page, a generated identification table, eight fixed body sections and annexes
after the IEEE bibliography.

These tests pin:
  1. the template file, its placeholders and the teacher's layout facts;
  2. the faculty logo asset and its pipeline wiring;
  3. render_tex output: APE title, identification table (order + LaTeX
     escaping) and the annexes-after-bibliography mechanism;
  4. the APE body-heading structure check (present, in order; Anexos may be
     empty but must exist).
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
from report_config import ReportConfig  # noqa: E402
from validate_report import ape_structure_validation, metadata_validation  # noqa: E402

APE_TEMPLATE = ROOT / "templates" / "ape-report.tex"
APE_LOGO = ROOT / "assets" / "ape-faculty-logo.png"

# Placeholders the APE template must expose for the renderer to fill.
APE_PLACEHOLDERS = (
    "{{APE_TITLE}}",
    "{{APE_LOGO_PATH}}",
    "{{IDENTIFICATION_TABLE}}",
    "{{BODY}}",
    "{{BIB_FILE}}",
    "{{HAS_BIB}}",
    "{{PRINT_BIBLIOGRAPHY}}",
    "{{AFTER_BIBLIOGRAPHY}}",
    "{{FRONT_MATTER}}",
    "{{AI_DECLARATION}}",
)

# The identification table rows, in the teacher's order.
IDENTIFICATION_ROWS = (
    ("Nombre del estudiante(s)", "student"),
    ("Asignatura", "subject"),
    ("Ciclo", "cycle"),
    ("Unidad", "unit"),
    ("Resultado de aprendizaje de la unidad", "learning_outcome"),
    ("Práctica Nro.", "practice_number"),
    ("Tipo", "practice_type"),
    ("Título de la Práctica", "title"),
    ("Nombre del Docente", "teacher"),
    ("Fecha", "date"),
    ("Horario", "schedule"),
    ("Lugar", "place"),
    ("Tiempo planificado en el Sílabo", "planned_time"),
)

BASE_RAW = {
    "type": "technical_report",
    "backend": "latex",
    "output": "pdf",
    "pdf": "build/report.pdf",
    "body": "body.md",
    "format": "ape",
}


def full_ape_metadata() -> dict:
    return {
        "title": "Simulación de una fila de espera",
        "subject": "Simulación",
        "teacher": "Ing. Hernán Torres",
        "student": "Alejandro Padilla",
        "date": "7 de octubre de 2026",
        "cycle": "Quinto",
        "unit": "Unidad 2",
        "learning_outcome": "Modela sistemas de eventos discretos",
        "practice_number": "3",
        "practice_type": "Experimental",
        "schedule": "Viernes 08:00-10:00",
        "place": "Laboratorio 2",
        "planned_time": "4 horas",
    }


def make_render_config(
    tmp_path: Path,
    raw: dict | None = None,
    body: str | None = None,
    metadata: dict | None = None,
    with_format: bool = True,
) -> ReportConfig:
    folder = tmp_path / "r"
    folder.mkdir(parents=True, exist_ok=True)
    written = {key: value for key, value in BASE_RAW.items() if key != "format"}
    if with_format:
        written["format"] = "ape"
    written.update(raw or {})
    if metadata is not None:
        written["metadata"] = metadata
    (folder / "report.yml").write_text(yaml.safe_dump(written), encoding="utf-8")
    (folder / "body.md").write_text(
        body if body is not None else default_ape_body(), encoding="utf-8"
    )
    (folder / "sources.bib").write_text(SOURCE_BIB, encoding="utf-8")
    return ReportConfig.load(folder)


SOURCE_BIB = """@book{fuente2026,
  author = {Autor, Ana},
  title = {Fundamentos de simulación},
  publisher = {Editorial Universitaria},
  year = {2026},
}
"""


def default_ape_body() -> str:
    headings = (
        "Objetivo(s) de la Práctica",
        "Materiales, Reactivos, Equipos y Herramientas",
        "Procedimiento / Metodología Ejecutada",
        "Resultados",
        "Preguntas de Control",
        "Conclusiones",
        "Recomendaciones",
    )
    parts = [f"# {heading}\n\nContenido de {heading}.\n" for heading in headings]
    parts.append("# Anexos\n\nContenido de anexos.\n")
    # A citation so the IEEE bibliography actually prints (emission is
    # citation-driven, #26).
    parts.insert(1, "\nSegún la literatura [@fuente2026].\n")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# The template itself
# ---------------------------------------------------------------------------


def test_ape_template_exists() -> None:
    assert APE_TEMPLATE.is_file(), "templates/ape-report.tex must exist"


@pytest.fixture(scope="module")
def ape_template() -> str:
    return APE_TEMPLATE.read_text(encoding="utf-8")


@pytest.mark.parametrize("placeholder", APE_PLACEHOLDERS)
def test_ape_template_exposes_placeholder(ape_template: str, placeholder: str) -> None:
    assert placeholder in ape_template, f"ape template must expose {placeholder}"


@pytest.mark.parametrize("snippet", ["hyperref", "Needspace", "onehalfspacing", "parindent"])
def test_ape_template_satisfies_latex_validator(ape_template: str, snippet: str) -> None:
    assert snippet in ape_template, (
        f"validate_report.py greps the generated .tex for {snippet!r}"
    )


def test_ape_template_has_no_cover_page(ape_template: str) -> None:
    assert "titlepage" not in ape_template, "the teacher's template has no cover page"


def test_ape_template_renders_the_faculty_header(ape_template: str) -> None:
    assert "FEIRNNR - Carrera de Computación" in ape_template
    assert "fancyhdr" in ape_template, "the header repeats on every page"


def test_ape_template_uses_montserrat_with_a_sans_fallback(ape_template: str) -> None:
    """Body font is Montserrat 10.5pt, falling back when it is not installed."""
    assert r"\IfFontExistsTF{Montserrat}" in ape_template
    assert "TeX Gyre Heros" in ape_template, "documented sans fallback"
    assert "10.5" in ape_template


def test_ape_template_uses_play_or_the_same_fallback_for_the_title(ape_template: str) -> None:
    assert r"\IfFontExistsTF{Play}" in ape_template


def test_ape_template_heading_color_and_size(ape_template: str) -> None:
    assert "0F4761" in ape_template, "level-1 headings use the teacher's petrol blue"
    assert "14" in ape_template, "level-1 headings are 14pt"


def test_ape_template_keeps_ieee_citations(ape_template: str, tmp_path: Path) -> None:
    assert "{{BIBLATEX_OPTIONS}}" in ape_template, "the citation style is filled by the renderer"
    rendered = build_latex_report.render_tex(
        make_render_config(tmp_path, metadata=full_ape_metadata())
    )
    assert "style=ieee" in rendered, "every format cites IEEE by default"


def test_ape_render_hyphenates_with_spanish_patterns(tmp_path: Path) -> None:
    # Without a language package LuaLaTeX hyphenates Spanish with English
    # patterns ("it-eración", "parámet-ros").
    rendered = build_latex_report.render_tex(
        make_render_config(tmp_path, metadata=full_ape_metadata())
    )
    assert r"\usepackage[spanish,es-noshorthands,es-tabla]{babel}" in rendered


def test_ape_markdown_ai_declaration_renders_tables(tmp_path: Path) -> None:
    declaration = {
        "title": "Declaración de uso de IA Generativa",
        "format": "markdown",
        "text": "Herramientas:\n\n| Herramienta | Uso |\n|---|---|\n| Python | Pruebas |\n",
    }
    rendered = build_latex_report.render_tex(make_render_config(
        tmp_path,
        raw={"ai_declaration": declaration, "ai_declaration_position": "after_bibliography"},
        metadata=full_ape_metadata(),
    ))
    assert "Python & Pruebas" in rendered
    assert "| Python | Pruebas |" not in rendered


def test_trailing_backslash_is_a_hard_line_break() -> None:
    # CommonMark hard break: a bold question, then its answer on the next line.
    latex = build_latex_report.markdown_to_latex(
        "**1. ¿Qué es?**\\\nUna respuesta\ncontinuada.\n"
    )
    assert "\\textbf{1. ¿Qué es?}\\\\\nUna respuesta continuada." in latex
    assert "textbackslash" not in latex


def test_paragraph_without_trailing_backslash_still_joins_lines() -> None:
    latex = build_latex_report.markdown_to_latex("Una línea\ny otra.\n")
    assert "Una línea y otra." in latex


def test_ape_plain_ai_declaration_stays_inline_text(tmp_path: Path) -> None:
    text = "Uso de IA para *redactar* y revisar."
    rendered = build_latex_report.render_tex(make_render_config(
        tmp_path,
        raw={"ai_declaration": {"title": "Declaración", "text": text},
             "ai_declaration_position": "after_bibliography"},
        metadata=full_ape_metadata(),
    ))
    assert "\n" + build_latex_report.convert_inline(text) + "\n" in rendered


# ---------------------------------------------------------------------------
# The faculty logo asset
# ---------------------------------------------------------------------------


def test_ape_logo_asset_exists() -> None:
    assert APE_LOGO.is_file(), "the faculty logo extracted from the teacher's DOCX"
    assert APE_LOGO.stat().st_size > 1_000, "a real logo, not a placeholder"


def test_ape_logo_is_wired_into_the_pipeline() -> None:
    assert build_latex_report.APE_LOGO_FILENAME == APE_LOGO.name
    assert (build_latex_report.ASSETS_DIR / build_latex_report.APE_LOGO_FILENAME).exists()
    assert any(
        filename == build_latex_report.APE_LOGO_FILENAME
        for filename, _description in build_latex_report.EXPECTED_ASSETS
    )


def test_ape_template_alias_resolves_to_the_ape_template() -> None:
    assert build_latex_report.TEMPLATE_ALIASES["ape"] == APE_TEMPLATE
    assert build_latex_report.TEMPLATE_ALIASES["ape_report"] == APE_TEMPLATE


def test_ape_bibliography_title() -> None:
    assert build_latex_report.BIBLIOGRAPHY_TITLES["ape"] == "Bibliografía / Referencias"
    assert build_latex_report.BIBLIOGRAPHY_TITLES["ape_report"] == "Bibliografía / Referencias"


# ---------------------------------------------------------------------------
# render_tex output
# ---------------------------------------------------------------------------


def test_ape_render_prints_the_practice_title(tmp_path):
    config = make_render_config(tmp_path, metadata=full_ape_metadata())
    tex = build_latex_report.render_tex(config)
    assert "Reporte Técnico de Actividades Práctico-Experimentales Nro. 3" in tex


def test_ape_render_fills_the_logo_path(tmp_path):
    config = make_render_config(tmp_path, metadata=full_ape_metadata())
    tex = build_latex_report.render_tex(config)
    assert build_latex_report.APE_LOGO_FILENAME in tex


def test_ape_render_identification_table_rows_in_order(tmp_path):
    config = make_render_config(tmp_path, metadata=full_ape_metadata())
    tex = build_latex_report.render_tex(config)
    # Section 1 is generated by the template: heading first, then the table.
    datos = tex.index("Datos de Identificación del Estudiante y la Práctica")
    assert datos < tex.index(r"\section{Objetivo(s) de la Práctica}"), (
        "the generated identification section must be numbered before the body"
    )
    positions = [tex.index(label) for label, _key in IDENTIFICATION_ROWS]
    assert positions == sorted(positions), "the teacher's row order is fixed"
    # Every value lands on its label's row.
    for label, key in IDENTIFICATION_ROWS:
        row = tex[tex.index(label): tex.index(label) + 400]
        assert str(full_ape_metadata()[key]) in row, f"{key} must fill the '{label}' row"


def test_ape_render_identification_table_escapes_latex_specials(tmp_path):
    metadata = full_ape_metadata()
    metadata["student"] = "Ana & Beto_100%"
    metadata["place"] = "Lab #2 (norte)"
    config = make_render_config(tmp_path, metadata=metadata)
    tex = build_latex_report.render_tex(config)
    assert r"Ana \& Beto\_100\%" in tex
    assert r"Lab \#2 (norte)" in tex


def test_ape_render_annexes_move_after_the_bibliography(tmp_path):
    config = make_render_config(tmp_path, metadata=full_ape_metadata())
    tex = build_latex_report.render_tex(config)
    annexes = tex.index("Contenido de anexos")
    bibliography = tex.index("Bibliografía / Referencias")
    last_section = tex.index("Contenido de Recomendaciones")
    assert last_section < bibliography < annexes, (
        "Anexos must render after the IEEE bibliography"
    )


def test_ape_render_annexes_may_be_empty(tmp_path):
    body = default_ape_body().replace("Contenido de anexos.\n", "").rstrip() + "\n"
    config = make_render_config(tmp_path, body=body, metadata=full_ape_metadata())
    tex = build_latex_report.render_tex(config)
    bibliography = tex.index("Bibliografía / Referencias")
    assert tex.index("\\section{Anexos}", bibliography) > bibliography


def test_ape_render_without_annexes_heading_keeps_body_whole(tmp_path):
    """No `# Anexos` in body.md: nothing to relocate (the validator reports it)."""
    body = "# Único\n\nContenido.\n"
    config = make_render_config(tmp_path, body=body, metadata=full_ape_metadata())
    tex = build_latex_report.render_tex(config)
    assert "Contenido." in tex


def test_ape_render_is_validated_by_ape_headings(tmp_path):
    config = make_render_config(tmp_path, metadata=full_ape_metadata())
    result = metadata_validation(config)
    assert not [error for error in result.errors if "APE" in error]


# ---------------------------------------------------------------------------
# APE structure validation
# ---------------------------------------------------------------------------


def test_ape_missing_headings_are_reported(tmp_path):
    body = "# Objetivo(s) de la Práctica\n\nContenido.\n\n# Anexos\n"
    config = make_render_config(tmp_path, body=body, metadata=full_ape_metadata())
    result = ape_structure_validation(config)
    joined = "\n".join(result.errors)
    assert "Resultados" in joined and "Conclusiones" in joined


def test_ape_out_of_order_headings_are_reported(tmp_path):
    body = (
        "# Resultados\n\nr.\n\n# Objetivo(s) de la Práctica\n\no.\n\n"
        "# Anexos\n"
    )
    config = make_render_config(tmp_path, body=body, metadata=full_ape_metadata())
    result = ape_structure_validation(config)
    assert any("orden" in error.lower() for error in result.errors)


def test_ape_empty_annexes_pass(tmp_path):
    body = "\n".join(
        f"# {heading}\n\nContenido.\n"
        for heading in (
            "Objetivo(s) de la Práctica",
            "Materiales, Reactivos, Equipos y Herramientas",
            "Procedimiento / Metodología Ejecutada",
            "Resultados",
            "Preguntas de Control",
            "Conclusiones",
            "Recomendaciones",
            "Anexos",
        )
    )
    config = make_render_config(tmp_path, body=body, metadata=full_ape_metadata())
    assert ape_structure_validation(config).errors == []


def test_ape_headings_check_is_inert_without_the_ape_format(tmp_path):
    """`aa`, `libre` and reports without a format keep free section choice."""
    body = "# Lo que quiera el autor\n\nContenido.\n"
    for fmt in (None, "aa", "libre"):
        raw = {} if fmt is None else {"format": fmt}
        config = make_render_config(
            tmp_path / (fmt or "none"), raw=raw, body=body, with_format=False
        )
        assert config.format == fmt
        assert ape_structure_validation(config).errors == []


def test_ape_structure_validation_surfaces_through_metadata_validation(tmp_path):
    body = "# Objetivo(s) de la Práctica\n\nContenido.\n"
    config = make_render_config(tmp_path, body=body, metadata=full_ape_metadata())
    result = metadata_validation(config)
    assert any("Resultados" in error for error in result.errors)


# The teacher may drop a fixed APE section (e.g. no control questions).
_APE_WITHOUT_QUESTIONS = "\n".join(
    f"# {heading}\n\nContenido.\n"
    for heading in (
        "Objetivo(s) de la Práctica",
        "Materiales, Reactivos, Equipos y Herramientas",
        "Procedimiento / Metodología Ejecutada",
        "Resultados",
        "Conclusiones",
        "Recomendaciones",
        "Anexos",
    )
)


def test_ape_omitted_section_is_not_required(tmp_path):
    config = make_render_config(
        tmp_path, raw={"ape_omit_sections": ["Preguntas de Control"]},
        body=_APE_WITHOUT_QUESTIONS, metadata=full_ape_metadata(),
    )
    assert ape_structure_validation(config).errors == []


def test_ape_section_still_required_without_the_omission(tmp_path):
    config = make_render_config(tmp_path, body=_APE_WITHOUT_QUESTIONS, metadata=full_ape_metadata())
    assert ape_structure_validation(config).errors == [
        "Faltan secciones del formato APE en body.md: Preguntas de Control"
    ]


def test_ape_omission_of_an_unknown_section_is_an_error(tmp_path):
    config = make_render_config(
        tmp_path, raw={"ape_omit_sections": ["Marco Teórico"]},
        body=_APE_WITHOUT_QUESTIONS, metadata=full_ape_metadata(),
    )
    errors = ape_structure_validation(config).errors
    assert "ape_omit_sections: 'Marco Teórico' no es una sección del formato APE" in errors


def _ape_metadata_without(*keys: str) -> dict:
    return {key: value for key, value in full_ape_metadata().items() if key not in keys}


_OMITTED_FIELDS = ["learning_outcome", "schedule", "place", "planned_time"]


def test_ape_omitted_fields_drop_their_identification_rows(tmp_path):
    config = make_render_config(
        tmp_path, raw={"ape_omit_fields": _OMITTED_FIELDS},
        metadata=_ape_metadata_without(*_OMITTED_FIELDS),
    )
    tex = build_latex_report.render_tex(config)
    for label, key in IDENTIFICATION_ROWS:
        if key in _OMITTED_FIELDS:
            assert label not in tex, f"omitted '{key}' must not print its '{label}' row"
        else:
            assert label in tex, f"kept '{key}' must still print its '{label}' row"


def test_ape_omitted_fields_are_not_required_metadata(tmp_path):
    config = make_render_config(
        tmp_path, raw={"ape_omit_fields": _OMITTED_FIELDS},
        metadata=_ape_metadata_without(*_OMITTED_FIELDS),
    )
    required = config.format_required_metadata
    assert not set(_OMITTED_FIELDS) & set(required)
    assert "unit" in required and "title" in required


def test_ape_fields_stay_required_without_the_omission(tmp_path):
    config = make_render_config(tmp_path, metadata=full_ape_metadata())
    assert set(_OMITTED_FIELDS) <= set(config.format_required_metadata)


def test_ape_omission_of_a_core_or_unknown_field_is_an_error(tmp_path):
    config = make_render_config(
        tmp_path, raw={"ape_omit_fields": ["title", "color"]}, metadata=full_ape_metadata(),
    )
    errors = ape_structure_validation(config).errors
    assert "ape_omit_fields: 'title' no es un campo omitible del formato APE" in errors
    assert "ape_omit_fields: 'color' no es un campo omitible del formato APE" in errors


def test_ape_group_report_lists_every_member_in_the_student_row(tmp_path):
    members = ["Ana Pérez", "Luis Mora", "Alejandro Padilla"]
    config = make_render_config(
        tmp_path, metadata={**full_ape_metadata(), "practice_type": "Grupal", "members": members},
    )
    tex = build_latex_report.render_tex(config)
    row = tex[tex.index("Nombre del estudiante(s)"):].split(r"\\")[0]
    assert all(name in row for name in members), "a group report names every member"


def test_ape_individual_report_keeps_the_student_row(tmp_path):
    config = make_render_config(tmp_path, metadata=full_ape_metadata())
    tex = build_latex_report.render_tex(config)
    row = tex[tex.index("Nombre del estudiante(s)"):].split(r"\\")[0]
    assert "Alejandro Padilla" in row


def test_ape_title_override_replaces_the_fixed_heading(tmp_path):
    config = make_render_config(
        tmp_path, metadata={**full_ape_metadata(), "ape_title": "Síntesis ACD 1"},
    )
    tex = build_latex_report.render_tex(config)
    assert "Síntesis ACD 1" in tex
    assert "Reporte Técnico de Actividades Práctico-Experimentales" not in tex


def test_ape_title_defaults_to_the_fixed_heading(tmp_path):
    config = make_render_config(tmp_path, metadata=full_ape_metadata())
    tex = build_latex_report.render_tex(config)
    assert "Reporte Técnico de Actividades Práctico-Experimentales Nro. 3" in tex


def test_aa_group_report_names_every_member_on_the_cover(tmp_path):
    members = ["Ana Pérez", "Luis Mora", "Alejandro Padilla"]
    config = make_render_config(
        tmp_path, raw={"format": "aa"},
        metadata={**full_ape_metadata(), "members": members},
    )
    tex = build_latex_report.render_tex(config)
    assert "Ana Pérez, Luis Mora, Alejandro Padilla" in tex


def test_aa_individual_report_keeps_the_single_student_on_the_cover(tmp_path):
    config = make_render_config(tmp_path, raw={"format": "aa"}, metadata=full_ape_metadata())
    tex = build_latex_report.render_tex(config)
    assert "Alejandro Padilla" in tex


def test_aa_cover_label_is_plural_for_a_group(tmp_path):
    # The cover label belongs to the UNL cover; `format: aa` now renders the AA
    # template by default, so the cover is asked for explicitly.
    config = make_render_config(
        tmp_path, raw={"format": "aa", "template": "unl"},
        metadata={**full_ape_metadata(), "members": ["Ana Pérez", "Luis Mora"]},
    )
    tex = build_latex_report.render_tex(config)
    assert "AUTORES:" in tex and "AUTOR:}" not in tex


def test_aa_cover_label_stays_singular_for_one_student(tmp_path):
    config = make_render_config(
        tmp_path, raw={"format": "aa", "template": "unl"}, metadata=full_ape_metadata()
    )
    assert "AUTOR:}" in build_latex_report.render_tex(config)


def test_aa_template_ficha_label_is_plural_for_a_group(tmp_path):
    """The default AA template has no cover: the ficha carries the group label."""
    config = make_render_config(
        tmp_path, raw={"format": "aa"},
        metadata={**full_ape_metadata(), "members": ["Ana Pérez", "Luis Mora"]},
    )
    tex = build_latex_report.render_tex(config)
    assert r"\ficha{Estudiantes}" in tex and r"\ficha{Estudiante}" not in tex


def test_aa_template_ficha_label_stays_singular_for_one_student(tmp_path):
    config = make_render_config(tmp_path, raw={"format": "aa"}, metadata=full_ape_metadata())
    assert r"\ficha{Estudiante}" in build_latex_report.render_tex(config)


# ---------------------------------------------------------------------------
# S6 (aa-acd-templates): adding the AA and ACD templates leaves APE untouched
# ---------------------------------------------------------------------------

# sha256 of render_tex() for the fixed reports below, taken on the commit
# before templates/aa-report.tex existed. Any change to ape-report.tex, to the
# shared placeholder machinery or to the markdown converter as APE sees it
# shows up here. Re-pinned when babel (Spanish hyphenation) joined the preamble.
APE_RENDER_SHA256 = {
    "individual": "38a686cc182a1ead71519b8407b8064f070bbde43d11588dc03002c1a305f682",
    "group": "61465256d5d9dc5676192055c4ecf2e08572e802876c440daa6e7d082d3af891",
}


def test_ape_render_is_byte_identical_to_the_one_before_the_aa_template(tmp_path):
    import hashlib

    individual = build_latex_report.render_tex(
        make_render_config(tmp_path / "a", metadata=full_ape_metadata())
    )
    group = build_latex_report.render_tex(
        make_render_config(
            tmp_path / "b",
            metadata={**full_ape_metadata(), "members": ["Ana Pérez", "Luis Mora"]},
        )
    )
    assert hashlib.sha256(individual.encode()).hexdigest() == APE_RENDER_SHA256["individual"]
    assert hashlib.sha256(group.encode()).hexdigest() == APE_RENDER_SHA256["group"]


def test_ape_render_carries_no_aa_machinery(tmp_path):
    tex = build_latex_report.render_tex(make_render_config(tmp_path, metadata=full_ape_metadata()))
    for marker in (r"\ficha", "zoneclear", r"\parshape", "Source Serif 4"):
        assert marker not in tex


def test_ape_keeps_its_template_and_the_aa_default_does_not_leak(tmp_path):
    ape = make_render_config(tmp_path / "a", metadata=full_ape_metadata())
    assert build_latex_report.resolve_template(build_latex_report.template_key_for(ape)) == APE_TEMPLATE
    explicit = make_render_config(
        tmp_path / "b", raw={"format": "aa", "template": "ape"}, metadata=full_ape_metadata()
    )
    assert build_latex_report.resolve_template(build_latex_report.template_key_for(explicit)) == APE_TEMPLATE
