"""``figure_placement`` opt-in: keep figures next to the text that discusses them."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import build_latex_report  # noqa: E402
import report_config  # noqa: E402

BODY = "Texto previo.\n\n![Diagrama de procesos](figs/missing.png)\n"


def make_config(folder: Path, **extra: object) -> report_config.ReportConfig:
    folder.mkdir(parents=True, exist_ok=True)
    raw = {
        "type": "technical_report",
        "backend": "latex",
        "output": "pdf",
        "template": "unl",
        "metadata": {"title": "T", "subject": "S"},
        "body": "body.md",
        **extra,
    }
    (folder / "report.yml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    (folder / "body.md").write_text(BODY, encoding="utf-8")
    return report_config.ReportConfig.load(folder)


def test_default_placement_is_float(tmp_path: Path) -> None:
    assert make_config(tmp_path).figure_placement == "float"


@pytest.mark.parametrize("value", ["float", "here"])
def test_accepts_known_values(tmp_path: Path, value: str) -> None:
    assert make_config(tmp_path, figure_placement=value).figure_placement == value


@pytest.mark.parametrize("value", ["top", "H", True, 1, None])
def test_rejects_other_values_at_load(tmp_path: Path, value: object) -> None:
    with pytest.raises(SystemExit, match="figure_placement"):
        make_config(tmp_path, figure_placement=value)


def test_markdown_to_latex_defaults_to_float_h_first() -> None:
    tex = build_latex_report.markdown_to_latex(BODY)
    assert r"\begin{figure}[!htbp]" in tex


def test_markdown_to_latex_here_emits_H_and_keeps_needspace() -> None:
    tex = build_latex_report.markdown_to_latex(BODY, figure_placement="H")
    assert r"\begin{figure}[H]" in tex
    assert r"\Needspace{6\baselineskip}" in tex
    assert "[!htbp]" not in tex


def test_render_tex_default_keeps_float(tmp_path: Path) -> None:
    tex = build_latex_report.render_tex(make_config(tmp_path))
    assert r"\begin{figure}[!htbp]" in tex


def test_render_tex_here_pins_figures(tmp_path: Path) -> None:
    tex = build_latex_report.render_tex(make_config(tmp_path, figure_placement="here"))
    assert r"\begin{figure}[H]" in tex
    assert "[!htbp]" not in tex


ANNEX_BODY = (
    "# Resultados\n\n![Mapa](figs/a.png)\n\n"
    "# Anexos\n\n## Anexo A. Original\n\n![Original](figs/b.png)\n"
)


def test_annex_figures_stay_where_they_are_written() -> None:
    # An annex starts a page with only its heading; a floating figure would
    # leave that page empty and jump to the next one.
    tex = build_latex_report.markdown_to_latex(ANNEX_BODY)
    before, after = tex.split(r"\section{Anexos}")
    assert r"\begin{figure}[!htbp]" in before and r"\begin{figure}[H]" not in before
    assert r"\begin{figure}[H]" in after and "[!htbp]" not in after
