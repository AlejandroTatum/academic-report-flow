#!/usr/bin/env python3
"""Build HTML (and WeasyPrint PDF) previews from a single Markdown file.

This is the *preview* branch of the toolkit. The canonical deliverable
pipeline is ``tools/build_report_auto.py`` -> ``tools/build_latex_report.py``;
this script exists for a quick, dependency-light look at one Markdown file and
does not implement covers, bibliographies or the validation gates.

Usage:
  python3 tools/build_report.py templates/ensayo_unl.md --html outputs/ensayo.html
  python3 tools/build_report.py templates/ensayo_unl.md --pdf outputs/ensayo.pdf

Two behaviours are worth knowing before writing Markdown for it:

- The academic header/metadata block is OPT-IN. It renders only for the fields
  the document actually declares in its YAML front-matter, and `academico:
  false` suppresses it entirely. A document with no front-matter gets no
  institutional furniture at all.
- ``---`` is front-matter only when it opens the file AND the block reads as
  key/value pairs. Anywhere else it is an ordinary horizontal rule. The LaTeX
  branch reads the same sequence as a page break, so a body written for one
  backend does not silently become metadata in the other.
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

import markdown

TOOLS_DIR = str(Path(__file__).resolve().parent)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from markdown_image import IMAGE_PATTERN  # noqa: E402
from table_directives import (  # noqa: E402
    DIRECTIVE_RE as TABLE_STYLE_DIRECTIVE_RE,
    FenceTracker,
    context_for_table,
    is_table_separator,
    split_table_row,
)
from table_html_tokens import render_styled_table_html  # noqa: E402
from table_styles import load_catalog, select_style  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

# Institutional identity, rendered in the page header.
ACADEMIC_HEADER_FIELDS = ("universidad", "facultad", "codigo", "carrera")
# Submission metadata, rendered as the labelled table under the header.
# The third element marks the fields that span the full row width.
ACADEMIC_META_FIELDS = (
    ("nombre", "Nombre", False),
    ("fecha", "Fecha", False),
    ("paralelo", "Paralelo", False),
    ("asignatura", "Asignatura", True),
    ("docente", "Docente", True),
)
ACADEMIC_FLAG_KEYS = ("academico", "academic")
TRUTHY = {"true", "1", "yes", "si", "sí", "on"}

# A front-matter key: a plain identifier, never a sentence.
FRONTMATTER_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*$")
# ``![caption](src "optional title")``
# Pandoc-style citation key, as used by the canonical LaTeX branch.
CITATION_PATTERN = re.compile(r"\[@(?P<key>[A-Za-z0-9_][A-Za-z0-9_:.#$%&+?/-]*)\]")
# Anything carrying a scheme (http:, data:) or a protocol-relative prefix.
EXTERNAL_SRC = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.\-]*:|//)")
FENCE_PATTERN = re.compile(r"^\s*(?:```+|~~~+)")

WARNING_STYLE = (
    "margin:0 0 1.2em;padding:.7em 1em;border-left:4px solid #b45309;"
    "background:#fef3c7;color:#3f2d0b;font-size:.85em;line-height:1.45"
)
MISSING_IMAGE_STYLE = (
    "margin:0;padding:.7em 1em;border:1px dashed #b45309;"
    "background:#fffbeb;color:#3f2d0b;font-size:.85em"
)
CITATION_STYLE = "color:#b45309;font-size:.85em"


def _looks_like_frontmatter(raw: str) -> bool:
    """Return True when a leading ``---`` block reads as YAML key/value pairs.

    The LaTeX branch turns a bare ``---`` line into a page break, so a body
    written for it can open with one. Without this check the text between the
    first two page breaks would be swallowed as metadata and vanish from the
    rendered page. Indented lines are accepted as continuations (list items,
    nested mappings); every top-level line must carry a plain key.
    """
    keys = 0
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1].isspace() or line.lstrip().startswith("-"):
            continue
        key, sep, _ = line.partition(":")
        if not sep or not FRONTMATTER_KEY.match(key.strip()):
            return False
        keys += 1
    return keys > 0


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split a leading YAML front-matter block from the Markdown body.

    Only a block that opens the file and reads as key/value pairs counts. Any
    other ``---`` stays in the body and renders as a horizontal rule.
    """
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    if not _looks_like_frontmatter(raw):
        return {}, text
    body = text[end + 5 :]
    meta: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        value = value.strip().strip('"').strip("'")
        meta[key.strip()] = value
    return meta, body


def wants_academic_block(meta: dict[str, str]) -> bool:
    """Decide whether the document declares itself academic.

    An explicit ``academico``/``academic`` flag wins. Otherwise the block is
    opt-in through the data itself: it renders only when the front-matter
    actually supplies at least one academic field.
    """
    for flag_key in ACADEMIC_FLAG_KEYS:
        if flag_key in meta:
            return meta[flag_key].strip().lower() in TRUTHY
    fields = ACADEMIC_HEADER_FIELDS + tuple(key for key, _, _ in ACADEMIC_META_FIELDS)
    return any(meta.get(key, "").strip() for key in fields)


def _apply_outside_code(md: str, transform) -> str:
    """Run ``transform`` on every line that is not inside a fenced code block."""
    out: list[str] = []
    fence: str | None = None
    for line in md.splitlines(keepends=True):
        marker = FENCE_PATTERN.match(line)
        if fence is None and marker:
            fence = marker.group(0).strip()[:3]
            out.append(line)
            continue
        if fence is not None:
            if marker and marker.group(0).strip().startswith(fence):
                fence = None
            out.append(line)
            continue
        out.append(transform(line))
    return "".join(out)


def image_search_bases(md_dir: Path) -> tuple[Path, ...]:
    """Directories a relative image reference is resolved against, in order.

    The Markdown file's own directory comes first, which is what an author and
    every ordinary Markdown renderer expect. ``<md_dir>/build`` comes second
    because ``build_latex_report.py`` writes its ``.tex`` there and resolves
    figure references from that directory, so real ``body.md`` files in this
    repository carry paths that escape the report from one level deeper
    (``../../../assets/generated/...``). Honouring that convention is what lets
    the same body render in both branches.
    """
    return (md_dir, md_dir / "build")


def resolve_image_src(src: str, md_dir: Path, out_dir: Path) -> tuple[str, bool]:
    """Rewrite an image reference so it resolves from the output directory.

    References in Markdown are relative to the Markdown file (or to the LaTeX
    build directory, see ``image_search_bases``). The HTML is often written
    somewhere else, which breaks them. Returns the rewritten source and whether
    the referenced file was found. External and absolute references come back
    untouched.
    """
    path = src.strip()
    # Drop an optional Markdown title: ![alt](path "title").
    match = re.match(r'^(?P<path>[^\s]+)(?:\s+(?:"[^"]*"|\'[^\']*\'|\([^)]*\)))?$', path)
    if match:
        path = match.group("path")
    path = path.strip("<>")

    if not path or EXTERNAL_SRC.match(path) or path.startswith("#"):
        return path, True
    if Path(path).is_absolute():
        return path, Path(path).exists()

    candidates = [Path(os.path.normpath(base / path)) for base in image_search_bases(md_dir)]
    target = next((candidate for candidate in candidates if candidate.exists()), None)
    found = target is not None
    if target is None:
        target = candidates[0]
    relative = os.path.relpath(target, out_dir)
    return quote(relative.replace(os.sep, "/")), found


def normalize_markdown(
    md: str,
    md_dir: Path | None = None,
    out_dir: Path | None = None,
    warnings: list[str] | None = None,
) -> str:
    """Turn images into semantic figures and neutralise unsupported citations.

    Both rewrites skip fenced code blocks so that documentation about the
    syntax is not mangled by the syntax.
    """
    md_dir = (md_dir or Path.cwd()).resolve()
    out_dir = (out_dir or md_dir).resolve()
    warnings = warnings if warnings is not None else []
    missing: list[tuple[str, str]] = []
    citations: list[str] = []

    def figure(match: re.Match[str]) -> str:
        caption = html.escape(match.group("caption"))
        raw_src = match.group("src")
        resolved, found = resolve_image_src(raw_src, md_dir, out_dir)
        if not found:
            shown = html.escape(raw_src.strip())
            probed = ", ".join(
                str(Path(os.path.normpath(base / raw_src.strip())))
                for base in image_search_bases(md_dir)
            )
            if all(shown != entry for entry, _ in missing):
                missing.append((shown, probed))
            return (
                '<figure class="figure--missing">'
                f'<p style="{MISSING_IMAGE_STYLE}">Imagen no encontrada: <code>{shown}</code></p>'
                f"<figcaption>{caption}</figcaption></figure>"
            )
        return (
            f'<figure><img src="{html.escape(resolved)}" alt="{caption}">'
            f"<figcaption>{caption}</figcaption></figure>"
        )

    def citation(match: re.Match[str]) -> str:
        key = match.group("key")
        if key not in citations:
            citations.append(key)
        return (
            f'<span class="citation-unsupported" style="{CITATION_STYLE}" '
            f'title="Cita sin resolver">[@{html.escape(key)}]</span>'
        )

    text = _apply_outside_code(md, lambda line: IMAGE_PATTERN.sub(figure, line))
    text = _apply_outside_code(text, lambda line: CITATION_PATTERN.sub(citation, line))

    for shown, probed in missing:
        warnings.append(f"Imagen no encontrada: {shown} (se buscó en: {probed})")
    if citations:
        warnings.append(
            "Este generador HTML no procesa citas [@clave] ni bibliografía. "
            f"Sin resolver: {', '.join(citations)}. "
            "Usá tools/build_report_auto.py para el documento entregable."
        )
    return text


def academic_header_html(meta: dict[str, str]) -> str:
    """Render the institutional header from the fields the document declares."""
    university, faculty, code, career = (
        html.escape(meta.get(key, "").strip()) for key in ACADEMIC_HEADER_FIELDS
    )
    lines = []
    if university:
        lines.append(f"<strong>{university}</strong>")
    if faculty:
        lines.append(faculty)
    if code:
        lines.append(code)

    parts = []
    if lines:
        parts.append('<div class="header__university">' + "<br>".join(lines) + "</div>")
    if career:
        parts.append(f'<div class="header__career">{career}</div>')
    if not parts:
        return ""
    return '  <header class="header">\n    ' + "\n    ".join(parts) + "\n  </header>\n"


def academic_meta_html(meta: dict[str, str]) -> str:
    """Render only the declared submission fields; never an orphan label."""
    rows = []
    for key, label, full in ACADEMIC_META_FIELDS:
        value = meta.get(key, "").strip()
        if not value:
            continue
        css = ' class="full"' if full else ""
        rows.append(f"<p{css}><strong>{label}:</strong> {html.escape(value)}</p>")
    if not rows:
        return ""
    return '  <section class="meta">\n    ' + "\n    ".join(rows) + "\n  </section>\n"


def warnings_html(warnings: list[str]) -> str:
    """Render collected build warnings as a visible banner."""
    if not warnings:
        return ""
    items = "".join(f"<li>{html.escape(text)}</li>" for text in warnings)
    return (
        f'  <aside class="build-warning" style="{WARNING_STYLE}" role="note">'
        f"<strong>Avisos de generación</strong><ul>{items}</ul></aside>\n"
    )


def _inline_markdown(text: str) -> str:
    """Render one cell's Markdown (bold/italic/links/code) without a wrapper.

    ``markdown.markdown`` always wraps its output in a single ``<p>``; a
    table cell needs the inline HTML alone. Used as the injected
    ``escape_inline`` for ``render_styled_table_html`` so a directed
    table's cells keep the same inline-formatting support undirected
    tables get for free from python-markdown's "tables" extension.
    """
    fragment = markdown.markdown(text, extensions=["fenced_code"]).strip()
    if fragment.startswith("<p>") and fragment.endswith("</p>"):
        fragment = fragment[len("<p>") : -len("</p>")]
    return fragment


def apply_table_styles(body: str, catalog=None, warnings: list[str] | None = None) -> str:
    """Replace every DIRECTED table with a self-contained styled HTML block.

    Issue #13. There is no ``ReportConfig`` in this preview tool (it takes
    one bare Markdown file, not a report folder), so there is no per-report
    opt-in flag and no teacher/institution override -- only automatic
    contextual selection applies. An UNDIRECTED table (no preceding
    ``<!-- table-style: ... -->`` comment) is left completely untouched, so
    it renders exactly as before through python-markdown's "tables"
    extension: this function never blocks a build.

    A fenced code block is skipped verbatim (directive-looking comments and
    pipe tables inside a code sample -- documentation about the syntax --
    must never be mistaken for a real directive/table), via the same
    ``table_directives.FenceTracker`` ``parse_table_blocks`` uses, so this
    rewrite and the shared directive parser can never disagree on where a
    fence starts or ends. The catalog is
    loaded lazily, only once a directed table is actually found, so an HTML
    build with no tables (or only undirected ones) never depends on it. A
    style-validation ``ValueError`` (an unknown status marker, or a missing/
    out-of-range ``emphasis_column``) is collected into ``warnings`` and the
    table's original Markdown source is left untouched, rather than crashing
    the whole preview build (T4+T5 review R3/R4).
    """
    warnings = warnings if warnings is not None else []
    lines = body.splitlines()
    output: list[str] = []
    i = 0
    fence = FenceTracker()
    while i < len(lines):
        raw_line = lines[i]
        stripped = raw_line.strip()

        if fence.consume(raw_line):
            output.append(raw_line)
            i += 1
            continue

        if not stripped:
            output.append(raw_line)
            i += 1
            continue

        if TABLE_STYLE_DIRECTIVE_RE.match(stripped):
            # Consumed by context_for_table when its table is found below
            # (or silently dropped if orphaned -- an inert HTML comment
            # either way, never visible in the rendered page).
            i += 1
            continue

        if "|" in stripped and i + 1 < len(lines) and is_table_separator(lines[i + 1]):
            table_start = i
            header = split_table_row(stripped)
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip() and "|" in lines[i]:
                rows.append(split_table_row(lines[i]))
                i += 1

            table_key, context = context_for_table(lines, table_start, header, rows)
            if table_key is None:
                output.append(lines[table_start])
                output.append(lines[table_start + 1])
                output.extend(lines[table_start + 2 : i])
                continue

            catalog = catalog or load_catalog()
            try:
                result = select_style(context, catalog)
                style = catalog.styles[result.style_id]
                html_fragment = render_styled_table_html(
                    header=header,
                    rows=rows,
                    style=style,
                    status_indicators=catalog.status_indicators,
                    escape_inline=_inline_markdown,
                    emphasis_column=context.emphasis_column,
                )
            except ValueError as exc:
                warnings.append(
                    f"Tabla '{table_key}' (línea {table_start + 1}) con estilo inválido, "
                    f"se muestra sin estilizar: {exc}"
                )
                output.append(lines[table_start])
                output.append(lines[table_start + 1])
                output.extend(lines[table_start + 2 : i])
                continue

            output.append("")
            output.append(html_fragment)
            output.append("")
            continue

        output.append(raw_line)
        i += 1

    return "\n".join(output)


def render(md_path: Path, css_path: Path, out_dir: Path | None = None) -> str:
    """Render ``md_path`` to a standalone HTML document.

    ``out_dir`` is the directory the HTML will be written to; image references
    are rewritten so they resolve from there. Warnings are collected into a
    visible banner and also echoed on stderr.
    """
    md_path = Path(md_path)
    out_dir = Path(out_dir) if out_dir is not None else md_path.parent
    source = md_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    meta, body = parse_frontmatter(source)

    warnings: list[str] = []
    body = normalize_markdown(body, md_path.parent, out_dir, warnings)
    body = apply_table_styles(body, warnings=warnings)
    body_html = markdown.markdown(body, extensions=["tables", "fenced_code", "attr_list"])

    css = css_path.read_text(encoding="utf-8") if css_path.is_file() else ""
    if not css:
        warnings.append(f"Hoja de estilos no encontrada: {css_path}")

    for text in warnings:
        print(f"Aviso: {text}", file=sys.stderr)

    title = html.escape(
        meta.get("titulo_documento", "").strip()
        or meta.get("titulo", "").strip()
        or md_path.stem
    )

    header = ""
    meta_block = ""
    if wants_academic_block(meta):
        header = academic_header_html(meta)
        meta_block = academic_meta_html(meta)

    report_title = html.escape(meta.get("titulo", "").strip())
    title_block = f'  <div class="report-title">{report_title}</div>\n' if report_title else ""

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>{css}</style>
</head>
<body>
{warnings_html(warnings)}{header}{meta_block}{title_block}  <main>
    {body_html}
  </main>
</body>
</html>
"""


def resolve_css(css_arg: Path) -> Path:
    """Resolve --css against the working directory, then the repository root."""
    if css_arg.is_absolute():
        return css_arg
    from_cwd = Path.cwd() / css_arg
    if from_cwd.is_file():
        return from_cwd
    return REPO_ROOT / css_arg


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Genera una vista previa HTML/PDF de un Markdown. Para entregables "
            "usá tools/build_report_auto.py (pipeline canónico LaTeX)."
        )
    )
    parser.add_argument("markdown_file", type=Path)
    parser.add_argument("--css", type=Path, default=Path("templates/ensayo_unl.css"))
    parser.add_argument("--html", type=Path)
    parser.add_argument("--pdf", type=Path)
    args = parser.parse_args()

    css_path = resolve_css(args.css)
    target = args.html or args.pdf
    out_dir = (target.parent if target else Path.cwd()).resolve()
    if target:
        out_dir.mkdir(parents=True, exist_ok=True)

    html_text = render(args.markdown_file, css_path, out_dir)

    if args.html:
        args.html.write_text(html_text, encoding="utf-8")
        print(f"HTML generado: {args.html}")

    if args.pdf:
        try:
            from weasyprint import HTML
        except ImportError as exc:
            raise SystemExit(
                "Falta WeasyPrint. Instalá en un venv: python3 -m pip install weasyprint"
            ) from exc
        args.pdf.parent.mkdir(parents=True, exist_ok=True)
        HTML(string=html_text, base_url=str(out_dir)).write_pdf(args.pdf)
        print(f"PDF generado: {args.pdf}")

    if not args.html and not args.pdf:
        print(html_text)


if __name__ == "__main__":
    main()
