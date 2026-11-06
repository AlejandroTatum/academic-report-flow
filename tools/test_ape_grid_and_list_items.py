"""Tests for APE 6 report-flow defects S4 (grid widths) and S5 (list items)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import build_latex_report  # noqa: E402

SIX_COLUMNS_MD = """\
| Intervalo | Obs | Esp | Chi | Crit | Decisión |
| --- | --- | --- | --- | --- | --- |
| 1 | 10 | 9.5 | 0.026 | 3.84 | no se rechaza H0 con el nivel de significancia fijado |
| 2 | 12 | 9.5 | 0.658 | 3.84 | no se rechaza H0 con el nivel de significancia fijado |
"""

EQUAL_COLUMNS_MD = """\
| Aaaa | Bbbb | Cccc |
| --- | --- | --- |
| 1111 | 2222 | 3333 |
| 4444 | 5555 | 6666 |
"""


def hsize_factors(tex: str) -> list[float]:
    return [float(value) for value in re.findall(r"\\hsize=([0-9.]+)\\hsize", tex)]


def test_grid_columns_follow_content_width() -> None:
    tex = build_latex_report.markdown_to_latex(SIX_COLUMNS_MD)
    factors = hsize_factors(tex)
    assert len(factors) == 6
    assert factors[-1] > factors[1]
    assert abs(sum(factors) - 6) < 0.01


def test_grid_keeps_legacy_look() -> None:
    tex = build_latex_report.markdown_to_latex(SIX_COLUMNS_MD)
    assert r"\begin{xltabular}{\textwidth}{|" in tex
    assert r"\hline" in tex
    assert r"\rowcolor[gray]{0.92}" in tex
    assert r"\footnotesize" in tex
    assert r"\centering\arraybackslash}X" in tex
    assert r"\endhead" in tex


def test_grid_with_equal_cells_keeps_equal_weights() -> None:
    tex = build_latex_report.markdown_to_latex(EQUAL_COLUMNS_MD)
    assert hsize_factors(tex) == [1.0, 1.0, 1.0]


def test_list_item_starting_with_bracket_is_not_read_as_label() -> None:
    tex = build_latex_report.markdown_to_latex("- [0.0, 0.1): 1001\n- [0.1, 0.2): 998\n")
    assert not re.search(r"\\item\s*\[", tex)
    assert r"\item{}[0.0, 0.1): 1001" in tex
    assert r"\item{}[0.1, 0.2): 998" in tex


def test_ordered_item_starting_with_bracket_is_not_read_as_label() -> None:
    tex = build_latex_report.markdown_to_latex("1. [a, b): x\n")
    assert not re.search(r"\\item\s*\[", tex)


def test_ordinary_list_items_are_unchanged() -> None:
    tex = build_latex_report.markdown_to_latex("- uno\n- dos\n\n1. tres\n")
    assert r"\item uno" in tex
    assert r"\item dos" in tex
    assert r"\item tres" in tex
    assert r"\item{}" not in tex
