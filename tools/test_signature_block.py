"""Tests for the author signature block.

The block used to open with `\\thispagestyle{plain}`. When the signature did
not fit on the current page, that command still ran on the previous page and
stripped its institutional header. The block must not set a page style.

Its role label must also follow the number of authors: a comma-separated
`student` field means several people sign.
"""

from __future__ import annotations

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
    end = tex.index(r"\rule{7.3cm}{0.4pt}")
    start = tex.rindex(r"\vspace*{1.15cm}", 0, end)
    return tex[start: tex.index(r"\newpage", end)]


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
