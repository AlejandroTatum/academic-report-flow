"""``citation_style`` in the LaTeX build: IEEE stays byte-identical, APA is opt-in."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import build_latex_report  # noqa: E402
import report_config  # noqa: E402

IEEE_OPTIONS = "backend=biber,style=ieee,sorting=none,hyperref=true"
APA_OPTIONS = "backend=biber,style=apa,hyperref=true"
TEMPLATES = ["unl", "plain", "ape", "chamba_overleaf", "ieee"]
BODY = "Los procesos [@a2018, b2019] planifican tareas.\n"
BIB = "@book{a2018, author={A, B}, title={T}, year={2018}}\n@book{b2019, author={C, D}, title={U}, year={2019}}\n"


def render(folder: Path, template: str, **extra: object) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    raw = {
        "type": "technical_report",
        "backend": "latex",
        "output": "pdf",
        "template": template,
        "metadata": {"title": "T", "subject": "S", "student": "E", "teacher": "P"},
        "body": "body.md",
        "bibliography": "sources.bib",
        **extra,
    }
    (folder / "report.yml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    (folder / "body.md").write_text(BODY, encoding="utf-8")
    (folder / "sources.bib").write_text(BIB, encoding="utf-8")
    return build_latex_report.render_tex(report_config.ReportConfig.load(folder))


@pytest.mark.parametrize("template", ["unl-report", "plain-report", "ape-report", "chamba-overleaf", "ieee-report"])
def test_templates_use_the_options_placeholder(template: str) -> None:
    text = (ROOT / "templates" / f"{template}.tex").read_text(encoding="utf-8")
    assert r"\usepackage[{{BIBLATEX_OPTIONS}}]{biblatex}{{BIBLATEX_SETUP}}" in text
    assert "style=ieee" not in text


@pytest.mark.parametrize("template", TEMPLATES)
def test_default_renders_ieee_unchanged(tmp_path: Path, template: str) -> None:
    tex = render(tmp_path, template)
    assert rf"\usepackage[{IEEE_OPTIONS}]{{biblatex}}" + "\n" in tex
    assert r"\cite{a2018,b2019}" in tex
    assert "parencite" not in tex
    assert "spanish-apa" not in tex


@pytest.mark.parametrize("template", TEMPLATES)
def test_explicit_ieee_matches_default(tmp_path: Path, template: str) -> None:
    assert render(tmp_path / "a", template) == render(tmp_path / "b", template, citation_style="ieee")


@pytest.mark.parametrize("template", TEMPLATES)
def test_apa_renders_apa_options_and_parencite(tmp_path: Path, template: str) -> None:
    tex = render(tmp_path, template, citation_style="apa")
    assert rf"\usepackage[{APA_OPTIONS}]{{biblatex}}" in tex
    assert r"\parencite{a2018,b2019}" in tex
    assert r"\cite{" not in tex
    assert "style=ieee" not in tex
    assert r"\DeclareLanguageMapping{spanish}{spanish-apa}" in tex
    assert r"\usepackage{csquotes}" in tex


@pytest.mark.parametrize("template", TEMPLATES)
def test_apa_titles_the_reference_list_referencias(tmp_path: Path, template: str) -> None:
    # APA 7 (Spanish) names the list "Referencias", whatever the template's default.
    tex = render(tmp_path, template, citation_style="apa")
    assert r"\printbibliography[title={Referencias}]" in tex


@pytest.mark.parametrize("text", ["[@a; @b]", "[@a;@b]", "[@a, @b]", "[@a, b]"])
def test_multi_key_citation_becomes_a_key_list(text: str) -> None:
    assert build_latex_report.convert_inline(text) == r"\cite{a,b}"


def test_single_key_citation_unchanged() -> None:
    assert build_latex_report.convert_inline("[@a2018]") == r"\cite{a2018}"


def test_apa_setup_uses_spanish_y_delimiter() -> None:
    setup = build_latex_report.BIBLATEX_SETUP["apa"]
    assert r"\DeclareDelimFormat[bib,biblist]{finalnamedelim}" in setup
    assert r"\DeclareDelimFormat[parencite]{finalnamedelim}" in setup
    assert r"\addspace y\space" in setup
    assert "&" not in setup


def test_apa_setup_spaces_entries_and_softens_url_breaks() -> None:
    setup = build_latex_report.BIBLATEX_SETUP["apa"]
    assert r"\setlength{\bibitemsep}{0.5\baselineskip}" in setup
    assert r"\urlstyle{same}" in setup
    assert r"\AtEndPreamble{" in setup
    assert r"\def\UrlBreaks{\do\/\do\.\do\-}" in setup
    for counter in ("biburlbreakpenalty", "biburlbigbreakpenalty", "biburlnumpenalty"):
        assert counter in setup


def test_apa_setup_sets_ragged_bibliography_and_body_url_breaks() -> None:
    setup = build_latex_report.BIBLATEX_SETUP["apa"]
    # APA reference lists are left-aligned; justified lines open wide gaps.
    assert r"\AtBeginBibliography{\raggedright}" in setup
    # Body \url/\href must not break right after "https:" either.
    assert r"\def\UrlBigBreaks{}" in setup


def test_apa_options_keep_biblatex_apa_sorting() -> None:
    # APA 7 (9.47) lists no-date works before dated ones of the same author;
    # biblatex-apa's own sorting=apa does that, sorting=nyt does not.
    options = build_latex_report.BIBLATEX_OPTIONS["apa"]
    assert "sorting=" not in options


def test_apa_setup_uses_spanish_retrieval_wording() -> None:
    # APA 7 in Spanish: "Recuperado el <fecha>, de <URL>", not "Consultado ... desde".
    setup = build_latex_report.BIBLATEX_SETUP["apa"]
    assert r"\DefineBibliographyStrings{spanish}{retrieved={Recuperado},from={de}}" in setup


def test_ieee_setup_stays_empty() -> None:
    assert build_latex_report.BIBLATEX_SETUP["ieee"] == ""
