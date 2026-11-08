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


# --- The signature does not depend on the AI declaration -------------------
#
# `ai_declaration: false` is the explicit opt-out of the declaration, not of
# the signature: the author still signs the report. The signature lands at the
# end of the document, after the body and the bibliography.

DECLARATION = {
    "title": "Declaración",
    "format": "markdown",
    "text": "Herramientas:\n\n| Herramienta | Uso |\n|---|---|\n| Python | Pruebas |\n",
}


def render_ape(tmp_path: Path, raw: dict, **metadata: object) -> str:
    from test_ape_template import full_ape_metadata, make_render_config

    return build_latex_report.render_tex(make_render_config(
        tmp_path, raw=raw, metadata={**full_ape_metadata(), **metadata},
    ))


def test_ape_group_signs_without_ai_declaration(tmp_path: Path) -> None:
    tex = render_ape(
        tmp_path, {"ai_declaration": False}, student=", ".join(GROUP), members=GROUP,
    )
    cells = signature_cells(tex)
    assert len(cells) == len(GROUP)
    assert all(cell.count(r"\rule") == 1 for cell in cells)
    assert tex.count("Autores") == 1
    # End of the document: after the last body section, and no declaration.
    assert tex.index("Autores") > tex.index("Contenido de Recomendaciones.")
    assert "Declaración de uso de IA" not in tex
    assert r"\section*" not in tex


def test_ape_single_author_signs_without_ai_declaration(tmp_path: Path) -> None:
    tex = render_ape(tmp_path, {"ai_declaration": False})
    assert (
        "\\vspace*{1.15cm}\n"
        "\\begin{flushright}\n"
        "\\rule{7.3cm}{0.4pt}\\\\[-0.1cm]\n"
        "{\\bfseries Alejandro Padilla}\\\\\n"
        "Autor\n"
        "\\end{flushright}\n"
    ) in tex
    assert tex.index(r"\rule{7.3cm}") > tex.index("Contenido de Recomendaciones.")
    assert r"\section*" not in tex


def test_signature_is_not_duplicated_at_the_front_without_declaration(tmp_path: Path) -> None:
    tex = render_ape(tmp_path, {"ai_declaration": False}, student=", ".join(GROUP), members=GROUP)
    assert tex.count(r"\vspace*{1.15cm}") == 1


def test_ape_declaration_output_is_unchanged(tmp_path: Path) -> None:
    raw = {"ai_declaration": DECLARATION, "ai_declaration_position": "after_bibliography"}
    tex = render_ape(tmp_path, raw)
    assert tex[tex.index(r"\Needspace{5"):] == (
        "\\Needspace{5\\baselineskip}\n"
        "\\section*{Declaración}\n"
        "\\addcontentsline{toc}{section}{Declaración}\n"
        "\n"
        "Herramientas:\n"
        "\n"
        "\\Needspace{4\\baselineskip}\n"
        "\\begingroup\n"
        "\\small\n"
        "\\renewcommand{\\arraystretch}{1.2}\n"
        "\\setlength{\\tabcolsep}{3pt}\n"
        "\\begin{longtable}{| >{\\centering\\arraybackslash}p{\\dimexpr(\\textwidth-16pt)/2\\relax}"
        " | >{\\centering\\arraybackslash}p{\\dimexpr(\\textwidth-16pt)/2\\relax} |}\n"
        "\\hline\n"
        "\\rowcolor[gray]{0.92}\n"
        "\\textbf{Herramienta} & \\textbf{Uso} \\\\\n"
        "\\hline\n"
        "\\endhead\n"
        "Python & Pruebas \\\\\n"
        "\\hline\n"
        "\\end{longtable}\n"
        "\\endgroup\n"
        "\n"
        "\\vspace*{1.15cm}\n"
        "\\begin{flushright}\n"
        "\\rule{7.3cm}{0.4pt}\\\\[-0.1cm]\n"
        "{\\bfseries Alejandro Padilla}\\\\\n"
        "Autor\n"
        "\\end{flushright}\n"
        "\n"
        "\n"
        "% The renderer fills FRONT_MATTER with the very same block it puts in\n"
        "% AI_DECLARATION (the plain-report.tex mechanism), so the declaration is\n"
        "% printed once above and the duplicate is captured here instead of being\n"
        "% typeset twice.\n"
        "\\long\\def\\reportaideclarationalias{}\n"
        "\n"
        "\\end{document}\n"
    )


def test_declaration_with_a_group_keeps_one_signature(tmp_path: Path) -> None:
    raw = {"ai_declaration": DECLARATION, "ai_declaration_position": "after_bibliography"}
    tex = render_ape(tmp_path, raw, student=", ".join(GROUP), members=GROUP)
    assert tex.count(r"\vspace*{1.15cm}") == 1
    assert len(signature_cells(tex)) == len(GROUP)
    assert tex.index(r"\section*{Declaración}") < tex.index("Autores")


def test_every_signing_format_signs_without_ai_declaration(tmp_path: Path) -> None:
    from test_ape_template import full_ape_metadata, make_render_config

    for fmt in ("ape", "acd", "aa", "libre", "ieee"):
        tex = build_latex_report.render_tex(make_render_config(
            tmp_path / fmt, raw={"format": fmt, "ai_declaration": False}, metadata=full_ape_metadata(),
        ))
        assert tex.count(r"\rule{7.3cm}{0.4pt}") == 1, fmt


def test_report_without_the_ai_declaration_key_is_left_alone(tmp_path: Path) -> None:
    tex = render_ape(tmp_path, {})
    assert r"\rule{7.3cm}" not in tex
