#!/usr/bin/env python3
"""Build the shared full-page UNL cover from a small YAML file.

One template (templates/cover-page.tex) serves every assignment type: ABPR, AA,
APE, ACD... Usage:

    build_cover.py cover.yml [-o portada.pdf] [--tex-only]
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

from report_config import ROOT, latex_escape, read_yaml

TEMPLATE = ROOT / "templates" / "cover-page.tex"
LOGO = ROOT / "assets" / "ape-faculty-logo.png"
DEFAULT_OUTPUT_NAME = "portada.pdf"
ROW_BREAK = r"\\[14pt]"

REQUIRED = ("activity", "subject", "heading")
DEFAULTS = {
    "university": "Universidad Nacional de Loja",
    "faculty": "Facultad de la Energía, las Industrias y los Recursos Naturales no Renovables",
    "career": "Carrera de Computación",
    "city": "Loja, Ecuador",
}
PLACEHOLDERS = (
    "UNIVERSITY", "FACULTY", "CAREER", "LOGO_PATH", "KICKER", "HEADING",
    "TITLE_BLOCK", "FICHA_ROWS", "CITY", "YEAR",
)
MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


class CoverError(Exception):
    """A problem with the cover input that the user can fix."""


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _get(data: dict, key: str) -> str:
    return _text(data.get(key)) or DEFAULTS.get(key, "")


def _date_text(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return f"{value.day} de {MONTHS[value.month - 1]} de {value.year}"
    return _text(value)


def _year(data: dict, date_text: str) -> str:
    explicit = _text(data.get("year"))
    if explicit:
        return explicit
    found = re.search(r"\b(?:19|20)\d{2}\b", date_text)
    return found.group(0) if found else str(date.today().year)


def _members(data: dict) -> list[str]:
    members = data.get("members")
    if isinstance(members, str):
        members = [members]
    names = [_text(name) for name in members or [] if _text(name)]
    if names:
        return names
    return [_text(data.get("student"))] if _text(data.get("student")) else []


def ficha_rows(data: dict) -> str:
    r"""Render the identification panel as tabular rows of ``\cell{label}{value}``.

    Absent fields are dropped and the remaining ones are packed two per row.
    """
    names = _members(data)
    cycle = _text(data.get("cycle"))
    parallel = _text(data.get("parallel"))
    if parallel:
        cycle = f"{cycle}, paralelo {parallel}" if cycle else f"Paralelo {parallel}"
    entries = [
        ("Estudiantes" if len(names) > 1 else "Estudiante", r"\\".join(latex_escape(n) for n in names)),
        ("Docente", latex_escape(_text(data.get("teacher")))),
        ("Asignatura", latex_escape(_text(data.get("subject")))),
        ("Ciclo", latex_escape(cycle)),
        ("Unidad", latex_escape(_text(data.get("unit")))),
        ("Actividad", latex_escape(_text(data.get("activity")))),
        ("Fecha de entrega", latex_escape(_date_text(data.get("date")))),
    ]
    cells = [rf"\cell{{{label}}}{{{value}}}" for label, value in entries if value]
    rows = [" & ".join(cells[i : i + 2]) for i in range(0, len(cells), 2)]
    return "\n".join(
        row + (f" {ROW_BREAK}" if index < len(rows) - 1 else "") for index, row in enumerate(rows)
    )


def build_values(data: dict, logo_name: str = LOGO.name) -> dict[str, str]:
    """Map every template placeholder to its LaTeX-ready value."""
    missing = [key for key in REQUIRED if not _text(data.get(key))]
    if missing:
        raise CoverError(
            "Faltan claves obligatorias en el YAML de la carátula: " + ", ".join(missing)
        )
    title = _text(data.get("title"))
    activity, subject = _text(data["activity"]), _text(data["subject"])
    values = {
        "UNIVERSITY": latex_escape(_get(data, "university")),
        "FACULTY": latex_escape(_get(data, "faculty")),
        "CAREER": latex_escape(_get(data, "career")),
        "LOGO_PATH": logo_name,
        "KICKER": latex_escape(f"ACTIVIDAD {activity.upper()} · {subject.upper()}"),
        "HEADING": latex_escape(_text(data["heading"])),
        "TITLE_BLOCK": rf"\coversubtitle{{{latex_escape(title)}}}" if title else "",
        "FICHA_ROWS": ficha_rows(data),
        "CITY": latex_escape(_get(data, "city")),
        "YEAR": latex_escape(_year(data, _date_text(data.get("date")))),
    }
    return values


def fill_template(template: str, values: dict[str, str]) -> str:
    """Replace ``{{NAME}}`` tokens; an unknown token is an error, never silent."""

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise CoverError(f"Marcador desconocido en la plantilla: {{{{{name}}}}}")
        return values[name]

    return re.sub(r"\{\{([A-Z_]+)\}\}", substitute, template)


def render_tex(data: dict, logo_name: str = LOGO.name) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    return fill_template(template, build_values(data, logo_name))


def compile_command(build_dir: Path, tex_name: str) -> list[str]:
    """LaTeX engine argv: local lualatex when present, TeX Live in Docker otherwise."""
    engine = ["lualatex", "-interaction=nonstopmode", "-halt-on-error", tex_name]
    if shutil.which("lualatex"):
        return engine
    if not shutil.which("docker"):
        raise CoverError("No hay lualatex ni docker disponibles para compilar la carátula.")
    return [
        "docker", "run", "--rm",
        "-u", f"{os.getuid()}:{os.getgid()}",
        "-v", f"{build_dir}:/work",
        "-w", "/work",
        "texlive/texlive:latest",
        "sh", "-lc", " ".join(engine),
    ]


def compile_pdf(tex: str, output: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="cover-build-") as tmp:
        build_dir = Path(tmp)
        (build_dir / "cover.tex").write_text(tex, encoding="utf-8")
        shutil.copy(LOGO, build_dir / LOGO.name)
        command = compile_command(build_dir, "cover.tex")
        result = subprocess.run(
            command, cwd=build_dir, text=True, capture_output=True, check=False
        )
        pdf = build_dir / "cover.pdf"
        if result.returncode != 0 or not pdf.exists():
            sys.stderr.write((result.stdout or "")[-3000:] + (result.stderr or "")[-1000:])
            raise CoverError("La compilación LaTeX de la carátula falló.")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(pdf, output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cover_yml", type=Path, help="YAML con los datos de la carátula")
    parser.add_argument("-o", "--output", type=Path, help="PDF de salida (default: portada.pdf junto al YAML)")
    parser.add_argument("--tex-only", action="store_true", help="solo escribe el .tex, sin compilar")
    args = parser.parse_args(argv)
    try:
        if not args.cover_yml.is_file():
            raise CoverError(f"No existe el archivo YAML: {args.cover_yml}")
        data = read_yaml(args.cover_yml)
        output = args.output or args.cover_yml.parent / DEFAULT_OUTPUT_NAME
        tex = render_tex(data)
        if args.tex_only:
            tex_path = output.with_suffix(".tex")
            tex_path.parent.mkdir(parents=True, exist_ok=True)
            tex_path.write_text(tex, encoding="utf-8")
            print(tex_path)
            return 0
        compile_pdf(tex, output)
        print(output)
        return 0
    except CoverError as error:
        print(f"build_cover: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
