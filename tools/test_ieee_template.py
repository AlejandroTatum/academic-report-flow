"""Tests for ``format: ieee`` (ieee-essay-format T2, S1-S6).

`format: ieee` renders an IEEE conference-style essay: A4, two columns, Times,
a 24 pt title, 10 pt body, no cover and no logo, Roman-numbered sections with
lettered subsections, and a biblatex ``style=ieee`` list titled "Referencias".

These tests pin:
  1. the format table: required metadata, cover defaults, no fixed sections;
  2. selection: the default template, the explicit ``template:`` override;
  3. render_tex: the author block, the abstract and keywords split off the
     ``# Resumen`` section, free sections, column-width tables and figures;
  4. the validators: no cover/logo demands and no fixed-heading typeset check;
  5. a real two-column PDF (skipped without a LaTeX engine or local image).
"""
from __future__ import annotations

import base64
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import build_latex_report  # noqa: E402
import validate_report  # noqa: E402
from report_config import FORMAT_COVER_DEFAULTS, FORMAT_REQUIRED_METADATA, ReportConfig  # noqa: E402
from test_latex_links import _DOCKER_FALLBACK, _LATEX_ENGINE  # noqa: E402

IEEE_TEMPLATE = ROOT / "templates" / "ieee-report.tex"
A4_PAGE_SIZE = "595.276 x 841.89 pts (A4)"
_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

AFFILIATION = "Facultad de Ingeniería, Universidad Nacional de Loja, Loja, Ecuador"
EMAIL = "camila.jaramillo@unl.edu.ec"

ESSAY_BODY = """# Resumen

Este ensayo compara la simulación determinista con la estocástica.

Se analizan colas M/M/1 y sus métricas.

Palabras clave— colas; simulación; eventos discretos; M/M/1

# Introducción

La simulación estudia sistemas reales [@fuente2026].

## Antecedentes

Texto de antecedentes.

# Conclusiones

Cierre del ensayo.
"""

SOURCE_BIB = """@book{fuente2026,
  author = {Autor, Ana},
  title = {Simulación de sistemas},
  publisher = {Editorial Universitaria},
  year = {2026},
}
"""

TABLE_AND_FIGURE_BODY = """# Introducción

Tabla 1. Métricas.

| Métrica | Valor | Unidad |
|---|---|---|
| Utilización | 0.8 | % |

![Cola M/M/1](cola.png)
"""


def ieee_metadata(**extra: str) -> dict:
    return {
        "title": "Simulación determinista frente a estocástica",
        "student": "Camila Jaramillo",
        "date": "9 de octubre de 2026",
        **extra,
    }


def make_config(
    tmp_path: Path,
    body: str = ESSAY_BODY,
    metadata: dict | None = None,
    raw: dict | None = None,
) -> ReportConfig:
    folder = tmp_path / "r"
    folder.mkdir(parents=True, exist_ok=True)
    written = {
        "type": "technical_report",
        "backend": "latex",
        "output": "pdf",
        "pdf": "build/main.pdf",
        "body": "body.md",
        "format": "ieee",
        "bibliography": "sources.bib",
        "metadata": metadata if metadata is not None else ieee_metadata(),
    }
    written.update(raw or {})
    (folder / "report.yml").write_text(yaml.safe_dump(written), encoding="utf-8")
    (folder / "body.md").write_text(body, encoding="utf-8")
    (folder / "sources.bib").write_text(SOURCE_BIB, encoding="utf-8")
    (folder / "cola.png").write_bytes(_PNG_1PX)
    return ReportConfig.load(folder)


def render(tmp_path: Path, **kwargs) -> str:
    return build_latex_report.render_tex(make_config(tmp_path, **kwargs))


def template_name(config: ReportConfig) -> str:
    return build_latex_report.resolve_template(build_latex_report.template_key_for(config)).name


# ---------------------------------------------------------------------------
# The format table
# ---------------------------------------------------------------------------


def test_ieee_is_a_known_format_with_the_libre_metadata(tmp_path: Path) -> None:
    assert FORMAT_REQUIRED_METADATA["ieee"] == ("title", "student", "date")
    config = make_config(tmp_path)
    assert config.format_is_known
    assert config.format_required_metadata == ("title", "student", "date")


def test_ieee_format_has_no_cover_and_no_logo(tmp_path: Path) -> None:
    assert FORMAT_COVER_DEFAULTS["ieee"] == {
        "required": False, "body_starts_on_page": 1, "logo_required": False,
    }
    config = make_config(tmp_path)
    assert config.cover_value("required", default=True) is False
    assert config.cover_value("body_starts_on_page", default=2) == 1
    assert config.cover_value("logo_required", default=True) is False


def test_ieee_has_no_fixed_section_spec() -> None:
    assert "ieee" not in validate_report.SECTION_SPECS


def test_affiliation_and_email_resolve_through_metadata_aliases(tmp_path: Path) -> None:
    config = make_config(
        tmp_path, metadata=ieee_metadata(afiliacion=AFFILIATION, correo=EMAIL)
    )
    assert config.metadata["affiliation"] == AFFILIATION
    assert config.metadata["email"] == EMAIL


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def test_ieee_format_renders_the_ieee_template_by_default(tmp_path: Path) -> None:
    assert template_name(make_config(tmp_path)) == "ieee-report.tex"


def test_ieee_format_beats_the_route_template_default(tmp_path: Path) -> None:
    config = make_config(tmp_path, raw={"route": "technical"})
    assert template_name(config) == "ieee-report.tex"


def test_ieee_format_can_still_ask_for_another_template(tmp_path: Path) -> None:
    config = make_config(tmp_path, raw={"template": "plain"})
    assert template_name(config) == "plain-report.tex"


@pytest.mark.parametrize("key", ["ieee", "ieee_report", "IEEE"])
def test_ieee_template_keys_resolve(key: str) -> None:
    assert build_latex_report.resolve_template(key) == IEEE_TEMPLATE


def test_ieee_bibliography_is_titled_referencias(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert build_latex_report.bibliography_title(config, "ieee") == "Referencias"
    assert build_latex_report.bibliography_title(config, "ieee_report") == "Referencias"


def test_other_formats_keep_their_template(tmp_path: Path) -> None:
    for fmt, name in (("aa", "aa-report.tex"), ("ape", "ape-report.tex"), ("acd", "acd-report.tex")):
        config = make_config(tmp_path / fmt, raw={"format": fmt})
        assert template_name(config) == name


# ---------------------------------------------------------------------------
# The template file
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def template() -> str:
    return IEEE_TEMPLATE.read_text(encoding="utf-8")


def test_template_is_an_a4_ieeetran_conference_paper(template: str) -> None:
    options = re.search(r"\\documentclass\[([^\]]*)\]\{IEEEtran\}", template)
    assert options, "IEEEtran class not declared"
    assert {"conference", "a4paper"} <= set(options.group(1).replace(" ", "").split(","))


def test_template_sets_times_through_fontspec(template: str) -> None:
    assert r"\usepackage{fontspec}" in template
    assert "TeX Gyre Termes" in template


def test_template_uses_spanish_labels_and_a_spanish_abstract_name(template: str) -> None:
    assert "babel" in template and "spanish" in template
    assert r"\renewcommand{\IEEEkeywordsname}{Palabras clave}" in template


@pytest.mark.parametrize(
    "placeholder",
    [
        "{{BIBLATEX_OPTIONS}}", "{{BIBLATEX_SETUP}}", "{{LISTING_PREAMBLE}}", "{{BIB_FILE}}",
        "{{HAS_BIB}}", "{{TITLE}}", "{{IEEE_AUTHOR}}", "{{IEEE_ABSTRACT}}", "{{BODY}}",
        "{{PRINT_BIBLIOGRAPHY}}",
    ],
)
def test_template_carries_every_placeholder_it_needs(template: str, placeholder: str) -> None:
    assert placeholder in template


def test_template_has_no_cover_logo_or_hardcoded_affiliation(template: str) -> None:
    assert r"\begin{titlepage}" not in template
    assert "includegraphics" not in template
    assert "Universidad Nacional de Loja" not in template


def test_template_keeps_the_ieee_biblatex_style(template: str) -> None:
    assert r"\usepackage[{{BIBLATEX_OPTIONS}}]{biblatex}{{BIBLATEX_SETUP}}" in template
    assert "style=ieee" not in template


# ---------------------------------------------------------------------------
# render_tex
# ---------------------------------------------------------------------------


def test_render_leaves_no_unfilled_placeholder(tmp_path: Path) -> None:
    assert "{{" not in render(tmp_path)


def test_render_uses_the_ieee_biblatex_options_and_cites_with_brackets(tmp_path: Path) -> None:
    tex = render(tmp_path)
    assert r"\usepackage[backend=biber,style=ieee,sorting=none,hyperref=true]{biblatex}" in tex
    assert r"\cite{fuente2026}" in tex
    assert r"\printbibliography[title={Referencias}]" in tex


def test_abstract_is_one_paragraph_in_the_abstract_environment(tmp_path: Path) -> None:
    tex = render(tmp_path)
    block = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.DOTALL)
    assert block, "no abstract environment"
    text = block.group(1).strip()
    assert "\n\n" not in text
    assert text == (
        "Este ensayo compara la simulación determinista con la estocástica. "
        "Se analizan colas M/M/1 y sus métricas."
    )


def test_keywords_go_in_ieeekeywords_without_their_label(tmp_path: Path) -> None:
    tex = render(tmp_path)
    block = re.search(r"\\begin\{IEEEkeywords\}(.*?)\\end\{IEEEkeywords\}", tex, re.DOTALL)
    assert block, "no IEEEkeywords environment"
    assert block.group(1).strip() == "colas; simulación; eventos discretos; M/M/1"
    assert "Palabras clave—" not in tex


def test_resumen_does_not_render_as_a_numbered_section(tmp_path: Path) -> None:
    tex = render(tmp_path)
    assert r"\section{Resumen}" not in tex
    assert r"\section{Introducción}" in tex
    assert r"\subsection{Antecedentes}" in tex
    assert r"\section{Conclusiones}" in tex


def test_abstract_precedes_the_body(tmp_path: Path) -> None:
    tex = render(tmp_path)
    assert tex.index(r"\maketitle") < tex.index(r"\begin{abstract}") < tex.index(r"\section{Introducción}")


def test_no_resumen_heading_means_no_abstract(tmp_path: Path) -> None:
    tex = render(tmp_path, body="# Introducción\n\nTexto [@fuente2026].\n")
    assert r"\begin{abstract}" not in tex
    assert r"\begin{IEEEkeywords}" not in tex
    assert r"\section{Introducción}" in tex


def test_resumen_without_a_keywords_line_renders_only_the_abstract(tmp_path: Path) -> None:
    tex = render(tmp_path, body="# Resumen\n\nSolo resumen.\n\n# Introducción\n\nTexto.\n")
    assert r"\begin{abstract}" in tex
    assert r"\begin{IEEEkeywords}" not in tex


def test_author_block_prints_name_affiliation_and_email(tmp_path: Path) -> None:
    tex = render(tmp_path, metadata=ieee_metadata(affiliation=AFFILIATION, email=EMAIL))
    assert r"\IEEEauthorblockN{Camila Jaramillo" in tex
    assert AFFILIATION in tex
    assert "camila.jaramillo@unl.edu.ec" in tex


def test_author_block_omits_affiliation_and_email_when_absent(tmp_path: Path) -> None:
    tex = render(tmp_path)
    assert r"\IEEEauthorblockN{Camila Jaramillo}" in tex
    assert r"\IEEEauthorblockA" not in tex
    assert "Universidad Nacional de Loja" not in tex


def test_author_block_omits_only_the_missing_line(tmp_path: Path) -> None:
    tex = render(tmp_path, metadata=ieee_metadata(email=EMAIL))
    assert r"\IEEEauthorblockA{" in tex
    assert "Facultad" not in tex


def test_title_is_escaped_into_the_title_command(tmp_path: Path) -> None:
    tex = render(tmp_path, metadata=ieee_metadata(title="Colas M/M/1 & simulación"))
    assert r"\title{Colas M/M/1 \& simulación}" in tex


def test_tables_fit_one_column_and_never_use_longtable(tmp_path: Path) -> None:
    tex = render(tmp_path, body=TABLE_AND_FIGURE_BODY)
    assert r"\columnwidth" in tex
    assert "xltabular" not in tex
    assert "longtable" not in tex
    assert r"\textwidth" not in tex.split(r"\begin{document}")[1]


def test_figures_are_sized_to_the_column(tmp_path: Path) -> None:
    tex = render(tmp_path, body=TABLE_AND_FIGURE_BODY)
    figure = re.search(r"\\includegraphics\[([^\]]*)\]", tex)
    assert figure
    assert r"\columnwidth" in figure.group(1)
    assert r"\textwidth" not in figure.group(1)


def test_column_tables_are_separated_from_the_surrounding_text(tmp_path: Path) -> None:
    # A tabularx block adds no vertical space of its own (xltabular does): without
    # an explicit gap the bottom rule touches the next paragraph's first line.
    tex = render(tmp_path, body=TABLE_AND_FIGURE_BODY)
    block = re.search(r"(.*)\n\\begingroup\n.*?\\end\{tabularx\}\n\\endgroup\n(.*)", tex, re.S)
    assert block
    assert block.group(1).rstrip().endswith(r"\par\medskip")
    assert block.group(2).lstrip().startswith(r"\par\medskip")


def test_column_tables_start_without_paragraph_indent(tmp_path: Path) -> None:
    # The table opens a paragraph: without \noindent it inherits \parindent and
    # the \columnwidth-wide tabularx overflows the column by that indent.
    tex = render(tmp_path, body=TABLE_AND_FIGURE_BODY)
    assert re.search(r"\\noindent\s*\n\\begin\{tabularx\}\{\\columnwidth\}", tex)


def test_long_affiliation_wraps_inside_the_text_width() -> None:
    # IEEEtran sets the author block in a tabular, so a long affiliation never
    # breaks and overflows the margins; a centred parbox lets it wrap.
    block = build_latex_report.ieee_author_block({"student": "Ana Pérez", "affiliation": "Facultad X, Universidad Y", "email": "a@b.ec"})
    assert r"\parbox{\textwidth}{\centering\textsuperscript{1}Facultad X, Universidad Y}" in block
    assert block.endswith(r"\\a@b.ec}")


def test_pinned_figures_load_the_float_package(tmp_path: Path) -> None:
    # figure_placement: here renders figures as [H], which only float.sty defines;
    # without it lualatex stops with "Unknown float option `H'" and no PDF.
    tex = render(tmp_path, body=TABLE_AND_FIGURE_BODY, raw={"figure_placement": "here"})
    assert r"\begin{figure}[H]" in tex
    assert r"\usepackage{float}" in tex.split(r"\begin{document}")[0]


@pytest.mark.parametrize("fmt", ["aa", "ape", "acd"])
def test_other_formats_keep_full_width_tables_and_figures(tmp_path: Path, fmt: str) -> None:
    metadata = {
        **ieee_metadata(), "subject": "S", "teacher": "P", "cycle": "c", "unit": "u",
        "learning_outcome": "l", "practice_number": "1", "practice_type": "t",
        "schedule": "s", "place": "p", "planned_time": "4",
    }
    tex = render(tmp_path, body=TABLE_AND_FIGURE_BODY, metadata=metadata, raw={"format": fmt})
    assert r"\columnwidth" not in tex
    assert "xltabular" in tex


def test_split_ieee_abstract_returns_the_remaining_markdown() -> None:
    abstract, keywords, rest = build_latex_report.split_ieee_abstract(ESSAY_BODY)
    assert abstract.startswith("Este ensayo compara")
    assert keywords == "colas; simulación; eventos discretos; M/M/1"
    assert rest.lstrip().startswith("# Introducción")
    assert "Resumen" not in rest


def test_split_ieee_abstract_without_resumen_changes_nothing() -> None:
    body = "# Introducción\n\nTexto.\n"
    assert build_latex_report.split_ieee_abstract(body) == (None, None, body)


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def test_ieee_report_without_cover_or_images_has_no_cover_or_logo_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = make_config(tmp_path)
    config.pdf_path.parent.mkdir(parents=True, exist_ok=True)
    config.pdf_path.write_bytes(b"%PDF-1.4\n")
    pages = ["Título del ensayo\nResumen— texto\nI. INTRODUCCIÓN\nTexto.", "II. DESARROLLO\nMás texto."]
    monkeypatch.setattr(validate_report, "pdf_text_pages", lambda _pdf: pages)
    monkeypatch.setattr(
        validate_report, "pdfinfo", lambda _pdf: {"Pages": "2", "Page size": A4_PAGE_SIZE}
    )
    # No embedded image at all: the logo check must not ask for one.
    monkeypatch.setattr(
        validate_report, "run", lambda cmd: type("P", (), {"stdout": "", "returncode": 0})()
    )

    result = validate_report.pdf_layout_validation(config)

    assert not any("logo UNL" in e for e in result.errors), result.errors
    assert not any("portada" in e.lower() for e in result.errors), result.errors


def test_ieee_template_passes_the_latex_rule_check_without_one_and_a_half_spacing(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.tex_path.parent.mkdir(parents=True, exist_ok=True)
    config.tex_path.write_text(build_latex_report.render_tex(config), encoding="utf-8")

    result = validate_report.latex_log_validation(config)

    assert not any("reglas obligatorias" in e for e in result.errors), result.errors
    assert r"\onehalfspacing" not in config.tex_path.read_text(encoding="utf-8")


def test_other_formats_still_require_one_and_a_half_spacing(tmp_path: Path) -> None:
    config = make_config(tmp_path, raw={"format": "libre", "format_spec": "x", "template": "plain"})
    config.tex_path.parent.mkdir(parents=True, exist_ok=True)
    config.tex_path.write_text("\\usepackage{hyperref}\\Needspace\\parindent", encoding="utf-8")

    result = validate_report.latex_log_validation(config)

    assert any("onehalfspacing" in e for e in result.errors)


# ---------------------------------------------------------------------------
# A real build
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    _LATEX_ENGINE is None and not _DOCKER_FALLBACK,
    reason="no local LaTeX engine and no already-present local texlive/texlive:latest image",
)
def test_ieee_builds_a_two_column_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if _LATEX_ENGINE is None:
        real = build_latex_report.docker_compile_command

        def offline(config):
            argv = real(config)
            return [*argv[:2], "--pull=never", "--network=none", *argv[2:]]

        monkeypatch.setattr(build_latex_report, "docker_compile_command", offline)
    config = make_config(
        tmp_path,
        body=ESSAY_BODY + "\n" + TABLE_AND_FIGURE_BODY.replace("# Introducción", "# Desarrollo"),
        metadata=ieee_metadata(affiliation=AFFILIATION, email=EMAIL),
    )

    built = build_latex_report.build(config.folder, compile_pdf=True)

    assert built.pdf_path.read_bytes().startswith(b"%PDF")
    if not shutil.which("pdftotext"):
        return
    text = subprocess.run(
        ["pdftotext", "-layout", str(built.pdf_path), "-"], capture_output=True, text=True, check=True
    ).stdout
    assert "Resumen—" in text
    assert "Palabras clave" in text
    # IEEEtran sets section titles in small caps, which extract as lowercase.
    assert re.search(r"^\s*I\.\s+Introducción", text, re.MULTILINE)
    assert re.search(r"^\s*A\.\s+Antecedentes", text, re.MULTILINE)
    assert re.search(r"^\s*Referencias\s*$", text, re.MULTILINE)
    assert "[1]" in text
