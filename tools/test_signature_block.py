"""Tests for the author signature block.

The block used to open with `\\thispagestyle{plain}`. When the signature did
not fit on the current page, that command still ran on the previous page and
stripped its institutional header. The block must not set a page style.

Its role label must also follow the number of authors: a comma-separated
`student` field means several people sign. A group gets one signature rule per
member, laid out in a two-column grid, kept together on one page.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import build_latex_report  # noqa: E402
from test_optional_template_fields import make_config  # noqa: E402

# This template always emits the signature after its IA declaration.
TEMPLATE = "chamba_overleaf"


def signature_block(tex: str) -> str:
    """Return the rendered signature, from its spacing up to its page break."""
    start = tex.index(r"\vspace*{1.15cm}")
    return tex[start: tex.index(r"\newpage", start)]


def signature_cells(block: str) -> list[str]:
    """Each member's own signature cell (rule plus name), in reading order."""
    return re.findall(
        r"\\begin\{minipage\}\[t\]\{0\.46\\linewidth\}.*?\\end\{minipage\}", block, flags=re.S,
    )


GROUP = ["Alejandro Padilla Espinoza", "Doménica Rojas", "Ivett Zaragocín", "Luis Gómez", "Ana Pérez"]


def test_signature_does_not_set_a_page_style(tmp_path: Path) -> None:
    tex = build_latex_report.render_tex(
        make_config(tmp_path, TEMPLATE, {"student": "Ana"}),
    )
    preceding = tex[: tex.index(r"\rule{7.3cm}{0.4pt}")].rsplit(r"\section*", 1)[-1]
    assert r"\thispagestyle" not in preceding


def test_single_author_is_labelled_autor(tmp_path: Path) -> None:
    tex = build_latex_report.render_tex(
        make_config(tmp_path, TEMPLATE, {"student": "Ana Pérez"}),
    )
    block = signature_block(tex)
    assert "Autor\n" in block
    assert "Autores" not in block


def test_several_authors_are_labelled_autores(tmp_path: Path) -> None:
    tex = build_latex_report.render_tex(
        make_config(tmp_path, TEMPLATE, {"student": "Ana Pérez, Luis Gómez"}),
    )
    assert "Autores\n" in signature_block(tex)


def test_single_author_signature_is_unchanged(tmp_path: Path) -> None:
    tex = build_latex_report.render_tex(
        make_config(tmp_path, TEMPLATE, {"student": "Ana Pérez & Co"}),
    )
    assert signature_block(tex) + "\\newpage\n" == (
        "\\vspace*{1.15cm}\n"
        "\\begin{flushright}\n"
        "\\rule{7.3cm}{0.4pt}\\\\[-0.1cm]\n"
        "{\\bfseries Ana Pérez \\& Co}\\\\\n"
        "Autor\n"
        "\\end{flushright}\n"
        "\\newpage\n"
    )


def test_group_members_each_sign_on_their_own_rule(tmp_path: Path) -> None:
    tex = build_latex_report.render_tex(
        make_config(tmp_path, TEMPLATE, {"student": ", ".join(GROUP), "members": GROUP}),
    )
    block = signature_block(tex)
    cells = signature_cells(block)
    assert len(cells) == len(GROUP)
    for cell, name in zip(cells, GROUP):
        assert cell.count(r"\rule") == 1
        assert cell.count(name) == 1
        assert sum(other in cell for other in GROUP) == 1
    assert not any(a in line and b in line for line in block.splitlines() for a in GROUP for b in GROUP if a != b)
    assert block.count("Autores") == 1


def test_group_from_comma_separated_student_without_members(tmp_path: Path) -> None:
    tex = build_latex_report.render_tex(
        make_config(tmp_path, TEMPLATE, {"student": ", ".join(GROUP)}),
    )
    assert len(signature_cells(signature_block(tex))) == len(GROUP)


def test_group_block_is_kept_on_one_page(tmp_path: Path) -> None:
    tex = build_latex_report.render_tex(
        make_config(tmp_path, TEMPLATE, {"members": GROUP}),
    )
    block = signature_block(tex)
    # An outer minipage is unbreakable, so no page break can split the grid.
    assert block.lstrip().startswith(r"\vspace*{1.15cm}")
    outer = block.index(r"\begin{minipage}{\linewidth}")
    assert block.rstrip().endswith(r"\end{minipage}")
    assert all(block.index(name) > outer for name in GROUP)


def test_odd_last_row_is_centred_and_even_rows_are_not(tmp_path: Path) -> None:
    def rows(members: list[str]) -> list[str]:
        tex = build_latex_report.render_tex(make_config(tmp_path, TEMPLATE, {"members": members}))
        return [r for r in signature_block(tex).split(r"\par") if "0.46" in r]

    odd = rows(GROUP)
    assert len(odd) == 3
    assert [r.count("0.46") for r in odd] == [2, 2, 1]
    assert r"\hspace*{\fill}" in odd[-1] and r"\hfill" not in odd[-1]
    assert all(r"\hfill" in r for r in odd[:2])
    even = rows(GROUP[:4])
    assert [r.count("0.46") for r in even] == [2, 2]
    assert all(r"\hspace*{\fill}" not in r for r in even)


def test_group_names_are_latex_escaped(tmp_path: Path) -> None:
    tex = build_latex_report.render_tex(
        make_config(tmp_path, TEMPLATE, {"members": ["A & B", "C_D"]}),
    )
    block = signature_block(tex)
    assert r"A \& B" in block and r"C\_D" in block
