"""Tests for the AA report template (aa-acd-templates T3, S1/S2/S4/S5/S8).

`format: aa` ("Aprendizaje autónomo") renders the approved AA-B editorial
design: a creative first page (letterhead, an identification "ficha" in the
left margin, a large serif title) and a conventional full-width report from
there on, with inline section numbers, Source Serif 4 / Source Sans 3 /
Source Code Pro and the crest green.

These tests pin:
  1. the template file, its placeholders and the approved design facts;
  2. render_tex output: the ficha rows (order, escaping, group members, rows
     that are omitted when their metadata is absent), the letterhead and the
     kicker, and the annexes-after-bibliography slot;
  3. selection: the default template for `format: aa`, the explicit
     `template:` override, and no newly required metadata;
  4. the ficha zone: floats, display math, code and tables that would start
     beside the ficha are pushed below it by the template, never by the
     author, proven on real PDFs (skipped without a LaTeX engine or image);
  5. AA never prints a list of figures (#85).
"""
from __future__ import annotations

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
from report_config import FORMAT_REQUIRED_METADATA, ReportConfig  # noqa: E402
from test_latex_links import _DOCKER_FALLBACK, _LATEX_ENGINE  # noqa: E402
from validate_report import metadata_validation  # noqa: E402


@pytest.fixture(autouse=True)
def _never_publish_outside_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Leak-proof by construction: a build here can only publish into a scratch dir.

    The repo-root conftest.py already pins REPORT_CONTENT_ROOT to a per-session
    temp dir. This adds the monkeypatch ``test_content_root.py`` uses, so a
    test that forgets ``publish_global: false`` (or a module that bound the
    root before the pin) still copies its PDF under tmp, never into the real
    ``outputs/<materia>/``.
    """
    import importlib

    sandbox = tmp_path_factory.mktemp("global-outputs")
    for name in ("output_router", "report_config", "build_latex_report", "validate_report"):
        module = importlib.import_module(name)
        if hasattr(module, "GLOBAL_OUTPUTS"):
            monkeypatch.setattr(module, "GLOBAL_OUTPUTS", sandbox)
    return sandbox


AA_TEMPLATE = ROOT / "templates" / "aa-report.tex"
UNL_TEMPLATE = ROOT / "templates" / "unl-report.tex"

AA_PLACEHOLDERS = (
    "{{AA_LABEL}}",
    "{{AA_HEADING}}",
    "{{AA_FICHA}}",
    "{{UNIVERSITY}}",
    "{{FACULTY}}",
    "{{CAREER}}",
    "{{TITLE}}",
    "{{SUBJECT}}",
    "{{STUDENT}}",
    "{{APE_LOGO_PATH}}",
    "{{BODY}}",
    "{{BIBLATEX_OPTIONS}}",
    "{{BIB_FILE}}",
    "{{HAS_BIB}}",
    "{{PRINT_BIBLIOGRAPHY}}",
    "{{AFTER_BIBLIOGRAPHY}}",
    "{{FRONT_MATTER}}",
    "{{AI_DECLARATION}}",
)

# The ficha entries in the mockup's reading order:
# (label printed above the value, metadata key that fills it).
FICHA_ROWS = (
    ("Estudiante", "student"),
    ("Asignatura", "subject"),
    ("Ciclo", "cycle"),
    ("Unidad", "unit"),
    ("Resultado de aprendizaje", "learning_outcome"),
    ("Actividad", "practice_number"),
    ("Docente", "teacher"),
    ("Fecha de entrega", "date"),
    ("Tiempo en el sílabo", "planned_time"),
)

AA_HEADINGS = (
    "Objetivo(s)",
    "Introducción",
    "Desarrollo",
    "Conclusiones",
)

BASE_RAW = {
    "type": "technical_report",
    "backend": "latex",
    "output": "pdf",
    "pdf": "build/report.pdf",
    "body": "body.md",
    "format": "aa",
}

SOURCE_BIB = """@book{fuente2026,
  author = {Autor, Ana},
  title = {Sistemas operativos modernos},
  publisher = {Editorial Universitaria},
  year = {2026},
}
"""


def required_aa_metadata() -> dict:
    """Exactly what `format: aa` has always required, nothing more."""
    return {
        "title": "Comparación de algoritmos de planificación",
        "subject": "Sistemas Operativos",
        "teacher": "Ing. Luis Cueva",
        "student": "Camila Jaramillo",
        "date": "9 de octubre de 2026",
    }


def full_aa_metadata() -> dict:
    return {
        **required_aa_metadata(),
        "cycle": "Cuarto",
        "parallel": "A",
        "unit": "Unidad 2: Gestión de procesos",
        "learning_outcome": "Compara algoritmos de planificación de procesos.",
        "practice_number": "2",
        "planned_time": "4 horas",
    }


def default_aa_body() -> str:
    parts = [f"# {heading}\n\nContenido de {heading}.\n" for heading in AA_HEADINGS]
    # A citation so the IEEE bibliography actually prints (emission is
    # citation-driven, #26).
    parts.insert(1, "\nSegún la literatura [@fuente2026].\n")
    parts.append("# Anexos\n\nContenido de anexos.\n")
    return "\n".join(parts)


def make_render_config(
    tmp_path: Path,
    raw: dict | None = None,
    body: str | None = None,
    metadata: dict | None = None,
) -> ReportConfig:
    folder = tmp_path / "r"
    folder.mkdir(parents=True, exist_ok=True)
    written = dict(BASE_RAW)
    written.update(raw or {})
    written["metadata"] = metadata if metadata is not None else full_aa_metadata()
    (folder / "report.yml").write_text(yaml.safe_dump(written), encoding="utf-8")
    (folder / "body.md").write_text(
        body if body is not None else default_aa_body(), encoding="utf-8"
    )
    (folder / "sources.bib").write_text(SOURCE_BIB, encoding="utf-8")
    return ReportConfig.load(folder)


def render(tmp_path: Path, **kwargs) -> str:
    return build_latex_report.render_tex(make_render_config(tmp_path, **kwargs))


def ficha_of(tex: str, label: str) -> str:
    """The generated ``\\ficha{label}{value}`` entry text."""
    start = tex.index(rf"\ficha{{{label}}}")
    return tex[start: start + 400].split("\n")[0]


# ---------------------------------------------------------------------------
# The template itself
# ---------------------------------------------------------------------------


def test_aa_template_exists() -> None:
    assert AA_TEMPLATE.is_file(), "templates/aa-report.tex must exist"


@pytest.fixture(scope="module")
def aa_template() -> str:
    return AA_TEMPLATE.read_text(encoding="utf-8")


@pytest.mark.parametrize("placeholder", AA_PLACEHOLDERS)
def test_aa_template_exposes_placeholder(aa_template: str, placeholder: str) -> None:
    assert placeholder in aa_template, f"aa template must expose {placeholder}"


@pytest.mark.parametrize("snippet", ["hyperref", "Needspace", "onehalfspacing", "parindent"])
def test_aa_template_satisfies_latex_validator(aa_template: str, snippet: str) -> None:
    assert snippet in aa_template, (
        f"validate_report.py greps the generated .tex for {snippet!r}"
    )


def test_aa_template_has_no_cover_page_and_no_figure_index(aa_template: str) -> None:
    assert "titlepage" not in aa_template, "page 1 is the letterhead and ficha, not a cover"
    assert "{{LIST_OF_FIGURES}}" not in aa_template, "AA never prints a list of figures (#85)"


def test_aa_template_carries_the_approved_design(aa_template: str) -> None:
    assert "Source Serif 4" in aa_template and "Source Sans 3" in aa_template
    assert "Source Code Pro" in aa_template
    assert "1F4E3D" in aa_template, "crest green accent"
    assert r"\selectfont {{AA_HEADING}}\par" in aa_template, "the large serif title (default: Aprendizaje autónomo)"
    assert "Datos de identificación" in aa_template, "the ficha heading"
    assert "ACTIVIDAD" in aa_template, "the kicker above the title"
    assert "fancyhdr" in aa_template, "discreet running header and footer"
    assert r"\pageref{LastPage}" in aa_template, "footer shows page n / total"
    assert r"\parshape" in aa_template, "the opening text wraps beside the ficha"


def test_aa_template_falls_back_when_the_fonts_are_not_installed(aa_template: str) -> None:
    """Like the other templates: a missing face degrades, it never fails the build."""
    assert r"\IfFontExistsTF" in aa_template
    assert "TeX Gyre Pagella" in aa_template, "serif fallback"
    assert "TeX Gyre Heros" in aa_template, "sans fallback shared with the other templates"
    assert "TeX Gyre Cursor" in aa_template, "monospace fallback"
    assert "Latin Modern Math" in aa_template, "math fallback"


def test_aa_template_keeps_ieee_citations(aa_template: str, tmp_path: Path) -> None:
    assert "{{BIBLATEX_OPTIONS}}" in aa_template
    assert "style=ieee" in render(tmp_path), "every format cites IEEE by default"


def test_aa_template_alias_resolves_to_the_aa_template() -> None:
    assert build_latex_report.TEMPLATE_ALIASES["aa"] == AA_TEMPLATE
    assert build_latex_report.TEMPLATE_ALIASES["aa_report"] == AA_TEMPLATE


def test_aa_bibliography_title() -> None:
    assert build_latex_report.BIBLIOGRAPHY_TITLES["aa"] == "Referencias"
    assert build_latex_report.BIBLIOGRAPHY_TITLES["aa_report"] == "Referencias"


# ---------------------------------------------------------------------------
# render_tex output
# ---------------------------------------------------------------------------


def test_aa_render_leaves_no_placeholder_unfilled(tmp_path: Path) -> None:
    tex = render(tmp_path)
    assert not re.findall(r"\{\{[A-Z_]+\}\}", tex), "every placeholder of the template is filled"


def test_aa_render_prints_the_activity_label(tmp_path: Path) -> None:
    tex = render(tmp_path)
    preamble, document = tex.split(r"\begin{document}")
    assert "AA-2" in preamble, "the running header carries AA-N"
    assert "ACTIVIDAD AA-2" in document, "the kicker carries AA-N"


def test_aa_heading_defaults_to_aprendizaje_autonomo(tmp_path: Path) -> None:
    preamble, document = render(tmp_path).split(r"\begin{document}")
    assert "pdftitle={Aprendizaje autónomo}" in preamble
    assert r"\MakeUppercase{Aprendizaje autónomo}" in preamble, "the running header keeps the default"
    assert "Aprendizaje autónomo\\par" in document, "the large title keeps the default"


def test_aa_heading_follows_the_metadata(tmp_path: Path) -> None:
    tex = render(tmp_path, metadata={**full_aa_metadata(), "heading": "Avance Grupal"})
    preamble, document = tex.split(r"\begin{document}")
    assert "pdftitle={Avance Grupal}" in preamble
    assert r"\MakeUppercase{Avance Grupal}" in preamble, "the running header uses the heading"
    assert "Avance Grupal\\par" in document, "the large title uses the heading"
    assert "Aprendizaje autónomo" not in tex and "APRENDIZAJE AUTÓNOMO" not in tex


def test_aa_label_does_not_double_an_authored_prefix(tmp_path: Path) -> None:
    tex = render(tmp_path, metadata={**full_aa_metadata(), "practice_number": "AA-2"})
    assert "AA-2" in tex and "AA-AA" not in tex


def test_aa_label_without_a_number_is_the_bare_acronym(tmp_path: Path) -> None:
    tex = render(tmp_path, metadata=required_aa_metadata())
    assert "ACTIVIDAD AA\\ " in tex and "AA-None" not in tex and "AA-\\" not in tex


def test_aa_render_prints_the_letterhead_and_title(tmp_path: Path) -> None:
    document = render(tmp_path).split(r"\begin{document}")[1]
    assert "Universidad Nacional de Loja" in document, "the letterhead names the university"
    assert "Carrera de Computación" in document, "the career default"
    assert "Comparación de algoritmos de planificación" in document, "the report title is the subtitle"
    assert "Sistemas Operativos" in document, "the kicker names the subject"


def test_aa_letterhead_follows_the_metadata_and_is_escaped(tmp_path: Path) -> None:
    metadata = {
        **full_aa_metadata(),
        "university": "Universidad A & B",
        "faculty": "Facultad 100%",
        "career": "Carrera de Computación_2",
    }
    tex = render(tmp_path, metadata=metadata)
    assert r"Universidad A \& B" in tex
    assert r"Facultad 100\%" in tex
    assert r"Carrera de Computación\_2" in tex


def test_aa_render_ficha_rows_in_order(tmp_path: Path) -> None:
    tex = render(tmp_path)
    positions = [tex.index(rf"\ficha{{{label}}}") for label, _key in FICHA_ROWS]
    assert positions == sorted(positions), "the mockup's reading order is fixed"
    assert positions[-1] < tex.index(r"\section{Objetivo(s)}"), "the ficha precedes the body"
    meta = full_aa_metadata()
    for label, key in FICHA_ROWS:
        value = {"practice_number": "AA-2", "cycle": "Cuarto, paralelo A"}.get(key, meta[key])
        assert value in ficha_of(tex, label), f"{key} must fill the '{label}' entry"


def test_aa_ficha_joins_cycle_and_parallel(tmp_path: Path) -> None:
    tex = render(tmp_path)
    assert "Cuarto, paralelo A" in ficha_of(tex, "Ciclo")
    tex = render(tmp_path, metadata={**full_aa_metadata(), "parallel": None})
    assert ficha_of(tex, "Ciclo").endswith("{Cuarto}")


def test_aa_ficha_omits_rows_whose_metadata_is_absent(tmp_path: Path) -> None:
    """Existing AA reports carry only the five required keys: no empty entries."""
    tex = render(tmp_path, metadata=required_aa_metadata())
    for label in ("Estudiante", "Asignatura", "Docente", "Fecha de entrega"):
        assert rf"\ficha{{{label}}}" in tex
    for label in ("Ciclo", "Unidad", "Resultado de aprendizaje", "Actividad", "Tiempo en el sílabo"):
        assert rf"\ficha{{{label}}}" not in tex, f"'{label}' has no metadata, so no entry"
    assert not re.search(r"\\ficha\{[^}]*\}\{\s*\}", tex), "no entry is ever printed empty"


def test_aa_ficha_escapes_latex_specials(tmp_path: Path) -> None:
    metadata = full_aa_metadata()
    metadata["student"] = "Ana & Beto_100%"
    metadata["unit"] = "Unidad #2 (norte)"
    metadata["learning_outcome"] = "Calcula $5 y {llaves}"
    tex = render(tmp_path, metadata=metadata)
    assert r"Ana \& Beto\_100\%" in tex
    assert r"Unidad \#2 (norte)" in tex
    assert r"Calcula \$5 y \{llaves\}" in tex


def test_aa_ficha_flattens_multiline_values(tmp_path: Path) -> None:
    metadata = full_aa_metadata()
    metadata["learning_outcome"] = "Compara algoritmos\nde planificación"
    tex = render(tmp_path, metadata=metadata)
    assert "Compara algoritmos de planificación" in ficha_of(tex, "Resultado de aprendizaje")


def test_aa_group_report_lists_every_member(tmp_path: Path) -> None:
    members = ["Ana Pérez", "Luis Mora", "Camila Jaramillo"]
    tex = render(tmp_path, metadata={**full_aa_metadata(), "members": members})
    entry = ficha_of(tex, "Estudiantes")
    assert all(name in entry for name in members), "a group report names every member"
    assert r"\ficha{Estudiante}" not in tex, "the label is plural for a group"


def test_aa_individual_report_keeps_the_single_student(tmp_path: Path) -> None:
    tex = render(tmp_path)
    assert "Camila Jaramillo" in ficha_of(tex, "Estudiante")
    assert r"\ficha{Estudiantes}" not in tex


def test_aa_render_fills_the_logo_path(tmp_path: Path) -> None:
    assert build_latex_report.APE_LOGO_FILENAME in render(tmp_path)


def test_aa_render_never_asks_the_author_for_zoneclear(tmp_path: Path) -> None:
    """The zone mechanism is the template's job: neither the renderer nor body.md needs it."""
    body = "# Objetivo(s)\n\nTexto.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n$$x^2$$\n"
    assert "zoneclear" not in render(tmp_path, body=body).split(r"\begin{document}")[1]


def test_aa_render_annexes_move_after_the_bibliography(tmp_path: Path) -> None:
    tex = render(tmp_path)
    last_section = tex.index("Contenido de Conclusiones")
    bibliography = tex.index(r"\printbibliography[title={Referencias}]")
    annexes = tex.index("Contenido de anexos")
    assert last_section < bibliography < annexes, "Anexos must render after the bibliography"
    assert tex.index(r"\section{Anexos}") > bibliography


def test_aa_render_without_annexes_keeps_the_body_whole(tmp_path: Path) -> None:
    body = default_aa_body().split("# Anexos")[0]
    tex = render(tmp_path, body=body)
    assert "Contenido de Conclusiones" in tex
    assert r"\section{Anexos}" not in tex


def test_aa_annex_split_is_a_template_capability_not_a_format_check() -> None:
    keys = build_latex_report.ANNEXES_AFTER_BIBLIOGRAPHY_TEMPLATE_KEYS
    assert {"aa", "aa_report"} <= keys
    assert {"ape", "ape_report", "acd", "acd_report"} <= keys, "APE and ACD keep the capability"


def test_aa_does_not_enable_definition_lists(tmp_path: Path) -> None:
    """The AA-B mockup has no label column, so Pandoc definition lists stay plain text."""
    assert not ({"aa", "aa_report"} & build_latex_report.DEFINITION_LIST_TEMPLATE_KEYS)
    body = "# Objetivo(s)\n\nTérmino\n: Definición\n"
    assert r"\begin{description}" not in render(tmp_path, body=body)


def test_aa_with_figures_has_no_list_of_figures(tmp_path: Path) -> None:
    body = default_aa_body().replace(
        "Contenido de Desarrollo.", "![Diagrama. Fuente: propia.](fig.png)"
    )
    tex = render(tmp_path, body=body)
    assert r"\includegraphics" in tex
    assert r"\listoffigures" not in tex


# ---------------------------------------------------------------------------
# Selection and validation
# ---------------------------------------------------------------------------


def rendered_template_name(config: ReportConfig) -> str:
    key = build_latex_report.normalize_template_key(build_latex_report.template_key_for(config))
    return build_latex_report.resolve_template(key).name


def test_aa_format_defaults_to_the_aa_template(tmp_path: Path) -> None:
    assert rendered_template_name(make_render_config(tmp_path)) == "aa-report.tex"


def test_aa_format_beats_the_route_template_default(tmp_path: Path) -> None:
    config = make_render_config(tmp_path, raw={"route": "technical"})
    assert rendered_template_name(config) == "aa-report.tex"


@pytest.mark.parametrize("key", ["unl", "unl_report", "default"])
def test_explicit_template_still_beats_the_aa_default(tmp_path: Path, key: str) -> None:
    config = make_render_config(tmp_path, raw={"template": key})
    assert rendered_template_name(config) == UNL_TEMPLATE.name
    tex = build_latex_report.render_tex(config)
    assert "titlepage" in tex, "the explicit UNL cover template keeps working for AA"
    assert r"\listoffigures" not in tex


def test_aa_requires_no_new_metadata() -> None:
    assert FORMAT_REQUIRED_METADATA["aa"] == ("title", "subject", "teacher", "student", "date")


def test_existing_aa_report_with_only_required_metadata_still_validates(tmp_path: Path) -> None:
    config = make_render_config(tmp_path, metadata=required_aa_metadata())
    result = metadata_validation(config)
    assert not result.errors, result.errors


def test_aa_group_report_renders_with_only_required_metadata(tmp_path: Path) -> None:
    tex = render(tmp_path, metadata={**required_aa_metadata(), "members": ["Ana Pérez", "Luis Mora"]})
    assert "Ana Pérez" in ficha_of(tex, "Estudiantes")


# ---------------------------------------------------------------------------
# The ficha zone, on real PDFs
# ---------------------------------------------------------------------------
#
# The ficha hangs in the left margin of page 1. Prose that starts beside it is
# narrowed by the template; floats, display math, code and tables that would
# start beside it must be pushed below it, and the author never writes a
# manual clear. A reference build with a trivial body shows what the ficha
# region looks like alone; every variant's ficha region must be pixel-identical.

needs_latex = pytest.mark.skipif(
    (_LATEX_ENGINE is None and not _DOCKER_FALLBACK) or shutil.which("pdftoppm") is None,
    reason="needs a local LaTeX engine or the local texlive/texlive:latest image, and pdftoppm",
)

SENTENCE = "Se calcula el tiempo de espera de cada proceso y se compara con el resultado esperado."
PARAGRAPH = " ".join([SENTENCE] * 4)
TABLE = "| Proceso | Llegada | Ráfaga |\n|---|---|---|\n| P1 | 0 | 8 |\n| P2 | 1 | 4 |\n| P3 | 2 | 9 |\n"
CODE = "```python\ndef fcfs(procs):\n    t = 0\n    for n, a, b in procs:\n        t += b\n    return t\n```\n"
MATH = "$$W_i = T_i - B_i$$\n"
WIDE_MATH = (
    "$$\\bar{T} = \\frac{1}{n}\\sum_{i=1}^{n}(C_i - A_i) = \\frac{(8-0)+(12-1)+(21-2)+(26-3)}{4}"
    " = 15{,}25 \\quad \\text{unidades de tiempo de retorno por proceso en promedio}$$\n"
)
FIGURE = "![Diagrama de Gantt. Fuente: elaboración propia.](figura.png)\n"
REST = "# Introducción\n\n" + PARAGRAPH + "\n\n# Desarrollo\n\n" + PARAGRAPH + "\n\n# Conclusiones\n\n" + PARAGRAPH + "\n"

# name -> body.md. The first heading is always followed by the stress material
# within the first centimetres of page 1.
ZONE_VARIANTS = {
    "short-first-section": "# Objetivo(s)\n\nComparar los algoritmos.\n\n" + REST,
    "long-first-section": "# Objetivo(s)\n\n" + "\n\n".join([PARAGRAPH] * 6) + "\n\n" + REST,
    "table-after-heading": "# Objetivo(s)\n\n" + TABLE + "\n" + PARAGRAPH + "\n\n" + REST,
    "figure-after-heading": "# Objetivo(s)\n\n" + FIGURE + "\n" + PARAGRAPH + "\n\n" + REST,
    "code-after-heading": "# Objetivo(s)\n\n" + CODE + "\n" + PARAGRAPH + "\n\n" + REST,
    "math-after-heading": "# Objetivo(s)\n\n" + MATH + "\n" + PARAGRAPH + "\n\n" + REST,
    "wide-math-after-heading": "# Objetivo(s)\n\n" + WIDE_MATH + "\n" + PARAGRAPH + "\n\n" + REST,
    "math-after-short-line": "# Objetivo(s)\n\nSe define:\n\n" + MATH + "\n" + PARAGRAPH + "\n\n" + REST,
    "figure-then-table-then-code": (
        "# Objetivo(s)\n\n" + FIGURE + "\n" + TABLE + "\n" + CODE + "\n" + MATH + "\n" + REST
    ),
    "list-and-subsection": (
        "# Objetivo(s)\n\n- Primero.\n- Segundo.\n\n## Detalle\n\n" + TABLE + "\n" + REST
    ),
}

# The ficha rectangle on page 1 (A4 pt at 40 dpi), from the mockup geometry:
# x from 1.3 cm to 5.2 cm, from 4.45 cm down to where the metadata ends. The
# crop below is generous on the right and bottom of the real ficha so that any
# intruder inside the margin column shows up.
DPI = 40
CM = DPI / 2.54


def _write_visible_figure(path: Path) -> None:
    """A dark block: the 1-pixel PNG of the other compile tests would be invisible."""
    from PIL import Image

    Image.new("RGB", (600, 240), (31, 78, 61)).save(path)


def _build_pdf(folder: Path, monkeypatch: pytest.MonkeyPatch, body: str, metadata: dict) -> Path:
    if _LATEX_ENGINE is None:
        real_docker_compile_command = build_latex_report.docker_compile_command

        def offline_docker_compile_command(config):
            argv = real_docker_compile_command(config)
            return [*argv[:2], "--pull=never", "--network=none", *argv[2:]]

        monkeypatch.setattr(build_latex_report, "docker_compile_command", offline_docker_compile_command)
    folder.mkdir(parents=True)
    _write_visible_figure(folder / "figura.png")
    (folder / "body.md").write_text(body, encoding="utf-8")
    (folder / "report.yml").write_text(
        # publish_global: false -- the sample subject would otherwise copy the
        # PDF into the real outputs/<materia>/ tree.
        yaml.safe_dump({**BASE_RAW, "pdf": "build/main.pdf", "publish_global": False, "metadata": metadata}),
        encoding="utf-8",
    )
    config = build_latex_report.build(folder, compile_pdf=True)
    return config.pdf_path


def _page_one_png(pdf: Path, stem: str) -> Path:
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(DPI), "-f", "1", "-l", "1", "-singlefile", str(pdf), str(pdf.parent / stem)],
        check=True, capture_output=True,
    )
    return pdf.parent / f"{stem}.png"


def _ficha_crop(png: Path, rows: tuple[int, int] | None = None):
    """The margin column of page 1, optionally limited to the ficha's own rows."""
    from PIL import Image

    image = Image.open(png).convert("L")
    top, bottom = rows if rows else (int(4.0 * CM), int(16.0 * CM))
    return image.crop((int(1.0 * CM), top, int(5.6 * CM), bottom))


@pytest.fixture(scope="module")
def reference_ficha(tmp_path_factory: pytest.TempPathFactory):
    """The ficha of a report whose body is a single short line: (pixels, rows it spans)."""
    from PIL import ImageChops

    mp = pytest.MonkeyPatch()
    try:
        folder = tmp_path_factory.mktemp("aa-reference") / "r"
        pdf = _build_pdf(folder, mp, "# Objetivo(s)\n\nComparar.\n", full_aa_metadata())
        png = _page_one_png(pdf, "reference")
        box = ImageChops.invert(_ficha_crop(png)).getbbox()
        top = int(4.0 * CM) + box[1]
        bottom = int(4.0 * CM) + box[3]
        return _ficha_crop(png, (top, bottom)), (top, bottom)
    finally:
        mp.undo()


@needs_latex
def test_reference_ficha_region_is_not_blank(reference_ficha) -> None:
    pixels, (top, bottom) = reference_ficha
    assert pixels.getextrema()[0] < 128, "the ficha text must be inside the compared region"
    assert bottom - top > 5 * CM, "the ficha spans several centimetres"


@needs_latex
@pytest.mark.parametrize("variant", sorted(ZONE_VARIANTS))
def test_ficha_stays_clear_for_every_body_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reference_ficha, variant: str
) -> None:
    from PIL import ImageChops

    pdf = _build_pdf(tmp_path / "r", monkeypatch, ZONE_VARIANTS[variant], full_aa_metadata())
    assert "zoneclear" not in (tmp_path / "r" / "body.md").read_text(encoding="utf-8")
    pixels, rows = reference_ficha
    crop = _ficha_crop(_page_one_png(pdf, f"variant-{variant}"), rows)
    difference = ImageChops.difference(pixels, crop).getbbox()
    assert difference is None, f"{variant}: something is drawn over the ficha at {difference}"
