"""#82: a float never crosses into the next subsection, proven on a real PDF.

A multi-exercise report puts each exercise in a ``##`` subsection. With the
``section`` barrier alone, a figure that did not fit under its exercise floated
past the next exercise heading, so every exercise showed the previous one's
figure. The compile is real (same engine/Docker policy as test_latex_links).
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

import build_latex_report
from test_latex_links import _DOCKER_FALLBACK, _LATEX_ENGINE, _PNG_1PX

# Enough prose that the square figure no longer fits on the page and must
# float, while the next subsection still fits below it: the old template then
# printed that heading first. Calibrated per template (font size, cover).
_SENTENCE = "Se calcula el polinomio de Taylor y se compara el error obtenido."


@pytest.mark.skipif(
    (_LATEX_ENGINE is None and not _DOCKER_FALLBACK) or shutil.which("pdftotext") is None,
    reason="needs a local LaTeX engine or the local texlive/texlive:latest image, and pdftotext",
)
@pytest.mark.parametrize(("template", "sentences"), (("plain", 70), ("unl", 35)))  # with and without titlesec
def test_a_figure_stays_before_the_next_subsection_heading(
    tmp_path, monkeypatch, template: str, sentences: int,
) -> None:
    if _LATEX_ENGINE is None:
        real_docker_compile_command = build_latex_report.docker_compile_command

        def offline_docker_compile_command(config):
            argv = real_docker_compile_command(config)
            return [*argv[:2], "--pull=never", "--network=none", *argv[2:]]

        monkeypatch.setattr(build_latex_report, "docker_compile_command", offline_docker_compile_command)
    folder = tmp_path / "report"
    folder.mkdir()
    (folder / "figura.png").write_bytes(_PNG_1PX)
    (folder / "body.md").write_text(
        "# Resultados\n\n"
        "## Ejercicio uno\n\n"
        f"{' '.join([_SENTENCE] * sentences)}\n\n"
        "![Figura del ejercicio uno](figura.png)\n\n"
        "## Ejercicio dos\n\n"
        "Texto breve del segundo ejercicio.\n",
        encoding="utf-8",
    )
    (folder / "report.yml").write_text(
        "route: technical\n"
        "backend: latex\n"
        f"template: {template}\n"
        "pdf: build/main.pdf\n"
        "metadata:\n"
        "  title: Prueba de barreras por subseccion\n"
        "  student: Alejandro Padilla\n",
        encoding="utf-8",
    )

    config = build_latex_report.build(folder, compile_pdf=True)

    assert r"\begin{figure}[!htbp]" in config.tex_path.read_text(encoding="utf-8")
    text = subprocess.run(
        ["pdftotext", "-layout", str(config.pdf_path), "-"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert text.index("Figura del ejercicio uno") < text.index("Ejercicio dos"), text
