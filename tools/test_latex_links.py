from pathlib import Path

import base64
import shutil
import subprocess

import pytest

import build_latex_report
from build_latex_report import convert_inline, markdown_to_latex

# Same engines compile_latex() accepts, plus its existing Docker fallback: the
# proof below skips cleanly without a local engine or image and must run for
# real wherever acceptance is claimed. The Docker probe is a bounded local
# ``docker image inspect`` — it never pulls, installs, or touches the network.
_LATEX_ENGINE = (
    shutil.which("latexmk")
    or shutil.which("lualatex")
    or shutil.which("xelatex")
    or shutil.which("pdflatex")
)
_DOCKER_IMAGE = "texlive/texlive:latest"


def _local_docker_image_present(image: str) -> bool:
    docker = shutil.which("docker")
    if not docker:
        return False
    try:
        probe = subprocess.run(
            [docker, "image", "inspect", image],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


_DOCKER_FALLBACK = _LATEX_ENGINE is None and _local_docker_image_present(_DOCKER_IMAGE)

# Optional second proof: read the produced PDF's URI annotations when the repo
# dependency happens to be installed in the running environment.
try:
    import pypdf
except ImportError:
    pypdf = None

# A real 1x1 PNG so the figure validation passes and the compile is honest.
_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def test_urls_in_moving_arguments_are_protected():
    rendered = markdown_to_latex('# See <https://example.org/a_b>\n\n![See <https://example.org/a_b>](x.png)')
    assert r'\section{See \texorpdfstring{\url{https://example.org/a_b}}{https://example.org/a_b}}' in rendered
    assert r'\caption{See \protect\url{https://example.org/a_b}}' in rendered


def test_loose_ordered_and_bullet_lists_remain_single_lists():
    rendered = markdown_to_latex('1. first\n\n2. second\n\n- third\n\n- fourth')
    assert rendered.count(r'\begin{enumerate}') == 1
    assert rendered.count(r'\begin{itemize}') == 1


def test_autolink_and_named_link_are_clickable():
    rendered = convert_inline('<https://github.com/a_b/repo%20x#top~end> [repo](https://github.com/a_b/repo%20x#top~end)')
    assert r'\url{https://github.com/a_b/repo%20x#top~end}' in rendered
    assert r'\href{https://github.com/a_b/repo%20x#top~end}{repo}' in rendered


def test_inline_ssh_remote_uses_breakable_nolinkurl():
    rendered = markdown_to_latex('`git@github.com:AlejandroTatum/academic-report-flow.git`')
    assert r'\nolinkurl{git@github.com:AlejandroTatum/academic-report-flow.git}' in rendered
    assert r'\texttt{' not in rendered


def test_url_like_inline_code_preserves_url_special_characters():
    rendered = convert_inline('`https://github.com/a_b/repo%20x#top~end`')
    assert r'\nolinkurl{https://github.com/a_b/repo%20x#top~end}' in rendered


def test_report_templates_enable_arbitrary_url_breaks():
    templates = Path(__file__).resolve().parent.parent / 'templates'
    for name in ('ape-report.tex', 'unl-report.tex', 'plain-report.tex', 'ieee-report.tex'):
        source = (templates / name).read_text(encoding='utf-8')
        assert r'\usepackage{xurl}' in source, name
        assert source.index(r'\usepackage[hidelinks]{hyperref}') < source.index(r'\usepackage{xurl}'), name


def test_nested_list_preserves_enumerate_and_continuation():
    rendered = markdown_to_latex('1. a\n2. b\n   - x\n   - y\n   continuation paragraph\n3. c')
    assert rendered.count(r'\begin{enumerate}') == 1
    assert rendered.count(r'\end{enumerate}') == 1
    assert rendered.index(r'\begin{itemize}') < rendered.index(r'\item x') < rendered.index(r'\end{itemize}') < rendered.index(r'\item c')
    assert rendered.index('continuation paragraph') < rendered.index(r'\item c')


@pytest.mark.skipif(
    _LATEX_ENGINE is None and not _DOCKER_FALLBACK,
    reason="no local LaTeX engine (latexmk/lualatex/xelatex/pdflatex) and no already-present local Docker image texlive/texlive:latest (bounded image inspect; the test never pulls)",
)
def test_url_in_heading_and_caption_compiles_into_a_real_pdf(tmp_path, monkeypatch):
    """Proof that moving-argument URL protection survives a real LaTeX build.

    Characterization of existing behavior: build_latex_report.build() with
    compile_pdf=True on a temp report folder (bib-less, so no biber pass), a
    nontrivial URL (query, underscores, &) inside a heading and a figure
    caption. The renderer must keep the URL raw inside \\url (headings via
    \\texorpdfstring, captions via \\protect\\url), and the build must produce a
    real, nonempty PDF.

    When only the Docker fallback exists, the real builder/render/compile
    pipeline is kept and only this proof's container invocation is pinned
    offline (--pull=never --network=none): the image must already be local and
    nothing may be fetched.
    """
    if _LATEX_ENGINE is None:
        assert _DOCKER_FALLBACK
        real_docker_compile_command = build_latex_report.docker_compile_command

        def offline_docker_compile_command(config):
            argv = real_docker_compile_command(config)
            return [*argv[:2], "--pull=never", "--network=none", *argv[2:]]

        monkeypatch.setattr(
            build_latex_report, "docker_compile_command", offline_docker_compile_command
        )
    folder = tmp_path / "report"
    folder.mkdir()
    (folder / "figura_url.png").write_bytes(_PNG_1PX)
    url = "https://observable.invalid/stats?year=2026&sort=desc&page_size=10"
    (folder / "body.md").write_text(
        f"# Resultados <{url}>\n\n![Fuente: <{url}>](figura_url.png)\n",
        encoding="utf-8",
    )
    (folder / "report.yml").write_text(
        "route: technical\n"
        "backend: latex\n"
        "template: plain\n"
        "pdf: build/main.pdf\n"
        "metadata:\n"
        "  title: Prueba de enlaces en titulos\n"
        "  student: Alejandro Padilla\n",
        encoding="utf-8",
    )

    config = build_latex_report.build(folder, compile_pdf=True)

    tex = config.tex_path.read_text(encoding="utf-8")
    assert r"\url{" + url + "}" in tex
    pdf = config.pdf_path
    assert pdf.is_file()
    assert pdf.stat().st_size > 0
    assert pdf.read_bytes().startswith(b"%PDF")

    if pypdf is not None:
        reader = pypdf.PdfReader(str(pdf))
        uris = {
            annotation.get_object()["/A"]["/URI"]
            for page in reader.pages
            for annotation in (page.get("/Annots") or [])
        }
        assert url in uris
