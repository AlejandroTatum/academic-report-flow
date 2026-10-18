#!/usr/bin/env python3
"""Build a UNL academic report through a Markdown/YAML/BibTeX -> LaTeX -> PDF pipeline."""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

from output_router import publish_global_output
from report_config import (
    CONTENT_ROOT,
    DEFAULT_ROUTE,
    GLOBAL_OUTPUTS,
    ROUTE_ALIASES,
    ROUTE_KEY,
    ROOT,
    ReportConfig,
    latex_escape,
    load_report_config,
    relative_subpath,
)
from table_directives import DIRECTIVE_RE as TABLE_STYLE_DIRECTIVE_RE
from table_directives import context_for_table
from table_latex_tokens import render_styled_table_latex
from table_model import TableStylesContext, resolve_table_style

DEFAULT_TEMPLATE = ROOT / "templates" / "unl-report.tex"
PLAIN_TEMPLATE = ROOT / "templates" / "plain-report.tex"
APE_TEMPLATE = ROOT / "templates" / "ape-report.tex"
ACD_TEMPLATE = ROOT / "templates" / "acd-report.tex"
AA_TEMPLATE = ROOT / "templates" / "aa-report.tex"
TEMPLATE_ALIASES = {
    "default": DEFAULT_TEMPLATE,
    "unl": DEFAULT_TEMPLATE,
    "unl_report": DEFAULT_TEMPLATE,
    "chamba_overleaf": ROOT / "templates" / "chamba-overleaf.tex",
    "overleaf_chamba": ROOT / "templates" / "chamba-overleaf.tex",
    "plain": PLAIN_TEMPLATE,
    "plain_report": PLAIN_TEMPLATE,
    "ape": APE_TEMPLATE,
    "ape_report": APE_TEMPLATE,
    "acd": ACD_TEMPLATE,
    "acd_report": ACD_TEMPLATE,
    "aa": AA_TEMPLATE,
    "aa_report": AA_TEMPLATE,
}


def normalize_template_key(key: str | None) -> str:
    """Normalize a report.yml template key (case-insensitive, trimmed)."""
    normalized = str(key or "").strip().lower()
    return normalized or "default"


def resolve_template(key: str | None) -> Path:
    """Resolve a template key to its .tex path.

    An empty/absent key keeps the historical academic default. An unknown key
    fails loudly instead of silently rendering the institutional template.
    """
    normalized = normalize_template_key(key)
    template_path = TEMPLATE_ALIASES.get(normalized)
    if template_path is None:
        valid = ", ".join(sorted(TEMPLATE_ALIASES))
        raise SystemExit(
            f"Template LaTeX desconocido: {normalized!r}. Valores válidos: {valid}"
        )
    return template_path


# Default template per confirmed route (routing.md): only Route A may
# activate the UNL institutional shell; Routes B–E derive the plain template.
# This is a DEFAULT for an absent `template:` key — an explicit key always
# wins, in either direction, and report.yml is never rewritten.
ROUTE_TEMPLATE_DEFAULTS = {
    "academic": "unl",
    "project": "plain",
    "business": "plain",
    "technical": "plain",
    "other": "plain",
}

# Default template per chosen FORMAT (new-report-flow): `ape` renders the
# teacher's Word replica, `acd` the session record sheet, `aa` the editorial
# autonomous-learning report and `libre` the plain template. The format is the
# user's post-approval presentation choice, so it outranks the route default —
# but never an explicit `template:` key, which still wins in either direction
# (a libre report may ask for any shell, an AA report may keep `unl`).
FORMAT_TEMPLATE_DEFAULTS = {
    "ape": "ape",
    "acd": "acd",
    "aa": "aa",
    "libre": "plain",
}


def template_key_for(config: ReportConfig) -> str | None:
    """The template key a report resolves to, honouring explicit choice first.

    Precedence: an explicit report.yml `template:` key, then the chosen
    format's default, then the confirmed route's default.
    """
    explicit = config.raw.get("template") or config.raw.get("latex_template")
    if str(explicit or "").strip():
        return explicit
    chosen = config.format
    if chosen in FORMAT_TEMPLATE_DEFAULTS:
        return FORMAT_TEMPLATE_DEFAULTS[chosen]
    return ROUTE_TEMPLATE_DEFAULTS.get(config.route, "default")


# report.yml key that turns academic section numbering on or off for one
# report. `routing.md` forbids auto-included academic section
# numbering on Routes B, C and D, but the templates numbered unconditionally.
#
# The DEFAULT is derived from the confirmed route (#23): academic reports
# number as always; Routes B–D, which the contract forbids from auto-including
# academic numbering, default to unnumbered. An explicit key still overrides
# the route default in either direction, and nothing rewrites report.yml.
SECTION_NUMBERING_KEY = "section_numbering"

# Absence of the key means numbered. Every report that exists today declares
# nothing about numbering and must keep rendering exactly as it does now.
SECTION_NUMBERING_DEFAULT = True

_SECTION_NUMBERING_TRUE = {"true", "yes", "on", "si", "sí", "1"}
_SECTION_NUMBERING_FALSE = {"false", "no", "off", "0"}


def section_numbering_enabled(raw: dict) -> bool:
    """Read `section_numbering:` from a report.yml mapping.

    Returns the route-derived default when the key is absent: numbered for the
    academic route, unnumbered for the non-academic routes the contract
    forbids from auto-including academic numbering. An unrecognised value
    fails loudly rather than picking a side: guessing would silently
    renumber — or unnumber — a whole document over a typo.
    """
    if SECTION_NUMBERING_KEY not in raw:
        written = str(raw.get(ROUTE_KEY) or "").strip().lower()
        route = (ROUTE_ALIASES.get(written, written) if written else DEFAULT_ROUTE)
        return route == DEFAULT_ROUTE or route not in ROUTE_TEMPLATE_DEFAULTS
    value = raw.get(SECTION_NUMBERING_KEY)
    if isinstance(value, bool):
        return value
    written = str(value if value is not None else "").strip().lower()
    if written in _SECTION_NUMBERING_TRUE:
        return True
    if written in _SECTION_NUMBERING_FALSE:
        return False
    raise SystemExit(
        f"Valor no válido para '{SECTION_NUMBERING_KEY}' en report.yml: "
        f"{value!r}. Valores aceptados: true, false (también sí/no, on/off). "
        "Sin la clave, la ruta decide: numeradas en la académica, sin números en las demás."
    )


# Asset constants — single source of truth for expected filenames.
ASSETS_DIR = ROOT / "assets"
# Markdown image syntax. Only ever matched against Markdown source, never
# against a body that markdown_to_latex() has already converted.
MARKDOWN_IMAGE_RE = re.compile(r"!\[.*\]\(.*\)")


def cover_field(value: str | None) -> str:
    r"""Escape an optional cover field, never returning an empty string.

    Cover templates render these on their own line as ``{\large {{FIELD}}}\\``.
    An empty substitution leaves ``{\large }\\``, which LaTeX rejects outright
    with ``There's no line here to end.`` — a fatal error whose message points
    at the title page rather than at the metadata field nobody set.

    ``\strut`` is an invisible box with the height and depth of a normal line,
    so the line exists for LaTeX to end while the reader sees nothing, and the
    cover's vertical rhythm stays exactly as designed.
    """
    text = (value or "").strip()
    return latex_escape(text) if text else r"\strut"
def report_authors(meta: dict) -> str:
    """The author line: every member of a group report, else the student."""
    members = meta.get("members")
    if isinstance(members, list) and members:
        return ", ".join(str(name) for name in members)
    return str(meta.get("student") or "")


LOGO_FILENAME = "unl-logo-aa1-transparent.png"
BACKGROUND_FILENAME = "fondo-overleaf-investigacion.png"
# Faculty logo extracted from the teacher's APE Word template (the header
# carries it on every page); referenced by ape-report.tex via {{APE_LOGO_PATH}}.
APE_LOGO_FILENAME = "ape-faculty-logo.png"
# Known extra PNGs in assets/ that are NOT referenced by the LaTeX pipeline.
# These are standalone files (e.g. prompt engineering flow diagrams) used
# directly from report body.md via Markdown image syntax.
KNOWN_EXTRA_ASSETS: set[str] = {"prompting-os-flow.png"}
# Plain logo variant — not used by the LaTeX pipeline directly but referenced
# in unl-shell.md as the original AA1 source asset.
PLAIN_LOGO_FILENAME = "unl-logo-aa1.png"

EXPECTED_ASSETS: list[tuple[str, str]] = [
    (LOGO_FILENAME, "Logo UNL (transparente, usado por {{LOGO_PATH}})"),
    (BACKGROUND_FILENAME, "Fondo portada (usado por {{BACKGROUND_PATH}})"),
    (PLAIN_LOGO_FILENAME, "Logo UNL original (referencia AA1, no usado por pipeline)"),
    (APE_LOGO_FILENAME, "Logo facultad FEIRNNR (usado por {{APE_LOGO_PATH}} en ape-report.tex)"),
]


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=check)


# Characters after which an inline-code run may break across lines. Monospace
# fonts carry no hyphenation patterns, so without these explicit penalties a
# path like ``tools/test_content_root.py`` is one unbreakable box: it overflows
# a table column into its neighbour, and in justified prose it forces TeX to
# shrink the surrounding interword glue until the code looks glued to the words
# next to it.
INLINE_CODE_BREAK_AFTER = "/_-.:,=()"


def inline_code(value: str) -> str:
    r"""Render inline code as ``\texttt`` with explicit break opportunities.

    ``\allowbreak{}`` is a zero-width penalty: it never adds a hyphen and never
    changes the glyphs, it only tells TeX that a line may end there. The
    trailing separator gets none, since a break at the very end of the run
    would leave the box empty.
    """
    if re.match(r"^(?:https?://|git@|ssh://)", value):
        return r"\nolinkurl{" + value + "}"
    characters = list(value)
    last = len(characters) - 1
    pieces: list[str] = []
    for index, character in enumerate(characters):
        pieces.append(latex_escape(character))
        if character in INLINE_CODE_BREAK_AFTER and index < last:
            pieces.append(r"\allowbreak{}")
    return r"\texttt{" + "".join(pieces) + "}"


# biblatex package options and trailing setup per `citation_style`. IEEE is
# the default and must render exactly as before; APA needs the Spanish mapping
# (csquotes, which biblatex-apa requires, is already loaded by every template).
BIBLATEX_OPTIONS = {
    "ieee": "backend=biber,style=ieee,sorting=none,hyperref=true",
    # biblatex-apa's own sorting=apa lists no-date works first (APA 7, 9.47).
    "apa": "backend=biber,style=apa,hyperref=true",
}
BIBLATEX_SETUP = {
    "ieee": "",
    "apa": (
        r"\DeclareLanguageMapping{spanish}{spanish-apa}"
        r"\ExecuteBibliographyOptions{language=spanish}"
        # APA 7 in Spanish: "Recuperado el <fecha>, de <URL>".
        r"\DefineBibliographyStrings{spanish}{retrieved={Recuperado},from={de}}"
        # Spanish joins the last two authors with "y", not "&".
        r"\DeclareDelimFormat[bib,biblist]{finalnamedelim}{\addspace y\space}"
        r"\DeclareDelimFormat[parencite]{finalnamedelim}{\addspace y\space}"
        # Air between reference entries; the hanging indent stays biblatex-apa's.
        r"\setlength{\bibitemsep}{0.5\baselineskip}"
        # APA lists are left-aligned; justified lines open wide word gaps.
        r"\AtBeginBibliography{\raggedright}"
        # URLs/DOIs may break after / . - only; never after "https:" or
        # mid-word. xurl (loaded after biblatex) resets the counters and
        # \biburlsetup resets the break sets, so apply both at end of preamble.
        r"\urlstyle{same}"
        r"\AtEndPreamble{"
        r"\setcounter{biburlbreakpenalty}{50}"
        r"\setcounter{biburlbigbreakpenalty}{10000}"
        r"\setcounter{biburlnumpenalty}{0}"
        r"\setcounter{biburlucpenalty}{0}"
        r"\setcounter{biburllcpenalty}{0}"
        r"\appto\biburlsetup{\Urlmuskip=0mu\relax\def\UrlBreaks{\do\/\do\.\do\-}\def\UrlBigBreaks{\do\:}}"
        # Body \url/\href: ":" is a big break by default, which splits "https: //".
        r"\def\UrlBigBreaks{}}"
    ),
}


def convert_inline(text: str) -> str:
    placeholders: list[tuple[str, str]] = []

    def keep(pattern: str, repl):
        nonlocal text
        def wrapper(match: re.Match[str]) -> str:
            token = f"@@LATEX_KEEP_{len(placeholders)}@@"
            placeholders.append((token, repl(match)))
            return token
        text = re.sub(pattern, wrapper, text)

    keep(r"\[@([A-Za-z0-9_:\-.,;@ ]+)\]",
         lambda m: r"\cite{" + ",".join(k for k in re.split(r"[;,\s]+", m.group(1).replace("@", "")) if k) + "}")
    keep(r"\$([^$]+)\$", lambda m: "$" + m.group(1) + "$")
    keep(r"`([^`]+)`", lambda m: inline_code(m.group(1)))
    keep(r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
         lambda m: r"\href{" + m.group(2) + "}{" + latex_escape(m.group(1)) + "}")
    keep(r"<(https?://[^\s>]+)>", lambda m: r"\url{" + m.group(1) + "}")
    # Paired straight quotes become “…”; code, math, URLs and cites are already
    # placeholders, and an unpaired quote has nothing to pair with.
    text = re.sub(r'"([^"\s](?:[^"]*[^"\s])?)"', "“\\1”", text)
    escaped = latex_escape(text)
    escaped = re.sub(r"\*\*([^*]+)\*\*", lambda m: r"\textbf{" + m.group(1) + "}", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", lambda m: r"\emph{" + m.group(1) + "}", escaped)
    for token, value in placeholders:
        escaped = escaped.replace(latex_escape(token), value)
        escaped = escaped.replace(token, value)
    return escaped


# Fenced code blocks: ``` or ~~~ (three or more), with an optional language
# word. Anything between an opening fence and its closing fence is literal.
# Fence language word -> listings language. Anything absent renders plain
# (still styled): a wrong guess would colour code as the wrong language.
LISTING_LANGUAGES = {
    "octave": "Octave",
    "matlab": "Matlab",
    "python": "Python",
    "py": "Python",
    "bash": "bash",
    "sh": "bash",
    "shell": "bash",
    "zsh": "bash",
    "c": "C",
    "c++": "C++",
    "cpp": "C++",
    "java": "Java",
    "sql": "SQL",
    "html": "HTML",
    "xml": "XML",
    "javascript": "Java",
    "js": "Java",
    "r": "R",
    "tex": "TeX",
    "latex": "[LaTeX]TeX",
}

# The one definition of the code look, injected through {{LISTING_PREAMBLE}}
# after xcolor in every template. UTF-8 comes from XeLaTeX itself;
# extendedchars keeps listings from splitting multibyte accents.
LISTING_PREAMBLE = r"""\usepackage{listings}
\definecolor{codebg}{gray}{0.955}
\definecolor{coderule}{RGB}{90,110,140}
\definecolor{codenum}{gray}{0.5}
\definecolor{codekw}{RGB}{30,50,110}
\definecolor{codecomment}{gray}{0.45}
\definecolor{codestring}{RGB}{135,40,40}
\lstdefinestyle{reportcode}{
  basicstyle=\linespread{1}\small\ttfamily,
  backgroundcolor=\color{codebg},
  frame=leftline,
  rulecolor=\color{coderule},
  framerule=1.4pt,
  xleftmargin=3.0em,
  framexleftmargin=2.4em,
  xrightmargin=0pt,
  framexrightmargin=0pt,
  framesep=0.6em,
  numbers=left,
  numbersep=0.7em,
  numberstyle=\tiny\ttfamily\color{codenum},
  breaklines=true,
  breakatwhitespace=false,
  postbreak=\mbox{\textcolor{codenum}{\tiny$\hookrightarrow$}\space},
  columns=fullflexible,
  keepspaces=true,
  showstringspaces=false,
  tabsize=2,
  extendedchars=true,
  aboveskip=1.1em,
  belowskip=0.9em,
  keywordstyle=\color{codekw}\bfseries,
  commentstyle=\color{codecomment}\itshape,
  stringstyle=\color{codestring},
}"""


CODE_FENCE_RE = re.compile(r"^(?P<marker>`{3,}|~{3,})\s*(?P<language>[^`]*)$")

# Pandoc definition-list marker: a ": " line that defines the term above it.
DEFINITION_LINE_RE = re.compile(r"^:\s+(\S.*)$")


def is_closing_fence(line: str, marker: str) -> bool:
    """Whether ``line`` closes a block opened with the fence character ``marker``.

    Any run of three or more of the same character closes it, whatever the
    opening fence's length.
    """
    candidate = line.strip()
    return len(candidate) >= 3 and set(candidate) == {marker}


# Headings the templates already print by themselves through \printbibliography.
BIBLIOGRAPHY_HEADINGS = {"bibliografia", "referencias", "references", "bibliography"}

# Title each template's \printbibliography prints, keyed by normalized template
# key. The renderer owns the emission decision (#26); the template owns the
# heading wording.
# APA 7 (Spanish) names the list "Referencias" regardless of the template.
APA_BIBLIOGRAPHY_TITLE = "Referencias"


def bibliography_title(config: ReportConfig, template_key: str) -> str:
    if config.citation_style == "apa":
        return APA_BIBLIOGRAPHY_TITLE
    return BIBLIOGRAPHY_TITLES[template_key]


BIBLIOGRAPHY_TITLES = {
    "default": "Bibliografía",
    "unl": "Bibliografía",
    "unl_report": "Bibliografía",
    "plain": "Referencias",
    "plain_report": "Referencias",
    "chamba_overleaf": "Referencias bibliográficas",
    "overleaf_chamba": "Referencias bibliográficas",
    "ape": "Bibliografía / Referencias",
    "ape_report": "Bibliografía / Referencias",
    "acd": "Referencias",
    "acd_report": "Referencias",
    "aa": "Referencias",
    "aa_report": "Referencias",
}


def fold_heading(title: str) -> str:
    """Normalize a heading for case- and accent-insensitive comparison."""
    decomposed = unicodedata.normalize("NFKD", title)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return stripped.casefold().strip()


def is_bibliography_heading(title: str) -> bool:
    """True for the heading titles ``\\printbibliography`` already prints."""
    return fold_heading(title) in BIBLIOGRAPHY_HEADINGS


# The APE identification table (section 1 of the teacher's document):
# label|value rows generated from metadata, in the teacher's fixed order.
# The heading itself is rendered by the template; body.md never authors it.
APE_IDENTIFICATION_ROWS: tuple[tuple[str, str], ...] = (
    ("Nombre del estudiante(s)", "student"),
    ("Asignatura", "subject"),
    ("Ciclo", "cycle"),
    ("Unidad", "unit"),
    ("Resultado de aprendizaje de la unidad", "learning_outcome"),
    ("Práctica Nro.", "practice_number"),
    ("Tipo", "practice_type"),
    ("Título de la Práctica", "title"),
    ("Nombre del Docente", "teacher"),
    ("Fecha", "date"),
    ("Horario", "schedule"),
    ("Lugar", "place"),
    ("Tiempo planificado en el Sílabo", "planned_time"),
)


def ape_identification_table(meta: dict, omitted: tuple[str, ...] = ()) -> str:
    """Render the teacher's 2-column identification table from metadata.

    Every value is LaTeX-escaped, and internal line breaks are flattened: a
    multi-line YAML value would otherwise break the `tabular` rows. Rows whose
    key is in ``omitted`` (``ape_omit_fields:``) are left out. A group report
    (``metadata.members``) names every member in the student row.
    """
    members = meta.get("members")
    values = dict(meta)
    if isinstance(members, list) and members:
        values["student"] = ", ".join(str(name) for name in members)
    rows = "\n\\hline\n".join(
        rf"{label} & {latex_escape(' '.join(str(values.get(key) or '').split()))} \\"
        for label, key in APE_IDENTIFICATION_ROWS
        if key not in omitted
    )
    return "\n".join([
        "\\begin{center}",
        r"\renewcommand{\arraystretch}{1.35}",
        r"\begin{tabular}{|>{\raggedright\arraybackslash}p{0.42\textwidth}"
        r"|>{\raggedright\arraybackslash}p{0.50\textwidth}|}",
        r"\hline",
        rows,
        r"\hline",
        r"\end{tabular}",
        r"\end{center}",
    ])


def ape_report_title(meta: dict) -> str:
    """The APE document title: the teacher's fixed wording plus the practice
    number, unless ``metadata.ape_title`` sets the heading for an activity that
    is not a practical-experimental report. Escaped by the caller through the
    normal replacement table."""
    override = " ".join(str(meta.get("ape_title") or "").split())
    if override:
        return override
    practice_number = str(meta.get("practice_number") or "").strip()
    title = "Reporte Técnico de Actividades Práctico-Experimentales"
    return f"{title} Nro. {practice_number}" if practice_number else title


def numbered_label(meta: dict, prefix: str) -> str:
    """The activity number as the report prints it: ``ACD-4`` for ``practice_number: 4``.

    An authored ``ACD-4`` / ``ACD 4`` is taken as the number, never doubled.
    Without a number the label is the bare acronym.
    """
    number = re.sub(
        rf"^{re.escape(prefix)}[\s_-]*", "", str(meta.get("practice_number") or "").strip(), flags=re.IGNORECASE
    )
    number = " ".join(number.split())
    return f"{prefix}-{number}" if number else prefix


def acd_label(meta: dict) -> str:
    return numbered_label(meta, "ACD")


def aa_label(meta: dict) -> str:
    return numbered_label(meta, "AA")


AA_DEFAULT_HEADING = "Aprendizaje autónomo"


def aa_heading(meta: dict) -> str:
    """Large page-1 title of the AA design; ``metadata.heading`` overrides the default."""
    return " ".join(str(meta.get("heading") or "").split()) or AA_DEFAULT_HEADING


def _flat(value: object) -> str:
    """One line of LaTeX-escaped text: multi-line YAML values would break a table cell."""
    return latex_escape(" ".join(str(value or "").split()))


def acd_session_block(meta: dict) -> str:
    """Render the ACD session grid (section 1 of the record) from metadata.

    The cells follow the approved mockup: the session topic across the top,
    then three-column rows. Every value is LaTeX-escaped and flattened, and a
    group report (``metadata.members``) names every member in the student cell.
    Cycle and parallel share one cell (the parallel defaults to A), and the ACD
    number shares one with the syllabus time. ``\acdcell`` is defined by the
    template.
    """
    def cell(label: str, value: str, size: str = "") -> str:
        return rf"\acdcell{{{label}}}{{{size}{value}}}"

    cycle_parallel = " · ".join(
        _flat(meta.get(key)) for key in ("cycle", "parallel") if str(meta.get(key) or "").strip()
    )
    number_time = " · ".join(
        part for part in (latex_escape(acd_label(meta)), _flat(meta.get("planned_time"))) if part
    )
    rows = [
        [cell("Fecha de la sesión", _flat(meta.get("date"))),
         cell("Horario", _flat(meta.get("schedule"))),
         cell("Lugar", _flat(meta.get("place")))],
        [cell("Asignatura", _flat(meta.get("subject"))),
         cell("Ciclo / paralelo", cycle_parallel),
         cell("Unidad", _flat(meta.get("unit")))],
        [cell("Docente", _flat(meta.get("teacher"))),
         cell("Estudiante(s)", _flat(report_authors(meta))),
         cell("ACD Nro. · tiempo en sílabo", number_time)],
    ]
    lines = [
        r"\begingroup",
        r"\renewcommand{\arraystretch}{1.12}",
        r"\setlength{\tabcolsep}{8pt}",
        r"\begin{tabularx}{\textwidth}{@{}XVXVX@{}}",
        r"\arrayrulecolor{brick}\specialrule{1.4pt}{0pt}{0pt}",
        r"\multicolumn{3}{@{}p{\textwidth}@{}}{"
        + cell("Tema de la sesión", _flat(meta.get("title")), r"\fontsize{11.5}{14}\selectfont ")
        + r"}\\",
        r"\arrayrulecolor{rule}\hline",
    ]
    for row in rows:
        lines.append(" & ".join(row) + r"\\")
        lines.append(r"\hline")
    lines.extend([
        r"\multicolumn{3}{@{}p{\textwidth}@{}}{"
        + cell("Resultado de aprendizaje de la unidad", _flat(meta.get("learning_outcome")))
        + r"}\\",
        r"\arrayrulecolor{ink}\hline",
        r"\end{tabularx}",
        r"\endgroup",
    ])
    return "\n".join(lines)


def acd_footer(meta: dict) -> str:
    """The running footer text: the student(s) and the subject, escaped."""
    return " · ".join(
        part for part in (_flat(report_authors(meta)), _flat(meta.get("subject"))) if part
    )


def aa_ficha(meta: dict) -> str:
    r"""Render the AA identification ficha (page 1, left margin) from metadata.

    One ``\ficha{label}{value}`` entry per field the report carries, in the
    mockup's reading order; a field that is absent produces no entry, so an
    existing AA report that only has the five required keys still renders.
    Every value is LaTeX-escaped and flattened, and a group report
    (``metadata.members``) lists each member on its own line under the plural
    label. ``\ficha`` is defined by the template.
    """
    members = meta.get("members")
    names = [_flat(name) for name in members if str(name).strip()] if isinstance(members, list) else []
    if names:
        student_label = "Estudiantes" if len(names) > 1 else "Estudiante"
        student = r"\\ ".join(names)
    else:
        student_label, student = "Estudiante", _flat(meta.get("student"))

    # The parallel defaults to "A" for every report, so on its own it is not
    # data the author gave: it only qualifies a cycle that is present.
    cycle = _flat(meta.get("cycle"))
    parallel = _flat(meta.get("parallel"))
    if cycle and parallel:
        cycle = f"{cycle}, paralelo {parallel}"

    activity = latex_escape(aa_label(meta)) if str(meta.get("practice_number") or "").strip() else ""
    entries = (
        (student_label, student),
        ("Asignatura", _flat(meta.get("subject"))),
        ("Ciclo", cycle),
        ("Unidad", _flat(meta.get("unit"))),
        ("Resultado de aprendizaje", _flat(meta.get("learning_outcome"))),
        ("Actividad", activity),
        ("Docente", _flat(meta.get("teacher"))),
        ("Fecha de entrega", _flat(meta.get("date"))),
        ("Tiempo en el sílabo", _flat(meta.get("planned_time"))),
    )
    return "\n".join(rf"\ficha{{{label}}}{{{value}}}" for label, value in entries if value)


def split_annexes_markdown(markdown_source: str) -> tuple[str, str | None]:
    """Split body.md at its first top-level `Anexos` heading.

    The templates in ANNEXES_AFTER_BIBLIOGRAPHY_TEMPLATE_KEYS (APE, ACD, AA)
    render the annexes after the bibliography, so everything from `# Anexos`
    onward is returned separately for {{AFTER_BIBLIOGRAPHY}}. The heading itself travels WITH the annex chunk so
    it renders (and keeps its section number) after the bibliography. When the
    body declares no `# Anexos` heading, nothing splits and the whole body
    renders as one piece -- the missing heading is the structure validator's
    finding to report, not the renderer's.
    """
    lines = markdown_source.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^(#)\s+(.+?)\s*$", line)
        if match and fold_heading(match.group(2)) == ANNEXES_HEADING_FOLDED:
            main = "\n".join(lines[:index]).strip()
            annex = "\n".join(lines[index:]).strip()
            return (f"{main}\n" if main else ""), (f"{annex}\n" if annex else None)
    return markdown_source, None


def markdown_to_latex(
    markdown: str,
    suppress_bibliography_heading: bool = False,
    build_dir: Path | None = None,
    table_styles: TableStylesContext | None = None,
    figure_placement: str = "tbp",
    definition_lists: bool = False,
    booktabs_tables: bool = False,
    compact_headings: bool = False,
) -> str:
    r"""Convert the report body to LaTeX.

    ``definition_lists`` turns Pandoc-style definition lists (a term line
    followed by ``: definition``) into ``description`` environments. It is off
    by default: a template opts in (``DEFINITION_LIST_TEMPLATE_KEYS``) because
    it restyles ``description`` for them. Everywhere else the same lines keep
    rendering as the paragraph they have always been.

    ``booktabs_tables`` emits tables as horizontal rules only (top, header,
    bottom) with a ``\reporttablehead`` header cell the template styles, and
    ``compact_headings`` reserves five lines before a heading instead of a
    page-sized look-ahead. Both are opt-in per template
    (``BOOKTABS_TEMPLATE_KEYS``, ``COMPACT_HEADING_TEMPLATE_KEYS``); the
    defaults keep the legacy grid table and look-ahead the other templates
    were tuned against.
    """
    lines = markdown.splitlines()
    output: list[str] = []
    paragraph: list[str] = []
    list_stack: list[tuple[int, str]] = []
    # Annex figures are pinned ([H]): an annex page often holds only its
    # heading, so a float would leave it empty and move to the next page.
    in_annex = False

    def split_table_row(row: str) -> list[str]:
        # GFM: `\|` is a literal pipe inside a cell, never a column break.
        stripped = re.sub(r"(?<!\\)\|$", "", row.strip()).lstrip("|")
        return [cell.strip().replace(r"\|", "|") for cell in re.split(r"(?<!\\)\|", stripped)]

    def is_table_separator(row: str) -> bool:
        cells = split_table_row(row)
        return bool(cells) and all(re.match(r"^:?-{3,}:?$", cell) for cell in cells)

    def booktabs_alignments(rows: list[list[str]], columns: int, markers: list[str]) -> list[str]:
        # An explicit marker in the separator row wins (`:---:` centered,
        # `---:` right, `:---` left). Otherwise the first column reads left, a
        # column of short values (numbers, yes/no, codes) is centered as in the
        # mockups, and any column with running text reads left.
        names: list[str] = []
        for index in range(columns):
            marker = markers[index] if index < len(markers) else ""
            if marker.startswith(":") and marker.endswith(":"):
                names.append("centering")
            elif marker.endswith(":"):
                names.append("raggedleft")
            elif marker.startswith(":"):
                names.append("raggedright")
            elif index == 0:
                names.append("raggedright")
            else:
                cells = [re.sub(r"[*`$_]", "", row[index]) for row in rows[1:] if index < len(row)]
                names.append("centering" if all(len(cell) <= 12 for cell in cells) else "raggedright")
        return names

    def render_booktabs_table(rows: list[list[str]], columns: int, markers: list[str]) -> None:
        # Horizontal rules only, as in the approved AA-B and ACD-B mockups. Still
        # one page-breakable xltabular: long cell text wraps (#26) at any column
        # count.
        # Column widths follow the content: X columns share the width in
        # proportion to their longest cell (clamped, so a long sentence cannot
        # starve a short column), instead of equal thirds. The \hsize factors
        # must add up to the number of columns, which tabularx requires.
        lengths = [
            min(max(max(
                (len(re.sub(r"[*`$_]", "", row[index])) for row in rows[1:] if index < len(row)),
                default=0,
            ), 8), 48)
            for index in range(columns)
        ]
        weights = [round(columns * length / sum(lengths), 3) for length in lengths]
        weights[-1] = round(columns - sum(weights[:-1]), 3)
        colspec = " ".join(
            rf">{{\hsize={weight}\hsize\{name}\arraybackslash}}X"
            for weight, name in zip(weights, booktabs_alignments(rows, columns, markers))
        )
        header_cells = rows[0] + [""] * (columns - len(rows[0]))
        output.extend([
            r"\Needspace{4\baselineskip}",
            r"\begingroup",
            r"\small",
            r"\renewcommand{\arraystretch}{1.2}",
            rf"\begin{{xltabular}}{{\textwidth}}{{@{{}}{colspec}@{{}}}}",
            r"\toprule",
            " & ".join(r"\reporttablehead{" + convert_inline(cell) + "}" for cell in header_cells) + r" \\",
            r"\midrule",
            r"\endhead",
        ])
        for row in rows[1:]:
            cells = row + [""] * (columns - len(row))
            output.append(" & ".join(convert_inline(cell) for cell in cells) + r" \\")
        output.extend([
            r"\bottomrule",
            r"\end{xltabular}",
            r"\endgroup",
            "",
        ])

    def render_table(rows: list[list[str]], markers: list[str] | None = None) -> None:
        if len(rows) < 2:
            return
        columns = max(len(row) for row in rows)
        if booktabs_tables:
            render_booktabs_table(rows, columns, markers or [])
            return
        # Clean bordered grid: visible rows (\hline) and columns (| separators),
        # centered alignment, subtle gray header, consistent padding. Both
        # branches emit a page-breakable environment (xltabular/longtable)
        # instead of an atomic float — a table too tall for the remaining
        # page space must flow onto the next page, not strand the heading
        # above it while the whole table jumps as one block.
        if columns <= 2:
            # Long cell text must wrap (#26): fixed `c` columns overflow the
            # page on any sentence longer than the column. Each column gets an
            # equal, centered paragraph width derived from \textwidth (8pt per
            # column covers the 2x3pt \tabcolsep plus the vertical rules),
            # keeping grid, font and page-break behavior unchanged.
            col_width = rf"\dimexpr(\textwidth-{8 * columns}pt)/{columns}\relax"
            colspec = " | ".join(
                [rf">{{\centering\arraybackslash}}p{{{col_width}}}"] * columns
            )
            env = "longtable"
            table_open = rf"\begin{{{env}}}{{| {colspec} |}}"
            font_size = r"\small"
        else:
            # Centered grid columns with automatic text wrapping via xltabular
            colspec = " | ".join([r">{\centering\arraybackslash}X"] * columns)
            env = "xltabular"
            table_open = rf"\begin{{{env}}}{{\textwidth}}{{| {colspec} |}}"
            font_size = r"\footnotesize"

        def normalized(row: list[str]) -> list[str]:
            return row + [""] * (columns - len(row))

        header_cells = normalized(rows[0])
        # No \begin{table}[H]/\centering — longtable/xltabular are not floats
        # and center themselves (\LTleft=\LTright=\fill by default). The
        # font-size/spacing declarations need an explicit group since the
        # table environment no longer provides one.
        output.extend([
            r"\Needspace{4\baselineskip}",
            r"\begingroup",
            font_size,
            r"\renewcommand{\arraystretch}{1.2}",
            r"\setlength{\tabcolsep}{3pt}",
            table_open,
            r"\hline",
            r"\rowcolor[gray]{0.92}",
            " & ".join(r"\textbf{" + convert_inline(cell) + "}" for cell in header_cells) + r" \\",
            r"\hline",
            r"\endhead",
        ])
        for idx, row in enumerate(rows[1:]):
            output.append(" & ".join(convert_inline(cell) for cell in normalized(row)) + r" \\")
            output.append(r"\hline")
        output.extend([
            rf"\end{{{env}}}",
            r"\endgroup",
            "",
        ])

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            text = " ".join(item.strip() for item in paragraph)
            # A "Tabla N." caption or a "**Código N.**" listing label must not be
            # stranded at a page foot apart from its table or listing.
            if re.match(r"^(Tabla|Table)\s+\d+\.|^\*\*(Código|Listing)\s+\S+?\.\*\*", text):
                output.append(r"\Needspace{8\baselineskip}")
            output.append(convert_inline(text))
            output.append("")
            paragraph = []

    def close_list() -> None:
        while list_stack:
            _, env = list_stack.pop()
            output.append(rf"\end{{{env}}}")
            output.append("")

    def open_list(env: str, indent: int) -> None:
        while list_stack and (list_stack[-1][0] > indent or
                              (list_stack[-1][0] == indent and list_stack[-1][1] != env)):
            _, previous = list_stack.pop()
            output.append(rf"\end{{{previous}}}")
        if not list_stack or list_stack[-1] != (indent, env):
            output.append(rf"\begin{{{env}}}")
            list_stack.append((indent, env))

    def render_code_block(code_lines: list[str], language: str = "") -> None:
        r"""Emit a fenced block as a styled, page-breakable ``lstlisting``.

        The look lives in ``LISTING_PREAMBLE`` (injected into every template),
        so this only picks the style and the listings language. The content is
        emitted untouched — neither ``latex_escape()`` nor ``convert_inline()``
        may run over it — except for a literal ``\end{lstlisting}``, which
        would otherwise close the environment from the inside.
        """
        block = list(code_lines)
        while block and not block[0].strip():
            block.pop(0)
        while block and not block[-1].strip():
            block.pop()
        if not block:
            return
        options = ["style=reportcode"]
        lst_language = LISTING_LANGUAGES.get(language.split()[0].lower()) if language.split() else None
        if lst_language:
            options.append(f"language={lst_language}")
        output.append(rf"\begin{{lstlisting}}[{', '.join(options)}]")
        output.extend(line.rstrip().replace(r"\end{lstlisting}", r"\end {lstlisting}") for line in block)
        output.extend([
            r"\end{lstlisting}",
            "",
        ])

    def starts_block(text: str) -> bool:
        """A line other block rules own: never a definition term or lazy continuation."""
        return bool(
            re.match(r"^(#{1,4}\s|[-*]\s|\d+[.)]\s|\\(?:begin|end)\{|!\[|\$\$|<!--)", text)
            or CODE_FENCE_RE.match(text)
            or "|" in text
        )

    def definition_start(index: int) -> int | None:
        """Index of the ``: definition`` line that follows the term at ``index``.

        One blank line between the term and its definition is allowed (a
        "loose" item); anything else means the line is not a term.
        """
        following = index + 1
        if following < len(lines) and not lines[following].strip():
            following += 1
        if following < len(lines) and DEFINITION_LINE_RE.match(lines[following].strip()):
            return following
        return None

    def is_definition_term(index: int) -> bool:
        text = lines[index].strip()
        return (
            bool(text)
            and not DEFINITION_LINE_RE.match(text)
            and not starts_block(text)
            and definition_start(index) is not None
        )

    def consume_definition_list(start: int) -> int:
        """Emit the run of definition items beginning at term ``start``; return the next line.

        A definition is the text after ``: `` plus its continuation lines (up
        to a blank line or the next block); extra ``: `` lines under the same
        term are further paragraphs of that item. Its content is inline text.
        """
        output.append(r"\begin{description}")
        term_index = start
        resume = start
        while True:
            definitions: list[str] = []
            position = definition_start(term_index)
            while position is not None:
                match = DEFINITION_LINE_RE.match(lines[position].strip())
                parts = [match.group(1).strip()]
                position += 1
                while position < len(lines) and lines[position].strip():
                    text = lines[position].strip()
                    indented = lines[position][:1] in {" ", "\t"}
                    if DEFINITION_LINE_RE.match(text) or (
                        not indented and (starts_block(text) or is_definition_term(position))
                    ):
                        break
                    parts.append(text)
                    position += 1
                definitions.append(" ".join(parts))
                resume = position
                while position < len(lines) and not lines[position].strip():
                    position += 1
                if position >= len(lines) or not DEFINITION_LINE_RE.match(lines[position].strip()):
                    position = None
            term = convert_inline(lines[term_index].strip())
            body = "\n\n".join(convert_inline(text) for text in definitions)
            output.append(rf"\item[{{{term}}}] {body}")
            following = resume
            while following < len(lines) and not lines[following].strip():
                following += 1
            if following < len(lines) and is_definition_term(following):
                term_index = following
                continue
            break
        output.append(r"\end{description}")
        output.append("")
        return resume

    def find_closing_fence(marker: str, start: int) -> int | None:
        """Index of the fence that closes the block opened at ``start - 1``."""
        for index in range(start, len(lines)):
            if is_closing_fence(lines[index], marker):
                return index
        return None

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            if list_stack:
                next_line = next((item for item in lines[i + 1:] if item.strip()), "")
                next_indent = len(next_line) - len(next_line.lstrip())
                if not next_line or (next_indent < list_stack[0][0] or
                    (next_indent == list_stack[0][0] and not re.match(r"(?:[-*]|\d+[.)])\s+", next_line.strip()))):
                    close_list()
            i += 1
            continue

        # A table-style directive (issue #13) is an inert HTML comment: it
        # must never render as visible paragraph text, whether or not
        # table_styles is active for this build (context_for_table already
        # consumes it when it is; a disabled/undirected build just drops it).
        if TABLE_STYLE_DIRECTIVE_RE.match(stripped):
            i += 1
            continue

        # Fences come first: a code line may contain anything, including the
        # pipes, hashes and dashes every other block rule keys on.
        fence = CODE_FENCE_RE.match(stripped)
        if fence:
            closing = find_closing_fence(fence.group("marker")[0], i + 1)
            if closing is None:
                # Unterminated fence: drop the stray marker and keep parsing.
                # Consuming everything to EOF would turn the rest of the
                # document — headings, tables, lists — into literal text.
                #
                # Recovering is right; recovering silently is not. The block's
                # lines now reflow as prose, which is precisely the defect
                # fence support exists to prevent, so say where it started.
                print(
                    f"Aviso: cerca de código sin cerrar en la línea {i + 1} "
                    f"({stripped}); su contenido se reflowará como texto "
                    "corriente. Cerrá el bloque para que salga como código.",
                    file=sys.stderr,
                )
                i += 1
                continue
            flush_paragraph(); close_list()
            render_code_block(lines[i + 1 : closing], fence.group("language").strip())
            i = closing + 1
            continue

        if "|" in stripped and i + 1 < len(lines) and is_table_separator(lines[i + 1]):
            flush_paragraph(); close_list()
            table_start = i
            table_rows = [split_table_row(stripped)]
            i += 2
            while i < len(lines) and "|" in lines[i].strip() and lines[i].strip():
                table_rows.append(split_table_row(lines[i]))
                i += 1
            if table_styles is not None:
                header, body_rows = table_rows[0], table_rows[1:]
                table_key, context = context_for_table(lines, table_start, header, body_rows)
                if table_key is None:
                    raise SystemExit(
                        f"Tabla sin directiva table-style en la línea {table_start + 1}: "
                        "con table_styles.enabled: true en report.yml, cada tabla debe "
                        "declarar '<!-- table-style: <key> purpose=... -->' inmediatamente "
                        "antes (issue #13; sin estilo genérico de reemplazo)."
                    )
                request = table_styles.request_for(table_key, context)
                receipt = resolve_table_style(request, table_styles.catalog)
                selected_style = table_styles.catalog.styles[receipt.style_id]
                output.extend(render_styled_table_latex(
                    header=header,
                    rows=body_rows,
                    style=selected_style,
                    status_indicators=table_styles.catalog.status_indicators,
                    convert_inline=convert_inline,
                    emphasis_column=context.emphasis_column,
                ))
            else:
                render_table(table_rows, split_table_row(lines[table_start + 1]))
            continue

        # finalanswer{...} —→ answerbox environment (before display_math)
        if stripped.startswith("finalanswer{"):
            flush_paragraph(); close_list()
            depth = 0
            content_start = len("finalanswer{")
            i_pos = content_start
            while i_pos < len(stripped) and depth >= 0:
                if stripped[i_pos] == "{":
                    depth += 1
                elif stripped[i_pos] == "}":
                    depth -= 1
                i_pos += 1
            if depth == -1:
                content = stripped[content_start:i_pos-1].strip()
                output.extend([
                    r"\begin{answerbox}",
                    r"\[",
                    content,
                    r"\]",
                    r"\end{answerbox}",
                    "",
                ])
            else:
                # fallback: unmatched braces — treat as plain paragraph
                paragraph.append(stripped)
            i += 1
            continue

        display_math = re.match(r"^\$\$(?P<formula>.+)\$\$$", stripped)
        if display_math:
            flush_paragraph(); close_list()
            output.extend([
                r"\[",
                display_math.group("formula").strip(),
                r"\]",
                "",
            ])
            i += 1
            continue

        image = re.match(r"!\[(?P<caption>[^\]]*)\]\((?P<src>[^)]+)\)", stripped)
        if image:
            flush_paragraph(); close_list()
            caption = convert_inline(image.group("caption"))
            caption = re.sub(r"\\url\{([^}]+)\}", r"\\protect\\url{\1}", caption)
            raw_src = image.group("src")
            resolved = resolve_figure(raw_src, build_dir) if build_dir is not None else None
            src = latex_escape(os.path.relpath(resolved, build_dir) if resolved is not None and build_dir is not None else raw_src)
            options = figure_includegraphics_options(resolved)
            output.extend([
                r"\Needspace{6\baselineskip}",
                rf"\begin{{figure}}[{'H' if in_annex else figure_placement}]",
                r"\centering",
                rf"\includegraphics[{options}]{{{src}}}",
                rf"\caption{{{caption}}}",
                r"\end{figure}",
                "",
            ])
            i += 1
            continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            flush_paragraph(); close_list()
            level = len(heading.group(1))
            raw_title = heading.group(2).strip()
            if level == 1:
                in_annex = fold_heading(raw_title).startswith("anexo")
            if is_bibliography_heading(raw_title) and (
                suppress_bibliography_heading
                or not any(rest.strip() for rest in lines[i + 1 :])
            ):
                # A dropped heading is one the template title would
                # duplicate: an empty trailing one (historical), or, when
                # the citation-driven bibliography prints, any heading
                # whose title \printbibliography prints itself (#26).
                # Content under a suppressed heading still renders.
                i += 1
                continue
            title = convert_inline(raw_title)
            title = re.sub(r"\\url\{([^}]+)\}",
                           r"\\texorpdfstring{\\url{\1}}{\1}", title)
            command = {1: "section", 2: "subsection", 3: "subsubsection"}.get(level, "paragraph")
            if compact_headings:
                # Enough for the heading and a few lines of what follows; a
                # page-sized look-ahead strands a gap at the foot of the page.
                needspace_lines = 5 if level == 1 else 4
            elif raw_title.casefold() in {"conclusiones", "conclusión", "conclusion"}:
                needspace_lines = 18
            elif level == 1:
                needspace_lines = 16
            elif level == 2:
                needspace_lines = 10
            else:
                needspace_lines = 8
            output.append(rf"\Needspace{{{needspace_lines}\baselineskip}}")
            output.append(rf"\{command}{{{title}}}")
            output.append("")
            i += 1
            continue

        # Raw LaTeX commands passthrough — \newpage, \clearpage
        if stripped in ("\\newpage", "\\clearpage", "\\pagebreak"):
            flush_paragraph()
            close_list()
            output.append(stripped)
            output.append("")
            i += 1
            continue

        # Passthrough for \begin{...} and \end{...} commands
        if re.match(r"^\\(begin|end)\{", stripped):
            flush_paragraph()
            close_list()
            output.append(stripped)
            output.append("")
            i += 1
            continue

        # Horizontal rule —→ \newpage (page break in PDF output)
        if re.match(r"^-{3,}$", stripped):
            flush_paragraph()
            close_list()
            output.append(r"\newpage")
            output.append("")
            i += 1
            continue

        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet:
            flush_paragraph()
            open_list("itemize", len(line) - len(line.lstrip()))
            output.append(r"\item " + convert_inline(bullet.group(1)))
            i += 1
            continue

        # Ordered lists — "1." and "1)" alike. Without this the numbers stay in
        # the paragraph buffer and the whole procedure renders as one justified
        # run-on line.
        ordered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if ordered:
            flush_paragraph()
            open_list("enumerate", len(line) - len(line.lstrip()))
            output.append(r"\item " + convert_inline(ordered.group(1)))
            i += 1
            continue

        if definition_lists and not list_stack and not paragraph and is_definition_term(i):
            i = consume_definition_list(i)
            continue

        if list_stack and len(line) - len(line.lstrip()) > list_stack[0][0]:
            flush_paragraph()
            while len(list_stack) > 1:
                _, env = list_stack.pop()
                output.append(rf"\end{{{env}}}")
            output.append(convert_inline(stripped))
            i += 1
            continue
        paragraph.append(stripped)
        i += 1

    flush_paragraph(); close_list()
    return "\n".join(output).strip() + "\n"


# Sentinel comment markers in unl-report.tex bracket the cover fields that
# routing.md reserves for the academic route: subject, activity,
# parallel (the framed box) and teacher (the DOCENTE block). The markers keep
# the template itself route-agnostic -- render_tex() below decides, per
# report, whether to strip just the marker lines (keeping the block
# byte-for-byte, for the academic route) or the whole marked block including
# its content (every other route, where these fields must not appear at all,
# not even empty).
COVER_SENTINELS = ("COVER_ACADEMIC_BOX", "COVER_TEACHER_BLOCK")

# Only these template keys resolve to unl-report.tex (see TEMPLATE_ALIASES),
# the one template that carries the sentinel contract above. plain-report.tex
# has no titlepage at all, and chamba-overleaf.tex has a titlepage but never
# declared these markers -- render_tex() must never demand them there.
UNL_TEMPLATE_KEYS = frozenset({"default", "unl", "unl_report"})

# Only these template keys resolve to ape-report.tex, the teacher's Word
# replica.
APE_TEMPLATE_KEYS = frozenset({"ape", "ape_report"})
# Likewise for acd-report.tex, the ACD session record sheet.
ACD_TEMPLATE_KEYS = frozenset({"acd", "acd_report"})
# And for aa-report.tex, the editorial autonomous-learning report.
AA_TEMPLATE_KEYS = frozenset({"aa", "aa_report"})

# Template capabilities, not per-format special cases: a template that lists its
# keys here gets the behaviour, and a new template opts in with one entry.
#
# On these templates the fixed `# Anexos` section must render AFTER the
# bibliography, so render_tex() splits body.md at that heading (see
# split_annexes_markdown) and emits it through {{AFTER_BIBLIOGRAPHY}}.
ANNEXES_AFTER_BIBLIOGRAPHY_TEMPLATE_KEYS = APE_TEMPLATE_KEYS | ACD_TEMPLATE_KEYS | AA_TEMPLATE_KEYS
# These templates restyle `description` as a label column, so render_tex()
# turns Pandoc definition lists (`term` / `: definition`) into it.
DEFINITION_LIST_TEMPLATE_KEYS = ACD_TEMPLATE_KEYS
# These templates follow mockups with booktabs tables, figures set where they
# are introduced and a short heading look-ahead, so render_tex() opts the
# converter into each (see markdown_to_latex).
BOOKTABS_TEMPLATE_KEYS = ACD_TEMPLATE_KEYS | AA_TEMPLATE_KEYS
INLINE_FIGURE_TEMPLATE_KEYS = ACD_TEMPLATE_KEYS | AA_TEMPLATE_KEYS
COMPACT_HEADING_TEMPLATE_KEYS = ACD_TEMPLATE_KEYS | AA_TEMPLATE_KEYS

# The APE annexes heading: the last fixed section of the teacher's document.
# Folded (accent/case-insensitive) so `# Anexos` and `# ANEXOS` both split.
ANNEXES_HEADING_FOLDED = "anexos"

# The titlepage environment, used to scope every sentinel match: a lookalike
# sentinel string sitting in body content (e.g. inside a fenced code block,
# which renders unescaped) must never be read as a real marker.
_TITLEPAGE_RE = re.compile(r"\\begin\{titlepage\}.*?\\end\{titlepage\}", re.DOTALL)


def _cover_sentinel_re(sentinel: str, marker: str) -> re.Pattern[str]:
    """A sentinel marker line, tolerant of trailing whitespace and CRLF.

    A plain, untolerant match silently no-ops on any formatting drift --
    exactly the failure this guards against: a mismatched marker must fail
    the build loudly, never leak the academic cover onto a non-academic
    route (or silently drop it on the academic one).
    """
    return re.compile(rf"[ \t]*% {re.escape(sentinel)}:{marker}[ \t]*\r?\n")


def _apply_cover_sentinels(
    template: str, keep_academic_only_fields: bool, template_path: Path
) -> str:
    """Strip (or keep) the UNL cover's academic-only sentinel-marked blocks.

    Scoped to the ``titlepage`` environment only (see ``_TITLEPAGE_RE``).
    Every sentinel pair must appear exactly once inside it -- on EITHER
    route, since the template contract requires both -- or the build fails
    loudly instead of silently rendering or dropping the academic cover
    fields.
    """
    match = _TITLEPAGE_RE.search(template)
    if not match:
        return template
    section = match.group(0)
    for sentinel in COVER_SENTINELS:
        begin_re = _cover_sentinel_re(sentinel, "BEGIN")
        end_re = _cover_sentinel_re(sentinel, "END")
        begins = begin_re.findall(section)
        ends = end_re.findall(section)
        if len(begins) != 1 or len(ends) != 1:
            raise SystemExit(
                f"Marcador de portada '{sentinel}' incompleto en {template_path}: "
                "se esperaba exactamente un BEGIN y un END dentro de "
                r"\begin{titlepage}...\end{titlepage} "
                f"(BEGIN={len(begins)}, END={len(ends)})"
            )
        if keep_academic_only_fields:
            section = begin_re.sub("", section)
            section = end_re.sub("", section)
        else:
            block_re = re.compile(
                rf"[ \t]*% {re.escape(sentinel)}:BEGIN[ \t]*\r?\n"
                rf".*?"
                rf"[ \t]*% {re.escape(sentinel)}:END[ \t]*\r?\n",
                re.DOTALL,
            )
            section = block_re.sub("", section)
    return template[: match.start()] + section + template[match.end() :]


# The author/date line of the plain template's title block (templates/plain-report.tex).
AUTHOR_LINE_TEX = (
    "\\noindent{\\sffamily\\small \\reportstudent\n"
    "  \\ifthenelse{\\equal{\\reportdate}{}}{}{\\enskip\\textbullet\\enskip\\reportdate}\\par}\n"
)


def hides_author_line(config: ReportConfig) -> bool:
    """A business document omits the author/date line unless ``metadata.show_author: true``."""
    return config.route == "business" and config.metadata.get("show_author") is not True


def render_tex(config: ReportConfig) -> str:
    template_key = normalize_template_key(template_key_for(config))
    template_path = resolve_template(template_key)
    if not template_path.exists():
        raise SystemExit(f"No existe template LaTeX: {template_path}")
    if not config.body_path.exists():
        raise SystemExit(f"No existe body.md: {config.body_path}")
    template = template_path.read_text(encoding="utf-8")
    if hides_author_line(config):
        template = template.replace(AUTHOR_LINE_TEX, "")
    markdown_source = config.body_path.read_text(encoding="utf-8")
    # Bibliography emission is decided by the body's ACTUAL rendered citations
    # -- not by the mere presence of the .bib file (#26). A raw-Markdown regex
    # would falsely count `[@key]` examples inside fenced code blocks or inline
    # code, which convert_inline() renders as literal text with zero \cite
    # commands. So the first conversion pass decides: only a body whose
    # rendered output carries \cite prints the bibliography (and suppresses a
    # bibliography-named Markdown heading the template title would duplicate).
    build_dir = config.tex_path.parent
    # Opt-in only (issue #13): a report that never declares `table_styles:
    # {enabled: true}` keeps the exact legacy single-style table renderer.
    table_styles = TableStylesContext.from_config(config) if config.table_styles_enabled else None
    # Templates with an after-bibliography annex slot (see
    # ANNEXES_AFTER_BIBLIOGRAPHY_TEMPLATE_KEYS): the fixed `# Anexos` section
    # renders after the bibliography, so it is split off the body before
    # conversion. Other templates keep body.md whole.
    main_source, annex_source = markdown_source, None
    if template_key in ANNEXES_AFTER_BIBLIOGRAPHY_TEMPLATE_KEYS:
        main_source, annex_source = split_annexes_markdown(markdown_source)
    if config.figure_placement == "here":
        figure_spec = "H"
    else:
        # `h` first: the figure stays where it is introduced when it fits.
        figure_spec = "htbp" if template_key in INLINE_FIGURE_TEMPLATE_KEYS else "tbp"
    definition_lists = template_key in DEFINITION_LIST_TEMPLATE_KEYS
    table_layout = {
        "definition_lists": definition_lists,
        "booktabs_tables": template_key in BOOKTABS_TEMPLATE_KEYS,
        "compact_headings": template_key in COMPACT_HEADING_TEMPLATE_KEYS,
    }
    body = markdown_to_latex(
        main_source, build_dir=build_dir, table_styles=table_styles, figure_placement=figure_spec,
        **table_layout,
    )
    # Emission detection reads the MAIN body: the annex chunk follows the
    # bibliography by construction, so its citations (if any) cannot decide
    # whether the bibliography prints before them.
    # ``uncited_bibliography: true`` prints the whole .bib without any \cite.
    emit_bibliography = (r"\cite{" in body or config.uncited_bibliography) and config.bib_path is not None
    if emit_bibliography:
        body = markdown_to_latex(
            main_source, suppress_bibliography_heading=True, build_dir=build_dir,
            table_styles=table_styles, figure_placement=figure_spec,
            **table_layout,
        )
    # Figure detection runs against the Markdown source: once converted, images
    # are \includegraphics commands and the Markdown pattern can never match.
    has_figures = bool(MARKDOWN_IMAGE_RE.search(markdown_source))
    meta = config.metadata
    front_matter = ""
    ai_declaration_latex = ""
    ai_signature_latex = ""
    after_bibliography_latex = ""
    ai_declaration = config.raw.get("ai_declaration") or config.raw.get("declaracion_ia")
    student = meta.get("student") or ""
    date = meta.get("date") or ""
    signature_latex = "\n".join([
        r"\thispagestyle{plain}",
        r"\vspace*{1.15cm}",
        r"\begin{flushright}",
        r"\rule{7.3cm}{0.4pt}\\[-0.1cm]",
        rf"{{\bfseries {cover_field(student)}}}\\",
        "Autor",
        r"\end{flushright}",
        r"\newpage",
        "",
    ])
    if ai_declaration:
        if isinstance(ai_declaration, dict):
            declaration_title = str(ai_declaration.get("title") or "Declaración de uso de IA generativa")
            declaration_text = str(ai_declaration.get("text") or "")
        else:
            declaration_title = "Declaración de uso de IA generativa"
            declaration_text = str(ai_declaration)
        declaration_latex = "\n".join([
            r"\Needspace{5\baselineskip}",
            rf"\section*{{{convert_inline(declaration_title)}}}",
            rf"\addcontentsline{{toc}}{{section}}{{{convert_inline(declaration_title)}}}",
            "",
            convert_inline(declaration_text),
            "",
        ])
        if str(config.raw.get("ai_declaration_position") or "").strip().lower() in {
            "after_bibliography",
            "after-bibliography",
            "after_bib",
        }:
            # Strip the trailing \newpage from signature when placed
            # after bibliography — avoids a blank end-page
            sig_no_newpage = signature_latex.rstrip()
            if sig_no_newpage.endswith(r"\newpage"):
                sig_no_newpage = sig_no_newpage[: -len(r"\newpage")].rstrip()
            after_bibliography_latex = declaration_latex + "\n" + sig_no_newpage
        else:
            front_matter = declaration_latex
            ai_declaration_latex = declaration_latex
            ai_signature_latex = signature_latex
    if template_key in {"chamba_overleaf", "overleaf_chamba"} and not ai_declaration_latex and not after_bibliography_latex:
        student = meta.get("student") or ""
        date = meta.get("date") or ""
        ai_declaration_latex = "\n".join([
            r"\section*{Declaración de uso de IA Generativa}",
            r"\addcontentsline{toc}{section}{Declaración de uso de IA Generativa}",
            rf"Yo, \textbf{{{latex_escape(student)}}}, en calidad de autor, declaro de manera transparente y responsable el uso de herramientas de Inteligencia Artificial Generativa (IAG) durante el desarrollo del presente trabajo, en conformidad con los principios de integridad académica, ética investigativa y buenas prácticas en el uso de tecnologías emergentes.",
            "",
            r"\subsection*{1. Alcance del uso de IA generativa}",
            "El uso de herramientas de IAG se ha limitado a funciones de apoyo, sin sustituir el juicio crítico ni la autoría intelectual del autor. En particular, se han utilizado para:",
            r"\begin{itemize}",
            r"\item Mejora de redacción y estilo académico.",
            r"\item Apoyo en la estructuración y conversión del documento a formato LaTeX.",
            r"\item Asistencia técnica para normalizar figuras, referencias y archivo BibTeX.",
            r"\end{itemize}",
            "",
            r"\subsection*{2. Clasificación del uso según GAIDeT}",
            "De acuerdo con la taxonomía GAIDeT, el uso de IA generativa en este trabajo se clasifica en asistencia lingüística, apoyo en organización documental y asistencia técnica de formato.",
            "",
            r"\subsection*{3. Validación y responsabilidad}",
            "Todo contenido asistido por IA ha sido revisado, validado y adaptado por el autor, quien asume la responsabilidad total sobre la calidad, veracidad y originalidad del trabajo.",
            "",
            r"\subsection*{4. Consideraciones éticas}",
            "El uso de IA se realizó respetando principios de honestidad académica, normativas institucionales de la Universidad Nacional de Loja y buenas prácticas internacionales.",
            "",
            rf"\begin{{flushright}}Loja, Ecuador, {latex_escape(date)}\end{{flushright}}",
            "",
        ])
        ai_signature_latex = signature_latex
    # Annexes land after the bibliography, BEFORE any after-bibliography
    # declaration block: Anexos is the last fixed section of these formats, and
    # the declaration is automation baggage that always goes last.
    if annex_source is not None:
        annex_body = markdown_to_latex(
            annex_source, suppress_bibliography_heading=emit_bibliography,
            build_dir=build_dir, table_styles=table_styles, figure_placement=figure_spec,
            **table_layout,
        )
        after_bibliography_latex = f"{annex_body}\n{after_bibliography_latex}".strip() + "\n"
    bib_file = config.bib_path.name if config.bib_path else ""
    replacements = {
        "{{TITLE}}": latex_escape(meta.get("title") or config.raw.get("title") or "Reporte académico"),
        "{{TITLE_EN}}": cover_field(meta.get("title_en") or config.raw.get("title_en")),
        "{{SUBJECT}}": latex_escape(meta.get("subject") or ""),
        "{{TEACHER}}": cover_field(meta.get("teacher")),
        "{{STUDENT}}": cover_field(report_authors(meta)),
        "{{AUTHOR_LABEL}}": "AUTORES" if isinstance(meta.get("members"), list) and len(meta["members"]) > 1 else "AUTOR",
        "{{DATE}}": latex_escape(meta.get("date") or ""),
        "{{CAREER}}": latex_escape(meta.get("career") or "Carrera de Computación"),
        "{{PARALLEL}}": latex_escape(meta.get("parallel") or ""),
        "{{ACTIVITY}}": latex_escape(meta.get("activity") or meta.get("tipo") or config.raw.get("activity") or "Informe académico"),
        "{{UNIVERSITY}}": latex_escape(meta.get("university") or "Universidad Nacional de Loja"),
        "{{FACULTY}}": latex_escape(meta.get("faculty") or "Facultad de la Energía, las Industrias y los Recursos Naturales no Renovables"),
        "{{LOGO_PATH}}": latex_escape(LOGO_FILENAME),
        "{{BACKGROUND_PATH}}": latex_escape(BACKGROUND_FILENAME),
        # APE-only machinery (the logo is shared with ACD); harmless no-ops for
        # every other template.
        "{{APE_LOGO_PATH}}": latex_escape(APE_LOGO_FILENAME),
        "{{APE_TITLE}}": latex_escape(ape_report_title(meta)),
        "{{IDENTIFICATION_TABLE}}": ape_identification_table(meta, config.ape_omit_fields),
        # ACD-only machinery; harmless no-ops for every other template.
        "{{ACD_LABEL}}": latex_escape(acd_label(meta)),
        "{{ACD_SESSION_BLOCK}}": acd_session_block(meta),
        "{{ACD_FOOTER}}": acd_footer(meta),
        # AA-only machinery; harmless no-ops for every other template.
        "{{AA_LABEL}}": latex_escape(aa_label(meta)),
        "{{AA_HEADING}}": latex_escape(aa_heading(meta)),
        "{{AA_FICHA}}": aa_ficha(meta),
        "{{BIBLATEX_OPTIONS}}": BIBLATEX_OPTIONS[config.citation_style],
        "{{BIBLATEX_SETUP}}": BIBLATEX_SETUP[config.citation_style],
        "{{BIB_FILE}}": latex_escape(bib_file),
        "{{HAS_BIB}}": "true" if config.bib_path else "false",
        "{{HAS_FIGURES}}": "true" if has_figures else "false",
        "{{SECTION_NUMBERING}}": "true" if section_numbering_enabled(config.raw) else "false",
        # Academic preliminary pages are Route A machinery (routing.md):
        # only the academic route auto-receives the list-of-figures page, and
        # only when the body actually has figures. Non-academic routes render
        # their figures without the academic prelim page, and no explicit
        # template choice reinstates it — the route owns the prelim default.
        # AA reports (the UNL template) never get it: the user dropped the
        # figure index from every AA work.
        "{{LIST_OF_FIGURES}}": (
            r"\newpage\listoffigures"
            if has_figures
            and config.route in {DEFAULT_ROUTE, "academic"}
            and template_key not in UNL_TEMPLATE_KEYS
            else ""
        ),
        "{{FRONT_MATTER}}": front_matter,
        "{{AI_DECLARATION}}": ai_declaration_latex,
        "{{AI_SIGNATURE}}": ai_signature_latex,
        "{{AFTER_BIBLIOGRAPHY}}": after_bibliography_latex,
        "{{LISTING_PREAMBLE}}": LISTING_PREAMBLE,
        "{{BODY}}": body,
        # Emission is citation-driven (#26): only a body that actually cites
        # the .bib file prints the bibliography (and its template title).
        "{{PRINT_BIBLIOGRAPHY}}": (
            (r"\nocite{*}" + "\n" if config.uncited_bibliography else "")
            + rf"\printbibliography[title={{{bibliography_title(config, template_key)}}}]"
            if emit_bibliography
            else "% Bibliography omitted: the body cites nothing from the .bib file (#26)."
        ),
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    if config.citation_style == "apa":
        # Author-year in-text citations; the converter emits \cite for IEEE.
        template = template.replace(r"\cite{", r"\parencite{")
    if template_key in UNL_TEMPLATE_KEYS:
        template = _apply_cover_sentinels(
            template,
            keep_academic_only_fields=config.route == DEFAULT_ROUTE,
            template_path=template_path,
        )
    return template


def validate_assets_exist() -> list[str]:
    """Check that expected build assets exist under ASSETS_DIR.

    Returns a list of error messages (empty if all assets are present).
    Callers may raise SystemExit or collect warnings.
    """
    errors: list[str] = []
    for filename, description in EXPECTED_ASSETS:
        path = ASSETS_DIR / filename
        if not path.exists():
            errors.append(f"Asset faltante: {description} → {path}")
        elif path.stat().st_size < 1_000:
            errors.append(f"Asset sospechosamente pequeño ({path.stat().st_size} bytes): {path}")
    return errors


# Extensions \includegraphics tries when a reference carries no suffix.
FIGURE_SUFFIXES = (".png", ".pdf", ".jpg", ".jpeg", ".eps")
# Same Markdown image syntax as MARKDOWN_IMAGE_RE, capturing the source path.
MARKDOWN_IMAGE_SRC_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def figure_references(markdown: str) -> list[str]:
    """Return every local image path referenced from a Markdown body.

    Remote sources are skipped: LaTeX cannot fetch them, and reporting them as
    missing files would be misleading.
    """
    references: list[str] = []
    for match in MARKDOWN_IMAGE_SRC_RE.finditer(markdown):
        source = match.group(1).strip().split(" ")[0].strip()
        if not source or source.startswith(("http://", "https://", "data:")):
            continue
        references.append(source)
    return references


def resolve_figure(reference: str, build_dir: Path) -> Path | None:
    r"""Resolve a figure reference the way ``\includegraphics`` will.

    Prefer report-relative references, retaining build-relative legacy paths.
    A reference with no suffix matches graphics extensions LaTeX would try.
    """
    candidate = Path(reference)
    bases = [candidate] if candidate.is_absolute() else [build_dir.parent / candidate, build_dir / candidate]
    matches = []
    for base in bases:
        if base.suffix:
            if base.exists():
                matches.append(base)
        else:
            for suffix in FIGURE_SUFFIXES:
                with_suffix = base.with_suffix(suffix)
                if with_suffix.exists():
                    matches.append(with_suffix)
                    break
    if len(matches) > 1 and matches[0] != matches[1]:
        print(f"Ambiguous figure: using {matches[0]} instead of {matches[1]}", file=sys.stderr)
    return matches[0] if matches else None


# Historical default width, unchanged by this fix (#31): a figure earns a
# smaller share of the page only by having a header/footer-hungry aspect
# ratio, never by matching a filename.
FIGURE_WIDTH_FRACTION = 0.86
# A figure can never claim more than this share of \textheight. keepaspectratio
# combined with an explicit width AND height lets LaTeX itself -- which alone
# knows the exact point value of \textheight for the active template -- pick
# whichever constraint actually binds: a wide figure is unaffected (its
# printed height never approaches the cap), a tall one is capped instead of
# floating alone onto a page of its own (the symptom in #31).
FIGURE_MAX_HEIGHT_FRACTION = 0.80


def figure_includegraphics_options(image_path: Path | None) -> str:
    r"""Return the ``\includegraphics`` size options for one figure.

    Sized from the image's own pixel dimensions (read via Pillow, already a
    project dependency) when the figure resolves to a readable file on disk;
    otherwise the historical width-only default applies, exactly as before
    this fix -- ``validate_figure_paths`` reports an unresolved figure as its
    own error, this function never needs to.
    """
    width = f"{FIGURE_WIDTH_FRACTION}\\textwidth"
    if image_path is not None:
        try:
            from PIL import Image

            with Image.open(image_path) as im:
                width_px, height_px = im.size
        except Exception:
            width_px = height_px = 0
        if width_px and height_px:
            return f"width={width},height={FIGURE_MAX_HEIGHT_FRACTION}\\textheight,keepaspectratio"
    return f"width={width},keepaspectratio"


def validate_figure_paths(
    markdown: str, build_dir: Path, docker_mount: Path | None = None
) -> list[str]:
    r"""Check every figure reference before the compiler ever starts.

    ``\includegraphics`` aborts the whole run on a file it cannot open, so an
    unresolvable figure has to be caught here or it becomes a fatal LaTeX error
    buried in the transcript.

    ``docker_mount`` is the host directory bind-mounted at ``/work`` when the
    Docker fallback is the engine. Under Docker an absolute host path simply
    does not exist inside the container, and a relative path that escapes the
    mount is equally invisible — both are rejected up front.

    Returns a list of Spanish error messages (empty when every figure resolves).
    """
    errors: list[str] = []
    for reference in figure_references(markdown):
        if docker_mount is not None and Path(reference).is_absolute():
            errors.append(
                f"Figura con ruta absoluta no utilizable dentro del contenedor Docker: "
                f"{reference}. Use una ruta relativa al directorio de compilación: {build_dir}"
            )
            continue
        resolved = resolve_figure(reference, build_dir)
        if resolved is None:
            errors.append(f"Figura no encontrada: {reference} (resuelta desde {build_dir})")
            continue
        if docker_mount is not None and not is_within(resolved.resolve(), docker_mount.resolve()):
            errors.append(
                f"Figura fuera del directorio montado en Docker ({docker_mount}): "
                f"{reference} → {resolved}"
            )
    return errors


def compilation_failure_message(
    pdf_path: Path, log_path: Path, output: str, max_lines: int = 30
) -> str:
    """Build the failure text for a compilation that produced no PDF.

    The compiler transcript is captured rather than streamed, so a failure used
    to be reported as a bare "no PDF" while the real cause — a missing figure,
    an unavailable package — stayed inside the pipe. This surfaces the lines
    LaTeX itself marks as errors plus the tail of the transcript, and always
    points at the full log for the rest.
    """
    lines = [line.rstrip() for line in (output or "").splitlines()]
    parts = [f"La compilación no generó PDF: {pdf_path}"]
    errors = [line for line in lines if line.startswith("!")]
    if errors:
        parts.extend(["", "Errores reportados por LaTeX:", *errors[:10]])
    tail = [line for line in lines if line.strip()][-max_lines:]
    if tail:
        parts.extend(["", f"Últimas {len(tail)} líneas de la salida del compilador:", *tail])
    parts.extend(["", f"Log completo: {log_path}"])
    return "\n".join(parts)


def is_within(path: Path, base: Path) -> bool:
    """True when ``path`` is ``base`` or lives under it."""
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


def docker_mount_root(config: ReportConfig) -> Path:
    """Pick the host directory to bind-mount into the LaTeX container.

    The old implementation mounted the single derived root and crashed with
    ValueError for any report outside it. Reports now live in the content tree
    (or anywhere the user points at), so the mount is derived from the report
    itself.

    It cannot simply be the report folder: figure references inside body.md are
    relative to the build dir and routinely escape the report
    (``../../../assets/generated/...``). So prefer the widest known root that
    already contains the report — content root first, then the code root for a
    report living inside the checkout (examples, fixtures) — and otherwise fall
    back to the closest common ancestor of the report folder and its build dir.
    A degenerate ancestor (``/``, ``/home``) is refused: mounting that much of
    the host is worse than a build that cannot see a stray figure.
    """
    build_dir = config.tex_path.parent.resolve()
    folder = config.folder.resolve()
    for base in (CONTENT_ROOT, ROOT):
        if is_within(build_dir, base) and is_within(folder, base):
            return base
    if is_within(build_dir, folder):
        return folder
    common = Path(os.path.commonpath([str(folder), str(build_dir)]))
    if len(common.parts) > 2 and is_within(build_dir, common):
        return common
    return build_dir


def docker_compile_command(config: ReportConfig) -> list[str]:
    """Build the ``docker run`` argv for the TeX Live fallback.

    Split out from compile_latex so the path arithmetic is testable without
    Docker installed.
    """
    mount = docker_mount_root(config)
    build_dir = config.tex_path.parent.resolve()
    workdir_rel = relative_subpath(build_dir, mount)
    workdir = "/work" if str(workdir_rel) == "." else f"/work/{workdir_rel.as_posix()}"
    tex_name = config.tex_path.name
    tex_stem = config.tex_path.stem
    return [
        "docker", "run", "--rm",
        "-u", f"{os.getuid()}:{os.getgid()}",
        "-v", f"{mount}:/work",
        "-w", workdir,
        "texlive/texlive:latest",
        "sh", "-lc",
        f"lualatex -interaction=nonstopmode -halt-on-error {tex_name}; "
        f"(biber {tex_stem} || bibtex {tex_stem} || true); "
        f"lualatex -interaction=nonstopmode -halt-on-error {tex_name}; "
        f"lualatex -interaction=nonstopmode -halt-on-error {tex_name}",
    ]


def is_same_file(built: Path, destination: Path) -> bool:
    """Return True when both paths name the same file on disk.

    The final publication step copies the build output to the configured
    ``pdf:`` destination. Those are usually distinct, but a report is entitled
    to point ``pdf:`` straight at the build output — and since final artifacts
    are barred from ``reports/<work>/outputs/``, that is now the obvious thing
    to write. ``shutil.copy2`` raises ``SameFileError`` for a self-copy, which
    killed the build *after* the PDF had been produced successfully.

    Path equality is not enough: a symlinked build directory reaches the same
    inode through a different path. ``Path.samefile`` compares the actual
    files, and a missing destination simply means it is not the built PDF.
    """
    try:
        return built.samefile(destination)
    except (OSError, ValueError):
        return False


def compile_latex(config: ReportConfig) -> None:
    build_dir = config.tex_path.parent
    build_dir.mkdir(parents=True, exist_ok=True)
    if config.bib_path:
        shutil.copy2(config.bib_path, build_dir / config.bib_path.name)
    asset_errors = validate_assets_exist()
    if asset_errors:
        raise SystemExit("Errores de assets:\n- " + "\n- ".join(asset_errors))
    logo = ASSETS_DIR / LOGO_FILENAME
    if logo.exists():
        shutil.copy2(logo, build_dir / logo.name)
    background = ASSETS_DIR / BACKGROUND_FILENAME
    if background.exists():
        shutil.copy2(background, build_dir / background.name)
    ape_logo = ASSETS_DIR / APE_LOGO_FILENAME
    if ape_logo.exists():
        shutil.copy2(ape_logo, build_dir / ape_logo.name)
    engine = shutil.which("latexmk")
    latex_engine = shutil.which("lualatex") or shutil.which("xelatex") or shutil.which("pdflatex")
    docker_engine = None if (engine or latex_engine) else shutil.which("docker")
    if not (engine or latex_engine or docker_engine):
        raise SystemExit("No hay pdflatex/latexmk ni Docker para compilar LaTeX")

    # Figures are resolved before any compiler starts. A figure LaTeX cannot
    # open is a fatal error, and the Docker fallback cannot see an absolute
    # host path at all — both are far clearer here than inside a transcript.
    if config.body_path.exists():
        figure_errors = validate_figure_paths(
            config.body_path.read_text(encoding="utf-8"),
            build_dir,
            docker_mount=docker_mount_root(config) if docker_engine else None,
        )
        if figure_errors:
            raise SystemExit("Errores de figuras:\n- " + "\n- ".join(figure_errors))

    # The transcript is kept so a failure can show what LaTeX actually said.
    transcripts: list[str] = []

    def compile_step(command: list[str], cwd: Path) -> None:
        completed = run(command, cwd=cwd, check=False)
        transcripts.append(completed.stdout or "")

    if engine:
        compile_step([engine, "-lualatex", "-interaction=nonstopmode", "-halt-on-error", config.tex_path.name], build_dir)
    elif latex_engine:
        compile_step([latex_engine, "-interaction=nonstopmode", "-halt-on-error", config.tex_path.name], build_dir)
        if config.bib_path and shutil.which("biber"):
            compile_step(["biber", config.tex_path.stem], build_dir)
        elif config.bib_path and shutil.which("bibtex"):
            compile_step(["bibtex", config.tex_path.stem], build_dir)
        compile_step([latex_engine, "-interaction=nonstopmode", "-halt-on-error", config.tex_path.name], build_dir)
        compile_step([latex_engine, "-interaction=nonstopmode", "-halt-on-error", config.tex_path.name], build_dir)
    else:
        compile_step(docker_compile_command(config), config.folder)

    built_pdf = build_dir / f"{config.tex_path.stem}.pdf"
    if not built_pdf.exists():
        log_path = build_dir / f"{config.tex_path.stem}.log"
        transcript = "\n".join(part for part in transcripts if part.strip())
        if not transcript.strip() and log_path.exists():
            transcript = log_path.read_text(encoding="utf-8", errors="replace")
        raise SystemExit(compilation_failure_message(built_pdf, log_path, transcript))
    config.pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if not is_same_file(built_pdf, config.pdf_path):
        shutil.copy2(built_pdf, config.pdf_path)
    if config.publish_global:
        if GLOBAL_OUTPUTS.resolve() in config.pdf_path.resolve().parents:
            # A report that never declared `pdf:` already lands under the
            # content root's outputs tree (report_config derives it there);
            # publishing a global copy would just copy the file onto itself.
            print(f"PDF final: {config.pdf_path}")
        else:
            global_pdf = publish_global_output(config.pdf_path, config.metadata)
            if global_pdf:
                print(f"PDF publicado por materia: {global_pdf}")
            else:
                print("Aviso: no pude inferir la materia; no se publicó copia global en outputs/<materia>/")


def build(folder: Path, compile_pdf: bool = True) -> ReportConfig:
    config = load_report_config(folder)
    if config.backend != "latex":
        raise SystemExit(f"build_latex_report solo aplica a backend=latex; actual: {config.backend}")
    config.tex_path.parent.mkdir(parents=True, exist_ok=True)
    config.tex_path.write_text(render_tex(config), encoding="utf-8")
    print(f"LaTeX generado: {config.tex_path}")
    if compile_pdf:
        compile_latex(config)
        print(f"PDF generado: {config.pdf_path}")
    return config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path, help="Carpeta del reporte con report.yml")
    parser.add_argument("--tex-only", action="store_true", help="Solo genera build/main.tex")
    args = parser.parse_args()
    build(args.folder, compile_pdf=not args.tex_only)


if __name__ == "__main__":
    main()
