"""Layout defaults that keep pages free of large blank gaps (skill-visual-organization T3).

S4: figures float by default (``[!htbp]``) unless report.yml pins them with
``figure_placement: here``; runs of consecutive screenshots are set two per
row so each one does not take a page of its own, with the same sequential
figure numbering as when they stand alone.
S3: long unbreakable tokens (MAC, IPv6, IP ranges) may break inside table
cells, and a row shorter than the header is reported instead of silently
padded.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import build_latex_report  # noqa: E402

md = build_latex_report.markdown_to_latex


def shots(count: int, gap: str = "\n\n") -> str:
    return gap.join(f"![Captura {n}](figures/pt-{n:02d}.png)" for n in range(1, count + 1)) + "\n"


def figure_envs(tex: str) -> list[str]:
    return re.findall(r"\\begin\{figure\}.*?\\end\{figure\}", tex, re.S)


# ---------------------------------------------------------------------------
# S4 — float default
# ---------------------------------------------------------------------------


def test_figures_float_with_h_first_by_default() -> None:
    tex = md("Texto.\n\n![Diagrama](figures/d.png)\n")
    assert r"\begin{figure}[!htbp]" in tex


def test_explicit_here_still_pins_the_figure() -> None:
    tex = md("Texto.\n\n![Diagrama](figures/d.png)\n", figure_placement="H")
    assert r"\begin{figure}[H]" in tex


# ---------------------------------------------------------------------------
# S4 — screenshot grid
# ---------------------------------------------------------------------------


def test_three_consecutive_screenshots_are_set_two_per_row_by_default() -> None:
    tex = md(shots(3))
    envs = figure_envs(tex)
    assert len(envs) == 2, "two rows: a pair and the odd one"
    assert envs[0].count(r"\begin{minipage}") == 2
    assert envs[1].count(r"\begin{minipage}") == 1
    # One numbered caption per screenshot, in body order.
    assert re.findall(r"\\caption\{(Captura \d)\}", tex) == ["Captura 1", "Captura 2", "Captura 3"]
    assert r"\subfloat" not in tex and r"\subcaption" not in tex


def test_grid_keeps_the_figure_count_of_the_ungrouped_case() -> None:
    grouped = md(shots(5))
    single = md(shots(5), figure_grid_min_run=0)
    assert grouped.count(r"\caption{") == single.count(r"\caption{") == 5
    assert len(figure_envs(single)) == 5
    assert len(figure_envs(grouped)) == 3


def test_two_consecutive_screenshots_stay_alone_by_default_but_group_on_opt_in() -> None:
    assert r"\begin{minipage}" not in md(shots(2))
    tex = md(shots(2), figure_grid_min_run=2)
    (env,) = figure_envs(tex)
    assert env.count(r"\begin{minipage}") == 2 and env.count(r"\caption{") == 2


def test_text_between_screenshots_breaks_the_run() -> None:
    body = "![A](figures/a.png)\n\n![B](figures/b.png)\n\nTexto.\n\n![C](figures/c.png)\n"
    assert r"\begin{minipage}" not in md(body)


def test_grid_disabled_keeps_one_figure_per_screenshot() -> None:
    assert r"\begin{minipage}" not in md(shots(4), figure_grid_min_run=0)


def test_grid_rows_also_apply_on_the_pinned_here_path() -> None:
    tex = md(shots(4), figure_placement="H")
    envs = figure_envs(tex)
    assert len(envs) == 2
    assert all(env.startswith(r"\begin{figure}[H]") for env in envs)


def test_grid_cells_fit_their_half_width_and_a_height_cap() -> None:
    tex = md(shots(3))
    assert re.search(r"\\begin\{minipage\}\[t\]\{0\.48\\linewidth\}", tex)
    assert re.search(r"\\includegraphics\[width=\\linewidth,height=0\.3\d*\\textheight,keepaspectratio\]", tex)


def test_a_sized_image_is_never_grouped() -> None:
    body = "![A](figures/a.png){width=60%}\n\n![B](figures/b.png)\n\n![C](figures/c.png)\n"
    tex = md(body)
    assert r"\begin{minipage}" not in tex


def test_grid_is_off_on_a_column_page() -> None:
    assert r"\begin{minipage}" not in md(shots(4), column_layout=True)


# ---------------------------------------------------------------------------
# S3 — breakable tokens in table cells
# ---------------------------------------------------------------------------

TOKENS_TABLE = """\
| Equipo | MAC | IPv6 | Rango |
|---|---|---|---|
| PC0 | 0001.6453.DBC1 | 2001:0db8:0000:0000:0000:ff00:0042:8329 | 192.168.10.1-192.168.10.254 |
| PC1 | 38:A7:46:39:D2:7B | fe80::1 | 10.0.0.0/8 |
"""


@pytest.mark.parametrize("options", [{}, {"booktabs_tables": True}])
def test_long_addresses_may_break_inside_table_cells(options: dict) -> None:
    tex = md(TOKENS_TABLE, **options)
    assert r"0001.\allowbreak{}6453.\allowbreak{}DBC1" in tex
    assert r"38:\allowbreak{}A7:\allowbreak{}46" in tex
    assert r"2001:\allowbreak{}0db8:\allowbreak{}0000" in tex
    assert r"192.\allowbreak{}168.\allowbreak{}10.\allowbreak{}1-\allowbreak{}192" in tex


def test_short_cells_and_prose_are_left_alone() -> None:
    tex = md(TOKENS_TABLE + "\nLa MAC 38:A7:46:39:D2:7B en prosa.\n")
    assert r"PC0 &" in tex or r"PC0}" in tex
    assert "fe80::1" in tex
    assert "La MAC 38:A7:46:39:D2:7B en prosa." in tex


def test_urls_and_citations_inside_cells_are_not_broken() -> None:
    table = (
        "| Fuente | Enlace | Dato |\n|---|---|---|\n"
        "| RFC | <http://192.168.100.200/a.b.c> | 172.16.254.1 [@rfc1918] |\n"
    )
    tex = md(table)
    assert r"\url{http://192.168.100.200/a.b.c}" in tex
    assert r"172.\allowbreak{}16.\allowbreak{}254.\allowbreak{}1" in tex
    assert r"\cite{rfc1918}" in tex


def test_styled_tables_also_receive_breakable_tokens() -> None:
    cell = build_latex_report.convert_table_cell("2001:0db8:0000:0000:0000:ff00:0042:8329")
    assert cell.count(r"\allowbreak{}") == 7


# S9: typeset auto wraps tokens in inline code; inside a cell they render as the
# same breakable \texttt as in prose, never with a second \allowbreak.
@pytest.mark.parametrize(
    "token",
    ["0001.6453.DBC1", "38:A7:46:39:D2:7B", "2001:0db8:0000:0000:0000:ff00:0042:8329", "192.168.10.0/24",
     "fe80::/10", "Fa0/24", "show mac address-table", "11000000.10101000.00001010.00000001"],
)
def test_backticked_tokens_in_cells_render_as_breakable_texttt_once(token: str) -> None:
    cell = build_latex_report.convert_table_cell(f"`{token}` y **clave**")
    assert cell == build_latex_report.inline_code(token) + r" y \textbf{clave}"
    assert r"\allowbreak{}\allowbreak{}" not in cell


@pytest.mark.parametrize("options", [{}, {"booktabs_tables": True}])
def test_backticked_tokens_and_bold_render_inside_table_cells(options: dict) -> None:
    table = (
        "| Equipo | MAC | Nota |\n|---|---|---|\n"
        "| `Fa0/1` | `0001.6453.DBC1` | la **dirección MAC** de `192.168.1.1`-`192.168.1.254` |\n"
    )
    tex = md(table, **options)
    assert r"\texttt{Fa0/\allowbreak{}1}" in tex
    assert r"\texttt{0001.\allowbreak{}6453.\allowbreak{}DBC1}" in tex
    assert r"\textbf{dirección MAC}" in tex
    assert r"\texttt{192.\allowbreak{}168.\allowbreak{}1.\allowbreak{}1}-\texttt{192." in tex
    assert r"\allowbreak{}\allowbreak{}" not in tex and "`" not in tex


# ---------------------------------------------------------------------------
# S3 — ragged rows are reported, not silently padded
# ---------------------------------------------------------------------------

RAGGED = """\
Tabla 3. Direcciones del laboratorio.

| Equipo | MAC | IP |
|---|---|---|
| PC0 | 0001.6453.DBC1 | 10.0.0.1 |
| PC1 | 0001.6453.DBC2 |
"""


@pytest.mark.parametrize("options", [{}, {"booktabs_tables": True}])
def test_a_short_row_warns_with_its_table_and_row(options: dict, capsys) -> None:
    tex = md(RAGGED, **options)
    err = capsys.readouterr().err
    assert "Aviso" in err and "Tabla 3" in err
    assert "fila 2" in err and "2 de 3 celdas" in err
    # The LaTeX stays valid: the row is still completed to the column count.
    assert re.search(r"PC1 & 0001\.\\allowbreak\{\}6453\.\\allowbreak\{\}DBC2 & +\\\\", tex)


def test_a_complete_table_prints_no_warning(capsys) -> None:
    md(TOKENS_TABLE)
    assert "Aviso" not in capsys.readouterr().err


# ---------------------------------------------------------------------------
# report.yml wiring
# ---------------------------------------------------------------------------


def render(folder: Path, body: str, template: str = "unl", **extra: object) -> str:
    import yaml

    import report_config

    folder.mkdir(parents=True, exist_ok=True)
    raw = {
        "type": "technical_report", "backend": "latex", "output": "pdf", "template": template,
        "metadata": {"title": "T", "subject": "S"}, "body": "body.md", **extra,
    }
    (folder / "report.yml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    (folder / "body.md").write_text(body, encoding="utf-8")
    return build_latex_report.render_tex(report_config.ReportConfig.load(folder))


@pytest.mark.parametrize("template", ["unl", "aa"])
def test_render_tex_floats_with_h_first_by_default(tmp_path: Path, template: str) -> None:
    assert r"\begin{figure}[!htbp]" in render(tmp_path, "Texto.\n\n![D](figs/d.png)\n", template)


def test_render_tex_here_report_gets_grids_too(tmp_path: Path) -> None:
    tex = render(tmp_path, shots(4), figure_placement="here")
    assert tex.count(r"\begin{figure}[H]") == 2 and tex.count(r"\begin{minipage}[t]{0.48") == 4


@pytest.mark.parametrize(("value", "minipages"), [(True, 2), (False, 0)])
def test_render_tex_reads_figure_grid(tmp_path: Path, value: bool, minipages: int) -> None:
    assert render(tmp_path, shots(2), figure_grid=value).count(r"\begin{minipage}[t]{0.48") == minipages
