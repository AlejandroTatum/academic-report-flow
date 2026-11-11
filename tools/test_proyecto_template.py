"""Tests for the `format: proyecto` report variant (odd/tasks/project-format.md, T2).

A project report keeps the AA look (letterhead, typography, colours, numbered
green headings, booktabs tables) but is not an "Aprendizaje autónomo"
activity:

  S2. the large title reads "Proyecto", the eyebrow and the running header
      read "PROYECTO · <SUBJECT>", no AA label appears, the required metadata
      is title/subject/teacher/student/date and no section list is enforced;
      `format: aa` output is unchanged.
  S3. no sidebar: the identification data is a full-width table in the flow,
      under the title block and before the first section.
  S4. a heading is never separated from the start of its content, and a short
      table (up to 12 rows) is not split across pages.

Every assertion reads the rendered .tex through ``render_tex``, the same
public render path the AA tests use; no TeX engine is needed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import build_latex_report  # noqa: E402
from report_config import FORMAT_REQUIRED_METADATA, ReportConfig  # noqa: E402
from validate_report import metadata_validation, section_structure_validation  # noqa: E402

PROYECTO_TEMPLATE = ROOT / "templates" / "proyecto-report.tex"


@pytest.fixture(autouse=True)
def _never_publish_outside_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Same guard as test_aa_template: a build here only publishes under tmp."""
    import importlib

    sandbox = tmp_path_factory.mktemp("global-outputs")
    for name in ("output_router", "report_config", "build_latex_report", "validate_report"):
        module = importlib.import_module(name)
        if hasattr(module, "GLOBAL_OUTPUTS"):
            monkeypatch.setattr(module, "GLOBAL_OUTPUTS", sandbox)
    return sandbox


SOURCE_BIB = """@book{fuente2026,
  author = {Autor, Ana},
  title = {Sistemas embebidos},
  publisher = {Editorial Universitaria},
  year = {2026},
}
"""


def required_metadata() -> dict:
    return {
        "title": "Jarvis: asistente de voz con ESP32",
        "subject": "Sistemas Digitales",
        "teacher": "Ing. Luis Cueva",
        "student": "Camila Jaramillo",
        "date": "11 de noviembre de 2026",
    }


def full_metadata() -> dict:
    """Every field, including the AA-only ones a project must never print."""
    return {
        **required_metadata(),
        "cycle": "Cuarto",
        "parallel": "A",
        "unit": "Unidad 2: Microcontroladores",
        "learning_outcome": "Diseña sistemas embebidos.",
        "practice_number": "2",
        "planned_time": "4 horas",
    }


PRESUPUESTO_TABLE = (
    "| Componente | Cantidad | Costo |\n"
    "|---|---|---|\n"
    "| ESP32 | 1 | 10 |\n"
    "| Micrófono | 1 | 5 |\n"
    "| Parlante | 1 | 4 |\n"
    "| Total | 3 | 19 |\n"
)


def project_body() -> str:
    return (
        "# Tema\n\nUn asistente de voz con ESP32 [@fuente2026].\n\n"
        "# Alcance\n\nReconoce comandos simples.\n\n"
        "# Presupuesto\n\n" + PRESUPUESTO_TABLE + "\nEl total cabe en el presupuesto.\n"
    )


def make_config(
    tmp_path: Path, *, fmt: str = "proyecto", metadata: dict | None = None, body: str | None = None
) -> ReportConfig:
    folder = tmp_path / "r"
    folder.mkdir(parents=True, exist_ok=True)
    raw = {
        "type": "technical_report",
        "route": "academic",
        "backend": "latex",
        "output": "pdf",
        "pdf": "build/report.pdf",
        "body": "body.md",
        "format": fmt,
        "metadata": metadata if metadata is not None else full_metadata(),
    }
    (folder / "report.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    (folder / "body.md").write_text(body if body is not None else project_body(), encoding="utf-8")
    (folder / "sources.bib").write_text(SOURCE_BIB, encoding="utf-8")
    return ReportConfig.load(folder)


def render(tmp_path: Path, **kwargs) -> str:
    return build_latex_report.render_tex(make_config(tmp_path, **kwargs))


def document_body(tex: str) -> str:
    """The typeset part of the .tex: comments stripped, from \\begin{document} on."""
    start = tex.index(r"\begin{document}")
    lines = [line.split("%")[0] if not line.lstrip().startswith(r"\%") else line for line in tex[start:].splitlines()]
    return "\n".join(lines)


def datos_table(tex: str) -> str:
    """The identification table block the renderer writes under the title."""
    start = tex.index("% Datos del proyecto")
    end = tex.index(r"\end{tabularx}", start)
    return tex[start:end]


# ---------------------------------------------------------------------------
# S2: the AA look, but a project
# ---------------------------------------------------------------------------


def test_s2_proyecto_selects_its_own_template(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    key = build_latex_report.template_key_for(config)
    assert build_latex_report.resolve_template(build_latex_report.normalize_template_key(key)) == PROYECTO_TEMPLATE


def test_s2_large_title_is_proyecto_and_subtitle_is_the_title(tmp_path: Path) -> None:
    tex = render(tmp_path)
    assert r"\selectfont Proyecto\par" in tex
    assert r"\itshape\fontsize{14}{18}\selectfont\color{muted}Jarvis: asistente de voz con ESP32\par" in tex


def test_s2_eyebrow_and_running_header_read_proyecto_and_subject(tmp_path: Path) -> None:
    tex = render(tmp_path)
    eyebrow = r"\spaced{PROYECTO\ \,·\ \,\MakeUppercase{Sistemas Digitales}}"
    assert eyebrow in document_body(tex), "eyebrow under the letterhead"
    header = next(line for line in tex.splitlines() if line.startswith(r"\fancyhead["))
    assert r"\MakeUppercase{Proyecto}\ \,·\,\ \MakeUppercase{Sistemas Digitales}" in header


def test_s2_no_aa_label_appears_anywhere(tmp_path: Path) -> None:
    tex = render(tmp_path)
    for forbidden in ("AA-", "ACTIVIDAD", "Actividad", "Aprendizaje autónomo", "Aprendizaje Autónomo"):
        assert forbidden not in tex, f"{forbidden!r} leaked into a project report"


def test_s2_keeps_the_aa_look(tmp_path: Path) -> None:
    tex = render(tmp_path)
    for snippet in ("Source Serif 4", "Source Sans 3", "1F4E3D", "Universidad Nacional de Loja", "Carrera de Computación"):
        assert snippet in tex, f"AA look element {snippet!r} missing"
    assert r"\includegraphics[width=4.4cm]" in tex, "UNL logo in the letterhead"
    assert r"\titleformat{\section}{\sffamily\fontsize{13.5}{16}\selectfont\bfseries\color{accent}}{\thesection}" in tex
    assert r"\toprule" in tex and r"\reporttablehead{Componente}" in tex, "AA booktabs table style"


def test_s2_required_metadata_without_cycle_or_parallel(tmp_path: Path) -> None:
    assert FORMAT_REQUIRED_METADATA["proyecto"] == ("title", "subject", "teacher", "student", "date")
    result = metadata_validation(make_config(tmp_path, metadata=required_metadata()))
    assert not [error for error in result.errors if "proyecto" in error], result.errors


def test_s2_missing_required_metadata_is_reported(tmp_path: Path) -> None:
    metadata = required_metadata()
    del metadata["teacher"]
    result = metadata_validation(make_config(tmp_path, metadata=metadata))
    assert any("formato 'proyecto'" in error and "teacher" in error for error in result.errors), result.errors


def test_s2_no_section_list_is_enforced(tmp_path: Path) -> None:
    config = make_config(tmp_path, body="# Tema\n\nTexto.\n\n# Presupuesto\n\nTexto.\n")
    assert section_structure_validation(config).errors == []


def test_s2_aa_still_renders_its_sidebar_ficha_and_title(tmp_path: Path) -> None:
    tex = render(tmp_path, fmt="aa")
    assert "Datos de identificación" in tex and r"\ficha{Asignatura}{Sistemas Digitales}" in tex
    assert r"\usebox{\fichabox}" in tex, "the ficha hangs in the left margin"
    assert r"\selectfont Aprendizaje autónomo\par" in tex
    assert "ACTIVIDAD AA-2" in tex


# ---------------------------------------------------------------------------
# S3: no sidebar, a normal identification table
# ---------------------------------------------------------------------------


def test_s3_no_sidebar_and_full_width_body(tmp_path: Path) -> None:
    tex = render(tmp_path)
    for sidebar in (r"\ficha", "fichabox", "zoneX", r"\parshape", "Datos de identificación"):
        assert sidebar not in tex, f"sidebar machinery {sidebar!r} in a project report"


def test_s3_table_sits_under_the_title_and_before_the_first_section(tmp_path: Path) -> None:
    tex = render(tmp_path)
    table = tex.index("% Datos del proyecto")
    assert tex.index(r"\selectfont Proyecto\par") < table < tex.index(r"\section{Tema}")
    assert r"\begin{tabularx}{\textwidth}" in datos_table(tex), "full text width"


def test_s3_rows_in_order(tmp_path: Path) -> None:
    table = datos_table(render(tmp_path))
    expected = (
        ("Integrantes", "Camila Jaramillo"),
        ("Asignatura", "Sistemas Digitales"),
        ("Ciclo", "Cuarto, paralelo A"),
        ("Docente", "Ing. Luis Cueva"),
        ("Fecha de entrega", "11 de noviembre de 2026"),
    )
    positions = []
    for label, value in expected:
        row = rf"\proyectodato{{{label}}} & {value} \\"
        assert row in table, f"missing row {row!r}"
        positions.append(table.index(row))
    assert positions == sorted(positions)
    for absent in ("Unidad", "Resultado de aprendizaje", "Actividad", "sílabo"):
        assert absent not in table


def test_s3_absent_values_omit_their_rows(tmp_path: Path) -> None:
    metadata = required_metadata()
    del metadata["date"]
    table = datos_table(render(tmp_path, metadata=metadata))
    assert "Ciclo" not in table and "Fecha de entrega" not in table
    # The parallel defaults to "A" (report_config), so a cycle alone still
    # reads "<cycle>, paralelo A", exactly like the AA ficha.
    metadata = {**required_metadata(), "cycle": "Cuarto", "parallel": "B"}
    table = datos_table(render(tmp_path / "b", metadata=metadata))
    assert r"\proyectodato{Ciclo} & Cuarto, paralelo B \\" in table


def test_s3_group_members_are_listed_as_integrantes(tmp_path: Path) -> None:
    metadata = {**required_metadata(), "members": ["Ana Pérez", "Luis Mora", "Eva_Ríos"]}
    table = datos_table(render(tmp_path, metadata=metadata))
    assert r"\proyectodato{Integrantes} & Ana Pérez\newline Luis Mora\newline Eva\_Ríos \\" in table


# ---------------------------------------------------------------------------
# S4: headings stay with their content, short tables are not split
# ---------------------------------------------------------------------------


def _between(tex: str, start: str, end: str) -> str:
    head = tex.index(start)
    return tex[head: tex.index(end, head)]


def test_s4_heading_is_kept_with_the_table_that_follows(tmp_path: Path) -> None:
    tex = render(tmp_path)
    gap = _between(tex, r"\section{Presupuesto}", r"\begin{tabularx}")
    assert r"\Needspace" not in gap, "a look-ahead after the heading can strand it at the page foot"
    assert r"\nopagebreak" in gap


def test_s4_heading_is_kept_with_a_caption_and_its_table(tmp_path: Path) -> None:
    body = "# Presupuesto\n\nTabla 1. Costos del prototipo.\n\n" + PRESUPUESTO_TABLE
    tex = render(tmp_path, body=body)
    gap = _between(tex, r"\section{Presupuesto}", r"\begin{tabularx}")
    assert r"\Needspace" not in gap and gap.count(r"\nopagebreak") == 2


def test_s4_template_forbids_club_and_widow_lines(tmp_path: Path) -> None:
    tex = render(tmp_path)
    assert r"\clubpenalty=10000" in tex and r"\widowpenalty=10000" in tex


def test_s4_short_table_is_one_unbreakable_block(tmp_path: Path) -> None:
    rows = "".join(f"| Item {n} | {n} |\n" for n in range(12))
    tex = render(tmp_path, body="# Lista\n\nTexto.\n\n| Ítem | Costo |\n|---|---|\n" + rows)
    body = tex[tex.index(r"\section{Lista}"):]
    assert r"\begin{tabularx}" in body and "xltabular" not in body


def test_s4_long_table_may_still_break(tmp_path: Path) -> None:
    rows = "".join(f"| Item {n} | {n} |\n" for n in range(13))
    tex = render(tmp_path, body="# Lista\n\n| Ítem | Costo |\n|---|---|\n" + rows)
    body = tex[tex.index(r"\section{Lista}"):]
    assert r"\begin{xltabular}" in body
    assert r"\Needspace" not in _between(body, r"\section{Lista}", r"\begin{xltabular}")


def test_s4_aa_tables_and_headings_are_unchanged(tmp_path: Path) -> None:
    tex = render(tmp_path, fmt="aa")
    gap = _between(tex, r"\section{Presupuesto}", r"\begin{xltabular}")
    assert r"\Needspace{4\baselineskip}" in gap and r"\nopagebreak" not in gap


# ---------------------------------------------------------------------------
# S5: title block, letterhead and running header are centred
# ---------------------------------------------------------------------------


def _title_block(tex: str) -> str:
    start = tex.index(r"\vspace*{\letterheaddrop}")
    return tex[start: tex.index(r"\endgroup", start)]


def test_s5_title_block_is_centred(tmp_path: Path) -> None:
    block = _title_block(render(tmp_path))
    assert r"\centering" in block and r"\raggedright" not in block
    assert block.index(r"\centering") < block.index("PROYECTO"), "the eyebrow is centred too"


def test_s5_letterhead_is_one_centred_group(tmp_path: Path) -> None:
    tex = render(tmp_path)
    letterhead = tex[tex.index(r"\AddToShipoutPictureBG*"): tex.index(r"\vspace*{\letterheaddrop}")]
    assert letterhead.count(r"\put(") == 1, "logo and institution lines are placed as one group"
    assert r"\put(\LenToUnit{0.5\paperwidth}" in letterhead and r"\makebox(0,0)[t]{" in letterhead
    assert r"\includegraphics" in letterhead and "Universidad Nacional de Loja" in letterhead


def test_s5_running_header_is_centred(tmp_path: Path) -> None:
    tex = render(tmp_path)
    assert r"\fancyhead[L]" not in tex
    header = next(line for line in tex.splitlines() if line.startswith(r"\fancyhead[C]"))
    assert r"\MakeUppercase{Sistemas Digitales}" in header and r"\hfill" not in header


# ---------------------------------------------------------------------------
# S6: compact identification table, emphasised data tables
# ---------------------------------------------------------------------------


def test_s6_label_starts_horizontal_mode(tmp_path: Path) -> None:
    tex = render(tmp_path)
    assert r"\newcommand{\proyectodato}[1]{\leavevmode" in tex, "label on the baseline of its value"


def test_s6_identification_table_is_compact(tmp_path: Path) -> None:
    table = datos_table(render(tmp_path))
    assert r"\begin{tabularx}{\textwidth}{@{}l" in table, "label column only as wide as its longest label"
    assert "p{3.6cm}" not in table
    assert r"\renewcommand{\arraystretch}{1}" in table, "rows only as tall as the text"


BUDGET = (
    "# Presupuesto\n\n"
    "| Componente | Cantidad | Precio (USD) | Subtotal (USD) |\n"
    "|---|---|---:|---:|\n"
    "| ESP32 | 1 | 10,00 | 10,00 |\n"
    "| Micrófono | 2 | $5.50 | 11,00 |\n"
    "| **Total** | | | **21,00** |\n"
)


def _budget(tex: str) -> str:
    start = tex.index(r"\section{Presupuesto}")
    return tex[start: tex.index(r"\end{tabularx}", start)]


def test_s6_data_table_header_row_is_tinted(tmp_path: Path) -> None:
    table = _budget(render(tmp_path, body=BUDGET))
    lines = table.splitlines()
    head = next(n for n, line in enumerate(lines) if r"\reporttablehead{Componente}" in line)
    assert lines[head - 1].strip() == r"\rowcolor{wash}", "light tint behind the header row"
    assert "|" not in next(line for line in lines if line.startswith(r"\begin{tabularx}")), "no vertical rules"


def test_s6_numeric_columns_are_right_aligned(tmp_path: Path) -> None:
    table = _budget(render(tmp_path, body=BUDGET))
    spec = next(line for line in table.splitlines() if line.startswith(r"\begin{tabularx}"))
    # Cantidad has no `---:` marker: a column of numbers is detected. Numeric
    # columns are natural-width `r` columns (S8a), the text column an X.
    assert spec.endswith("{>{\\hsize=1\\hsize\\raggedright\\arraybackslash}X r r r}"), spec
    assert r"\centering" not in spec


def test_s6_total_row_is_bold_under_a_rule(tmp_path: Path) -> None:
    table = _budget(render(tmp_path, body=BUDGET))
    lines = table.splitlines()
    total = next(n for n, line in enumerate(lines) if "Total" in line)
    assert lines[total - 1].strip() == r"\midrule", "a rule above the total row"
    cells = [cell.strip() for cell in lines[total].removesuffix(r"\\").split("&")]
    assert all(cell.startswith(r"\textbf{") for cell in cells), cells


def test_s6_rows_without_total_get_no_total_rule(tmp_path: Path) -> None:
    table = _budget(render(tmp_path, body=BUDGET.replace("**Total**", "Otro")))
    assert table.count(r"\midrule") == 1, "only the rule under the header"


def test_s6_data_rows_are_comfortably_spaced(tmp_path: Path) -> None:
    table = _budget(render(tmp_path, body=BUDGET))
    assert r"\renewcommand{\arraystretch}{1.35}" in table


def test_s6_aa_tables_are_unchanged(tmp_path: Path) -> None:
    tex = render(tmp_path, fmt="aa", body=BUDGET)
    start = tex.index(r"\section{Presupuesto}")
    table = tex[start: tex.index(r"\end{xltabular}", start)]
    assert r"\rowcolor" not in table and r"\renewcommand{\arraystretch}{1.2}" in table
    assert table.count(r"\midrule") == 1 and r"\centering" in table


# ---------------------------------------------------------------------------
# S7: one heading style family
# ---------------------------------------------------------------------------


def test_s7_every_heading_level_uses_the_section_style(tmp_path: Path) -> None:
    tex = render(tmp_path)
    for level, number in (("section", r"\thesection"), ("subsection", r"\thesubsection"), ("subsubsection", r"\thesubsubsection")):
        line = next(line for line in tex.splitlines() if line.startswith(rf"\titleformat{{\{level}}}"))
        assert r"\sffamily" in line and r"\bfseries" in line and r"\color{accent}" in line, line
        assert r"\itshape" not in line and r"\normalfont" not in line, line
        assert f"}}{{{number}}}{{" in line, f"{level}: number in the heading face, not restyled"


def test_s6_header_tint_stays_inside_the_rules(tmp_path: Path) -> None:
    """colortbl paints \\tabcolsep beyond each cell: with `@{}` edges the tint
    would stick out past the rules, so tinted tables keep their edge padding."""
    table = _budget(render(tmp_path, body=BUDGET))
    spec = next(line for line in table.splitlines() if line.startswith(r"\begin{tabularx}"))
    assert "@{}" not in spec, spec



# ---------------------------------------------------------------------------
# S8: numeric headers, table captions, long-form date
# ---------------------------------------------------------------------------

STORE_BUDGET = (
    "# Presupuesto\n\n"
    "Tabla 2. Componentes obligatorios\n\n"
    "| Componente | Tienda | Cant. | Precio unitario (USD) | Subtotal (USD) |\n"
    "|---|---|---:|---:|---:|\n"
    "| ESP32-S3 DevKit N16R8, 16 MB de flash y 8 MB de PSRAM | bmlogics, Loja | 1 | 15,25 | 15,25 |\n"
    "| Micrófono INMP441 I2S | bmlogics, Loja | 1 | 6,90 | 6,90 |\n"
    "| **Total obligatorio** | | | | **22,15** |\n"
)


def _spec(table: str) -> str:
    return next(line for line in table.splitlines() if line.startswith(r"\begin{tabularx}"))


def test_s8a_numeric_columns_fit_their_header_and_text_columns_give_up_the_width(tmp_path: Path) -> None:
    table = _budget(render(tmp_path, body=STORE_BUDGET))
    spec = _spec(table)
    # Natural-width numeric columns can never hyphenate; the two text columns
    # share the rest of the line (their \hsize factors add up to 2).
    assert spec.endswith("X r r r}"), spec
    weights = [float(w) for w in re.findall(r"\\hsize=([\d.]+)\\hsize", spec)]
    assert len(weights) == 2 and abs(sum(weights) - 2) < 1e-6, weights
    header = next(line for line in table.splitlines() if r"\reporttablehead{Componente}" in line)
    # A header breaks only at a space: a trailing unit goes under the words.
    # Its lines are set at normal spacing, not the table's opened-up rows.
    stack = r"{\renewcommand{\arraystretch}{1}\begin{tabular}[t]{@{}r@{}}"
    assert r"\reporttablehead{" + stack + r"Precio unitario\\(USD)\end{tabular}}}" in header
    assert r"\reporttablehead{" + stack + r"Subtotal\\(USD)\end{tabular}}}" in header
    assert r"\reporttablehead{Cant.}" in header


def test_s8b_table_caption_line_is_a_caption_tied_to_its_table(tmp_path: Path) -> None:
    tex = render(tmp_path, body=STORE_BUDGET)
    # Space above (it is not part of the paragraph before it), none indent.
    assert r"\newcommand{\proyectotablecaption}[2]{\par\medskip\noindent{\sffamily" in tex
    gap = _between(tex, r"\section{Presupuesto}", r"\begin{tabularx}")
    assert r"\proyectotablecaption{Tabla 2.}{Componentes obligatorios}" in gap
    after = gap[gap.index(r"\proyectotablecaption"):]
    assert r"\nopagebreak" in after and r"\Needspace" not in gap
    assert "\nTabla 2. Componentes obligatorios\n" not in tex, "no longer a body paragraph"


def test_s8b_a_tabla_line_without_a_table_stays_a_paragraph(tmp_path: Path) -> None:
    tex = render(tmp_path, body="# Notas\n\nTabla 3. Ver anexo.\n\nOtro texto.\n")
    assert r"\proyectotablecaption{" not in tex.split(r"\begin{document}")[1]
    assert "Tabla 3. Ver anexo." in tex


def test_s8c_iso_date_prints_in_spanish_long_form(tmp_path: Path) -> None:
    table = datos_table(render(tmp_path, metadata={**required_metadata(), "date": "2026-11-11"}))
    assert r"\proyectodato{Fecha de entrega} & 11 de noviembre de 2026 \\" in table


def test_s8c_yaml_date_and_free_text_dates(tmp_path: Path) -> None:
    import datetime

    table = datos_table(render(tmp_path, metadata={**required_metadata(), "date": datetime.date(2026, 3, 5)}))
    assert r"\proyectodato{Fecha de entrega} & 5 de marzo de 2026 \\" in table
    for n, written in enumerate(("Noviembre de 2026", "2026-13-40")):
        table = datos_table(render(tmp_path / str(n), metadata={**required_metadata(), "date": written}))
        assert rf"\proyectodato{{Fecha de entrega}} & {written} \\" in table, "other text unchanged"
