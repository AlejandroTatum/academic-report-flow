"""#101: an image caption may contain a citation; every builder must agree."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

TOOLS_DIR = str(Path(__file__).resolve().parent)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import build_docx_report  # noqa: E402
import build_latex_report  # noqa: E402
import build_report  # noqa: E402
import concision  # noqa: E402
from test_build_docx_report import SAMPLE_IMAGE, make_report  # noqa: E402

CITED = "![Figura 1. Acceso a internet, datos de [@inec2025tic].](figures/x.png)"


def test_latex_renders_an_image_whose_caption_cites() -> None:
    latex = build_latex_report.markdown_to_latex(f"# T\n\n{CITED}\n")
    assert "![" not in latex
    assert r"\includegraphics" in latex
    assert r"\caption{Figura 1. Acceso a internet, datos de" in latex


def test_latex_figure_references_include_an_image_whose_caption_cites() -> None:
    assert build_latex_report.figure_references(CITED) == ["figures/x.png"]


def test_html_renders_an_image_whose_caption_cites(tmp_path: Path) -> None:
    md = tmp_path / "body.md"
    md.write_text(f"# T\n\n{CITED}\n", encoding="utf-8")
    out = build_report.render(md, Path(build_report.__file__).resolve().parents[1] / "templates" / "ensayo_unl.css", tmp_path)
    assert "![" not in out
    assert "<figure" in out


def test_docx_renders_an_image_whose_caption_cites(tmp_path: Path) -> None:
    shutil.copy2(SAMPLE_IMAGE, tmp_path / "figura.png")
    body = "# T\n\n![Diagrama, datos de [@k].](../../figura.png)\n"
    bib = "@misc{k, author = {Autor}, title = {Titulo}, year = {2025}}\n"
    folder = make_report(tmp_path, body, route="technical", bib=bib)
    from docx import Document

    document = Document(str(build_docx_report.build(folder).docx_path))
    assert len(document.inline_shapes) == 1


def test_concision_does_not_count_an_image_whose_caption_cites() -> None:
    assert concision.prose_words(CITED) == 0


# #103: an optional {width=NN%} / {height=NN%} block sizes one figure.


def test_figure_without_size_attribute_keeps_the_default_options() -> None:
    latex = build_latex_report.markdown_to_latex("![C.](figures/x.png)\n")
    assert r"\includegraphics[width=0.86\textwidth,keepaspectratio]" in latex


def test_width_attribute_overrides_the_width_of_that_figure_only() -> None:
    latex = build_latex_report.markdown_to_latex("![A.](figures/a.png){width=70%}\n\n![B.](figures/b.png)\n")
    assert r"\includegraphics[width=0.7\textwidth,keepaspectratio]{figures/a.png}" in latex
    assert r"\includegraphics[width=0.86\textwidth,keepaspectratio]{figures/b.png}" in latex
    assert "{width=" not in latex


def test_height_attribute_caps_the_height_of_that_figure() -> None:
    latex = build_latex_report.markdown_to_latex("![A.](figures/a.png){height=50%}\n")
    assert r"\includegraphics[width=0.86\textwidth,height=0.5\textheight,keepaspectratio]" in latex


def test_sized_figure_is_still_a_figure_reference() -> None:
    assert build_latex_report.figure_references("![A.](figures/a.png){width=70%}") == ["figures/a.png"]


def test_html_drops_the_size_attribute_text(tmp_path: Path) -> None:
    md = tmp_path / "body.md"
    md.write_text("# T\n\n![A.](a.png){width=70%}\n", encoding="utf-8")
    out = build_report.render(md, Path(build_report.__file__).resolve().parents[1] / "templates" / "ensayo_unl.css", tmp_path)
    assert "{width=" not in out


def test_connector_final_scale_follows_the_width_override() -> None:
    import connector_pdf_stage

    geometry = connector_pdf_stage.TemplateGeometry(text_width_pt=400.0, text_height_pt=600.0)
    default = connector_pdf_stage.final_print_scale(1000.0, 100.0, geometry)
    narrow = connector_pdf_stage.final_print_scale(1000.0, 100.0, geometry, {"width": 0.43})
    assert narrow == pytest.approx(default / 2)
