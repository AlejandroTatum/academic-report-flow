"""AA and ACD rendering polish (aa-acd-templates T5, S1/S6).

The approved AA-B and ACD-B mockups use booktabs tables (no vertical rules, no
shaded header), keep figures next to the text that introduces them, and do not
reserve a full page of look-ahead before every section. These tests pin the
deterministic part of that, scoped to the templates that opt in:

  1. ``markdown_to_latex`` only emits the booktabs table with
     ``booktabs_tables=True``; the default keeps the legacy grid (S6);
  2. ``render_tex`` turns it on for ``aa`` and ``acd`` and for no other
     template (APE, UNL keep the grid, the ``tbp`` figure and the look-ahead);
  3. the two templates define the macros that output relies on.

Purely visual tweaks (indentation, gaps, footer) are checked on the rendered
PDFs, not here.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import build_latex_report  # noqa: E402
import test_aa_template  # noqa: E402
import test_acd_template  # noqa: E402

# Reuse the leak-proof fixture: a render here can never publish globally.
_never_publish_outside_tmp = test_aa_template._never_publish_outside_tmp

THREE_COLUMNS = """\
| Algoritmo | Espera | Retorno |
|---|---|---|
| FCFS | 8,75 | 15,25 |
| SJF | 7,75 | 14,25 |
"""

TWO_COLUMNS = """\
| Termino | Definicion |
|---|---|
| API | Interfaz |
"""

FIGURE = "![Diagrama. Fuente: propia.](fig.png)\n"

BOOKTABS_BODY = (
    "# Desarrollo\n\n" + THREE_COLUMNS + "\n" + TWO_COLUMNS + "\n" + FIGURE + "\n# Conclusiones\n\nFin.\n"
)


def table_blocks(tex: str) -> list[str]:
    return re.findall(r"\\begin\{(?:xltabular|longtable)\}.*?\\end\{(?:xltabular|longtable)\}", tex, re.S)


# ---------------------------------------------------------------------------
# 1. The converter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("markdown", [THREE_COLUMNS, TWO_COLUMNS])
def test_booktabs_tables_emit_horizontal_rules_only(markdown: str) -> None:
    tex = build_latex_report.markdown_to_latex(markdown, booktabs_tables=True)
    (block,) = table_blocks(tex)
    for rule in (r"\toprule", r"\midrule", r"\bottomrule"):
        assert rule in block
    assert r"\hline" not in block
    assert r"\rowcolor" not in block
    colspec = block.split("\n", 1)[0]
    assert "|" not in colspec, "no vertical rules"


def test_booktabs_tables_stay_breakable_and_repeat_the_header() -> None:
    tex = build_latex_report.markdown_to_latex(TWO_COLUMNS, booktabs_tables=True)
    assert r"\begin{xltabular}{\textwidth}{" in tex
    assert r"\endhead" in tex, "a table that breaks across pages repeats its header"
    assert r"\reporttablehead{Termino}" in tex


def colspec_of(markdown: str) -> str:
    tex = build_latex_report.markdown_to_latex(markdown, booktabs_tables=True)
    (block,) = table_blocks(tex)
    return block.split("\n", 1)[0]


MIXED_COLUMNS = """\
| Fase | Duración | Actividad | Producto |
|---|---|---|---|
| Inicio | 10 | Exposición del docente sobre restricciones de REST | Apuntes |
| Taller | 40 | Demostración en vivo de los endpoints GET y POST | Código |
"""


def test_booktabs_columns_share_the_width_by_content() -> None:
    weights = [float(w) for w in re.findall(r"\\hsize=([\d.]+)\\hsize", colspec_of(MIXED_COLUMNS))]
    assert len(weights) == 4
    assert sum(weights) == pytest.approx(4, abs=0.002), "tabularx needs the factors to add up to the column count"
    assert max(weights[0], weights[1], weights[3]) < weights[2], "a column of sentences is the widest"


def test_booktabs_alignment_left_for_the_first_and_text_columns_centered_for_short_ones() -> None:
    spec = colspec_of(MIXED_COLUMNS)
    cols = re.findall(r">\{\\hsize=[\d.]+\\hsize\\(\w+)\\arraybackslash\}X", spec)
    assert cols == ["raggedright", "centering", "raggedright", "centering"]


def test_booktabs_alignment_markers_in_the_separator_row_win() -> None:
    markdown = MIXED_COLUMNS.replace("|---|---|---|---|", "|:---:|---:|:---|:---:|")
    cols = re.findall(r">\{\\hsize=[\d.]+\\hsize\\(\w+)\\arraybackslash\}X", colspec_of(markdown))
    assert cols == ["centering", "raggedleft", "raggedright", "centering"]


def test_booktabs_tables_are_off_by_default_and_keep_the_grid() -> None:
    tex = build_latex_report.markdown_to_latex(THREE_COLUMNS)
    assert r"\hline" in tex and r"\rowcolor[gray]{0.92}" in tex
    assert r"\toprule" not in tex and r"\reporttablehead" not in tex


def test_default_figure_placement_is_unchanged() -> None:
    assert r"\begin{figure}[tbp]" in build_latex_report.markdown_to_latex(FIGURE)


def test_compact_look_ahead_replaces_the_page_sized_needspace() -> None:
    body = "# Desarrollo\n\nTexto.\n\n## Detalle\n\nTexto.\n\n# Conclusiones\n\nFin.\n"
    legacy = build_latex_report.markdown_to_latex(body)
    compact = build_latex_report.markdown_to_latex(body, compact_headings=True)
    assert r"\Needspace{18\baselineskip}" in legacy and r"\Needspace{16\baselineskip}" in legacy
    assert r"\Needspace{5\baselineskip}" in compact
    assert not re.search(r"\\Needspace\{(16|18)\\baselineskip\}", compact)


# ---------------------------------------------------------------------------
# 2. Which templates opt in
# ---------------------------------------------------------------------------


def test_only_aa_and_acd_opt_in() -> None:
    expected = {"aa", "aa_report", "acd", "acd_report"}
    for capability in (
        build_latex_report.BOOKTABS_TEMPLATE_KEYS,
        build_latex_report.INLINE_FIGURE_TEMPLATE_KEYS,
    ):
        assert capability == expected
        assert not (capability & build_latex_report.APE_TEMPLATE_KEYS)
        assert not (capability & build_latex_report.UNL_TEMPLATE_KEYS)


def test_compact_headings_are_aa_acd_and_the_two_column_ieee_essay() -> None:
    capability = build_latex_report.COMPACT_HEADING_TEMPLATE_KEYS
    assert capability == {"aa", "aa_report", "acd", "acd_report", "ieee", "ieee_report"}
    assert not (capability & build_latex_report.APE_TEMPLATE_KEYS)
    assert not (capability & build_latex_report.UNL_TEMPLATE_KEYS)
    # A column page is the IEEE essay's alone.
    assert build_latex_report.COLUMN_LAYOUT_TEMPLATE_KEYS == {"ieee", "ieee_report"}


def aa_render(tmp_path: Path, **raw) -> str:
    return test_aa_template.render(tmp_path, raw=raw or None, body=BOOKTABS_BODY)


def acd_render(tmp_path: Path, **raw) -> str:
    return test_acd_template.render(tmp_path, raw=raw or None, body=BOOKTABS_BODY)


@pytest.mark.parametrize("render", [aa_render, acd_render])
def test_aa_and_acd_render_booktabs_inline_figures_and_compact_headings(render, tmp_path: Path) -> None:
    tex = render(tmp_path)
    blocks = table_blocks(tex)
    assert len(blocks) == 2
    for block in blocks:
        assert r"\toprule" in block and r"\hline" not in block
    assert r"\begin{figure}[htbp]" in tex
    assert r"\Needspace{5\baselineskip}" in tex
    assert not re.search(r"\\Needspace\{(16|18)\\baselineskip\}", tex)


@pytest.mark.parametrize("render", [aa_render, acd_render])
def test_explicit_here_placement_still_pins_the_figure(render, tmp_path: Path) -> None:
    tex = render(tmp_path, figure_placement="here")
    assert r"\begin{figure}[H]" in tex


def test_other_templates_keep_the_grid_the_tbp_figure_and_the_look_ahead(tmp_path: Path) -> None:
    """S6: `template: unl` (and APE, by key) render exactly as before."""
    tex = aa_render(tmp_path, template="unl")
    blocks = table_blocks(tex)
    assert len(blocks) == 2 and all(r"\hline" in block for block in blocks)
    assert r"\toprule" not in tex
    assert r"\begin{figure}[tbp]" in tex
    assert r"\Needspace{18\baselineskip}" in tex


# ---------------------------------------------------------------------------
# 3. The templates carry the macros the output uses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["aa-report.tex", "acd-report.tex"])
def test_templates_define_the_table_header_macro_and_load_booktabs(name: str) -> None:
    text = (ROOT / "templates" / name).read_text(encoding="utf-8")
    assert r"\newcommand{\reporttablehead}" in text
    assert r"\usepackage{booktabs}" in text


def test_aa_template_does_not_indent_the_paragraph_after_a_heading_or_a_table() -> None:
    text = test_aa_template.AA_TEMPLATE.read_text(encoding="utf-8")
    assert "es-noindentfirst" in text, "babel-spanish indents the first paragraph by default"
    # xltabular never runs the env/.../after hook, but its end command is hookable.
    assert "cmd/endxltabular/after" in text


def test_aa_zone_also_clears_floats_that_may_land_in_place() -> None:
    """A `[htbp]` figure can be placed where it is written, so it must clear the ficha too."""
    text = test_aa_template.AA_TEMPLATE.read_text(encoding="utf-8")
    blocks = re.search(r"\\newcommand\{\\zone@blocks\}\{(.*?)\}", text, re.S).group(1)
    assert "figure" in blocks and "table" in blocks
