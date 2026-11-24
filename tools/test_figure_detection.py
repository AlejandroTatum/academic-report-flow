"""Tests for figure detection in the LaTeX renderer.

`{{HAS_FIGURES}}` and `{{LIST_OF_FIGURES}}` decide whether the rendered
document gets a list of figures. Detection has to run against the Markdown
source, because that is where the `![caption](path)` syntax exists. Once the
body has been converted the images are already `\\includegraphics` commands
and the Markdown pattern can never match again.

These tests pin the observable behaviour:
  1. A body containing a Markdown image produces a list of figures.
  2. A body with no images does not.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import build_latex_report  # noqa: E402
import report_config  # noqa: E402

BODY_WITH_FIGURE = """# Section

Some prose before the figure.

![A flow diagram. Source: own elaboration.](../assets/flow.png)

Some prose after the figure.
"""

BODY_WITHOUT_FIGURE = """# Section

Only prose here, no images at all.
"""


# Every template must honour figure detection. `unl-report.tex` originally
# exposed no {{LIST_OF_FIGURES}} placeholder at all, so an academic report with
# figures silently got no figure index — and the placeholder test only checked
# the plain template, so nothing caught it.
TEMPLATE_KEYS = ("unl", "plain", "chamba_overleaf")
# AA reports (the UNL template) never print a list of figures; the other
# academic templates still list them when the body has images.
LISTING_TEMPLATE_KEYS = ("plain", "chamba_overleaf")


def make_config(
    tmp_path: Path, body: str, template: str = "plain",
) -> "report_config.ReportConfig":
    import yaml

    folder = tmp_path / "r"
    folder.mkdir(parents=True, exist_ok=True)
    raw = {
        "type": "technical_report",
        "backend": "latex",
        "output": "pdf",
        "template": template,
        "metadata": {"title": "T", "subject": "S", "teacher": "D", "student": "A"},
        "body": "body.md",
    }
    (folder / "report.yml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    (folder / "body.md").write_text(body, encoding="utf-8")
    return report_config.ReportConfig.load(folder)


@pytest.mark.parametrize("template", LISTING_TEMPLATE_KEYS)
def test_markdown_image_produces_a_list_of_figures(
    tmp_path: Path, template: str,
) -> None:
    config = make_config(tmp_path, BODY_WITH_FIGURE, template)
    rendered = build_latex_report.render_tex(config)
    assert r"\listoffigures" in rendered


def test_unl_template_with_a_markdown_image_has_no_list_of_figures(tmp_path: Path) -> None:
    config = make_config(tmp_path, BODY_WITH_FIGURE, "unl")
    rendered = build_latex_report.render_tex(config)
    assert r"\includegraphics" in rendered
    assert r"\listoffigures" not in rendered


@pytest.mark.parametrize("template", TEMPLATE_KEYS)
def test_body_without_images_has_no_list_of_figures(
    tmp_path: Path, template: str,
) -> None:
    config = make_config(tmp_path, BODY_WITHOUT_FIGURE, template)
    rendered = build_latex_report.render_tex(config)
    assert r"\listoffigures" not in rendered


@pytest.mark.parametrize("template", TEMPLATE_KEYS)
def test_template_exposes_the_figure_list_placeholder(template: str) -> None:
    r"""Every template must have somewhere to put the list.

    Only `{{LIST_OF_FIGURES}}` is required. The renderer already substitutes an
    empty string when the body has no images, so a bare placeholder is
    self-gating; the extra `{{HAS_FIGURES}}` flag that `plain-report.tex` uses
    is one valid implementation, not a contract.
    """
    path = build_latex_report.resolve_template(template)
    tex = path.read_text(encoding="utf-8")
    assert "{{LIST_OF_FIGURES}}" in tex, f"{path.name} exposes no figure list"


# ---------------------------------------------------------------------------
# Figure sizing derives from the image's own aspect ratio, not a filename (#31)
# ---------------------------------------------------------------------------


def test_wide_image_outside_the_old_filename_table_gets_aspect_and_height_cap(
    tmp_path: Path,
) -> None:
    """The removed filename table never named this image; it still gets sized.

    Shape matches the wide Mermaid figure from #31 (2768x514) that rendered
    unreadably small labels under the old fixed ``width=0.86\\textwidth`` with
    no height constraint at all.
    """
    from PIL import Image

    config = make_config(
        tmp_path,
        "# Section\n\n"
        "![A wide diagram. Source: own elaboration.](../assets/widediagram.png)\n",
        "plain",
    )
    assets = config.folder / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (2768, 514), color="white").save(assets / "widediagram.png")
    # build() always mkdirs the build directory before rendering (figure paths
    # resolve relative to it); mirror that ordering here.
    config.tex_path.parent.mkdir(parents=True, exist_ok=True)

    rendered = build_latex_report.render_tex(config)

    assert "widediagram.png" in rendered
    assert r"\textheight" in rendered
    assert r"\begin{figure}[H]" not in rendered


def test_unresolvable_figure_falls_back_to_the_historical_width_only_default(
    tmp_path: Path,
) -> None:
    """A figure that never resolves on disk keeps the old, safe fallback.

    ``validate_figure_paths`` reports the missing figure as its own error
    before compilation; this renderer must not crash trying to read pixels
    from a file that is not there.
    """
    config = make_config(
        tmp_path,
        "# Section\n\n"
        "![Missing figure. Source: own elaboration.](../assets/does_not_exist.png)\n",
        "plain",
    )
    config.tex_path.parent.mkdir(parents=True, exist_ok=True)

    rendered = build_latex_report.render_tex(config)

    assert r"width=0.86\textwidth,keepaspectratio" in rendered


# ---------------------------------------------------------------------------
# Floats stay bound to their section (#38): [!htbp] lets a figure drift within
# the page, but nothing bounded how far until a \FloatBarrier closes every
# section.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("template", TEMPLATE_KEYS)
def test_figure_is_emitted_with_float_placement(tmp_path: Path, template: str) -> None:
    """Figures float ([!htbp], h first: S4), not fixed ([H]), across every template (#36)."""
    config = make_config(tmp_path, BODY_WITH_FIGURE, template)
    config.tex_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = build_latex_report.render_tex(config)
    assert r"\begin{figure}[!htbp]" in rendered


@pytest.mark.parametrize("template", (*TEMPLATE_KEYS, "ape"))
def test_template_loads_placeins_with_subsection_barrier(template: str) -> None:
    r"""A float may drift within its subsection, but never past the next one.

    ``\usepackage{float}`` alone lets [tbp] figures cross into the next
    section; ``placeins`` with the ``section`` option bounds them by
    ``\section`` only, so in a multi-exercise report each figure landed under
    the next exercise (#82). placeins has no ``subsection`` option, so the
    template prefixes ``\subsection`` with ``\FloatBarrier`` itself, after any
    ``titlesec`` load that would redefine it. test_float_barrier_compile.py
    proves the effect on a real PDF.
    """
    path = build_latex_report.resolve_template(template)
    tex = path.read_text(encoding="utf-8")
    assert re.search(r"\\usepackage(\[[^\]]*\bsection\b[^\]]*\])\{placeins\}", tex), (
        f"{path.name} never loads placeins with the section option"
    )
    patch = r"\renewcommand{\subsection}{\FloatBarrier\ReportOriginalSubsection}"
    assert patch in tex, f"{path.name} never puts a float barrier before \\subsection"
    if r"\usepackage{titlesec}" in tex:
        assert tex.index(r"\usepackage{titlesec}") < tex.index(patch)


@pytest.mark.parametrize("template", TEMPLATE_KEYS)
def test_template_localizes_the_figure_list_title(template: str) -> None:
    r"""The documents are written in Spanish; the index heading must match.

    Without `\renewcommand{\listfigurename}{...}`, `\listoffigures` prints the
    LaTeX default "List of Figures" in the middle of a Spanish report.
    """
    path = build_latex_report.resolve_template(template)
    tex = path.read_text(encoding="utf-8")
    assert r"\renewcommand{\listfigurename}" in tex, (
        f"{path.name} emits a figure list but never localizes its title"
    )
