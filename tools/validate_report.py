#!/usr/bin/env python3
"""Common, backend-aware validation layer for Alejandro's university reports."""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from report_config import ROOT as AUTOMATION_ROOT
from report_config import (
    ACADEMIC_ONLY_METADATA,
    CONTENT_ROOT,
    DEFAULT_ROUTE,
    LOCAL_OUTPUTS_ERROR,
    PLACEHOLDER_RE,
    ReportConfig,
    is_placeholder_value,
    load_report_config,
    relative_label,
    targets_local_outputs,
    unknown_format_message,
    unknown_route_message,
)
from output_router import FINAL_EXTENSIONS, GLOBAL_OUTPUTS, infer_subject_for_path
from structure_contract import parse_structure, structure_confirmation_state
from table_directives import TableDirectiveError, parse_table_blocks
from table_model import OverrideRejectedError, SelectionReceipt, TableStylesContext, resolve_table_style
from table_styles import CatalogError, UnsupportedContextError
from validate_ieee_refs import ValidationResult, validate_ieee
from visual_metadata import validate_visual_manifest

# Visual PDF auditor integration — optional dependency
try:
    # page_issues and default_output_dir come along deliberately: the auditor
    # owns what a finding means and where its artefacts go. Re-deriving either
    # here is how this module used to report the same page as an error and a
    # warning at once, and how a PDF outside the content tree still wrote its
    # renders into it.
    from visual_pdf_auditor import (
        FAILURE,
        WARNING,
        audit_pdf,
        default_output_dir,
        page_issues,
    )
    VISUAL_AUDITOR_AVAILABLE = True
except ImportError:
    VISUAL_AUDITOR_AVAILABLE = False

A4_WIDTH = 595.28
A4_HEIGHT = 841.89

# ---------------------------------------------------------------------------
# Overfull box thresholds
# ---------------------------------------------------------------------------
#
# LaTeX reports every box that does not fit, and a real log carries dozens of
# them. Severity has to be proportional or the signal is buried again.
#
# Below OVERFULL_NOISE_PT the overflow is a sub-point rounding artefact: at
# 300 dpi one point is four pixels, so a fraction of a point is not visible on
# paper and is not worth a line of output.
#
# OVERFULL_CLIPPING_PT is the page margin. Every template compiles with
# `\usepackage[a4paper,margin=2.5cm]{geometry}`, and 2.5 cm is 71.13 pt, so an
# overflow wider than that does not merely intrude into the white margin: it
# reaches the physical paper edge and everything past it is cut off. That is
# lost content, not a typographic blemish, so it is an error. Anything in
# between is visible in the margin but still on the page — a warning.
OVERFULL_NOISE_PT = 1.0
OVERFULL_CLIPPING_PT = 71.13

# Cap on individually listed boxes; the total is always reported.
OVERFULL_REPORT_LIMIT = 8

# LaTeX hard-wraps log lines at `max_print_line` (79 or 80 in practice), so a
# message can be split anywhere. Only a line that long can have been wrapped,
# and only an incomplete message is ever re-joined.
LATEX_LOG_WRAP_MIN_WIDTH = 60
OVERFULL_LOOKAHEAD_LINES = 2

OVERFULL_RE = re.compile(
    r"Overfull \\(?P<kind>[hv])box \((?P<points>\d+(?:\.\d+)?)pt too (?:wide|high)\)"
)
OVERFULL_LINES_RE = re.compile(r"at lines (?P<start>\d+)--(?P<end>\d+)")
OVERFULL_LINE_RE = re.compile(r"at line (?P<start>\d+)\b")
# A page ships out as `[12]`, ` [12<image.png>]` or ` [12`. Version stamps such
# as `[2026/01/01 v1.2]` are excluded by the lookahead.
PAGE_SHIPOUT_RE = re.compile(r"(?:^|[\s)])\[(\d+)(?=[\]\s<{]|$)")

# Intake placeholders: bracket templates such as `[Nombre del estudiante]` and
# Word-style fill-in marks such as `XXX` are instructions, not identity. The
# definition (PLACEHOLDER_RE) and the predicate (is_placeholder_value) live in
# report_config so the route checks and the format checks share one source of
# truth; the name is re-exported here for the callers that import it from this
# module.

# Teacher-required structure (#12): body headings are the source proof that
# the rendered document carries every section the confirmed contract froze.
# Only top-level (H1, a single '#') headings count as section boundaries.
# Every required section title is itself a top-level heading, and a
# subsection (##, ###, ...) lives INSIDE its enclosing section -- matching
# every heading level here used to split a section's text bucket at its
# first subsection, truncating the content criteria/word-count checks for
# everything after it (#12 hardening).
BODY_HEADING_RE = re.compile(r"^(#)\s+(.+?)\s*$")


@dataclass(frozen=True)
class OverfullBox:
    """One `Overfull \\hbox/\\vbox` report parsed out of a LaTeX log."""

    kind: str
    points: float
    start_line: int | None = None
    end_line: int | None = None
    page: int | None = None

    def location(self) -> str:
        parts = []
        if self.page is not None:
            parts.append(f"página {self.page}")
        if self.start_line is not None:
            if self.end_line is not None and self.end_line != self.start_line:
                parts.append(f"líneas {self.start_line}--{self.end_line}")
            else:
                parts.append(f"línea {self.start_line}")
        return ", ".join(parts) if parts else "ubicación no indicada en el log"

    def describe(self) -> str:
        return f"\\{self.kind} de {self.points:.2f}pt ({self.location()})"


def _parse_overfull(window: str, page: int | None) -> OverfullBox | None:
    match = OVERFULL_RE.search(window)
    if match is None:
        return None
    tail = window[match.end():]
    lines_match = OVERFULL_LINES_RE.search(tail)
    if lines_match:
        start = int(lines_match.group("start"))
        end = int(lines_match.group("end"))
    else:
        single = OVERFULL_LINE_RE.search(tail)
        start = int(single.group("start")) if single else None
        end = start
    return OverfullBox(
        kind=f"{match.group('kind')}box",
        points=float(match.group("points")),
        start_line=start,
        end_line=end,
        page=page,
    )


def _overfull_is_complete(window: str) -> bool:
    """True when the window holds a whole message, so no unwrapping is needed."""
    match = OVERFULL_RE.search(window)
    if match is None:
        return False
    tail = window[match.end():].rstrip()
    location = OVERFULL_LINES_RE.search(tail) or OVERFULL_LINE_RE.search(tail)
    if location is None:
        # `has occurred while \output is active` carries no source location.
        return "is active" in tail or "has occurred" in tail
    # A location running to the very end of the line may have been cut by the
    # hard wrap (`... at lines 1780--17` continued by `99`), so it counts as
    # complete only when something follows it.
    return location.end() < len(tail)


def parse_overfull_boxes(log: str) -> list[OverfullBox]:
    """Extract every Overfull box report from a LaTeX log.

    Tolerates a missing, empty or truncated log, and re-joins messages that
    LaTeX hard-wrapped mid-sentence. The page is inferred from the shipout
    markers that precede the message; when the log names no page at all (a
    truncated log, or a run that never shipped a page) it is left unknown
    rather than guessed.
    """
    lines = log.splitlines()
    has_shipouts = any(PAGE_SHIPOUT_RE.search(line) for line in lines)
    next_page = 1
    boxes: list[OverfullBox] = []

    for index, line in enumerate(lines):
        if "Overfull" in line:
            window = line
            steps = 0
            while (
                not _overfull_is_complete(window)
                and steps < OVERFULL_LOOKAHEAD_LINES
                and len(lines[index + steps]) >= LATEX_LOG_WRAP_MIN_WIDTH
                and index + steps + 1 < len(lines)
            ):
                steps += 1
                window += lines[index + steps]
            box = _parse_overfull(window, next_page if has_shipouts else None)
            if box is not None:
                boxes.append(box)
        for marker in PAGE_SHIPOUT_RE.findall(line):
            next_page = int(marker) + 1

    return boxes


def overfull_validation(boxes: list[OverfullBox]) -> ValidationResult:
    """Turn parsed Overfull boxes into proportional errors and warnings."""
    result = ValidationResult()
    relevant = [box for box in boxes if box.points >= OVERFULL_NOISE_PT]
    if not relevant:
        return result

    clipping = [box for box in relevant if box.points >= OVERFULL_CLIPPING_PT]
    visible = [box for box in relevant if box.points < OVERFULL_CLIPPING_PT]

    for box in clipping[:OVERFULL_REPORT_LIMIT]:
        result.errors.append(
            f"Contenido cortado en el borde de la hoja: Overfull {box.describe()} "
            f"supera el margen de {OVERFULL_CLIPPING_PT:.0f}pt; el texto que sobra no se imprime"
        )
    if len(clipping) > OVERFULL_REPORT_LIMIT:
        result.errors.append(
            f"Hay {len(clipping)} desbordes que cortan contenido; "
            f"se listaron los primeros {OVERFULL_REPORT_LIMIT}"
        )

    for box in visible[:OVERFULL_REPORT_LIMIT]:
        result.warnings.append(
            f"Overfull {box.describe()} invade el margen; revisar corte de línea, "
            "URL larga o ancho de tabla"
        )
    if len(visible) > OVERFULL_REPORT_LIMIT:
        result.warnings.append(
            f"Hay {len(visible)} desbordes que invaden el margen; "
            f"se listaron los primeros {OVERFULL_REPORT_LIMIT}"
        )
    return result


@dataclass
class ReportValidation:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    table_style_receipts: list[SelectionReceipt] = field(default_factory=list)

    def add(self, name: str, result: ValidationResult) -> None:
        self.checks.append(name)
        self.errors.extend(result.errors)
        self.warnings.extend(result.warnings)


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def pdf_text_pages(pdf: Path) -> list[str]:
    if not pdf.exists():
        return []
    result = run(["pdftotext", str(pdf), "-"])
    if result.returncode != 0:
        return []
    return result.stdout.split("\f")


def pdfinfo(pdf: Path) -> dict[str, str]:
    if not pdf.exists():
        return {}
    result = run(["pdfinfo", str(pdf)])
    data: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            data[key.strip()] = value.strip()
    return data


def _split_body_by_heading(body: str) -> dict[str, str]:
    """Map each folded top-level (H1) heading title to the text between it
    and the next top-level heading. A subsection heading (##, ###, ...)
    never matches ``BODY_HEADING_RE`` here, so its text -- and its
    subsection line itself -- stays inside the enclosing section's bucket
    rather than starting a new one."""
    from build_latex_report import fold_heading

    sections: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []
    for line in body.splitlines():
        match = BODY_HEADING_RE.match(line)
        if match:
            if current is not None:
                sections[current] = "\n".join(buffer)
            current = fold_heading(match.group(2))
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        sections[current] = "\n".join(buffer)
    return sections


def structure_validation(config: ReportConfig) -> ValidationResult:
    """Enforce a confirmed ``structure:`` contract against the rendered body.

    Absent ``structure:`` means no enforcement here — the intake gate
    (``doc_status``/``structure_contract.structure_confirmation_state``) owns
    confirmation; this check owns the final-source proof once a contract is
    confirmed. A malformed/unconfirmed draft (e.g. the ``"proposed"`` marker)
    is reported as a schema error rather than silently skipped, so a report
    can never reach final validation with an unconfirmed contract in force.
    A confirmed-but-now-stale contract (a recorded source changed or
    disappeared since confirmation) is rejected the same way: final
    validation never certifies a report against a superseded structure.

    Checks, in order: confirmation state (schema + staleness), section
    presence under the exact declared name, declared order, each
    criterion's optional ``content_anchor`` (declared but missing content),
    and each declared quantitative limit (currently ``words``; unsupplied
    limits are never enforced, #6408/R3).
    """
    result = ValidationResult()
    structure = parse_structure(config.raw)
    if structure is None:
        return result

    state, detail = structure_confirmation_state(config)
    if state != "confirmed":
        result.errors.append(
            f"La estructura del reporte no está confirmada ({state}): {detail}"
        )
        return result

    from build_latex_report import fold_heading

    body = (
        config.body_path.read_text(encoding="utf-8", errors="ignore")
        if config.body_path.exists()
        else ""
    )
    body_heads = [
        fold_heading(match.group(2))
        for match in (BODY_HEADING_RE.match(line) for line in body.splitlines())
        if match
    ]
    sections_text = _split_body_by_heading(body)

    required = structure["sections"]
    required_norm = [fold_heading(section["title"]) for section in required]

    missing = [
        section["title"]
        for section, norm in zip(required, required_norm)
        if norm not in body_heads
    ]
    if missing:
        result.errors.append("Faltan secciones requeridas en body.md: " + ", ".join(missing))

    positions = {norm: index for index, norm in enumerate(body_heads)}
    last_seen = -1
    for section, norm in zip(required, required_norm):
        if norm not in positions:
            continue
        if positions[norm] < last_seen:
            result.errors.append(
                f"La sección '{section['title']}' está fuera del orden requerido en body.md"
            )
            break
        last_seen = positions[norm]

    for section, norm in zip(required, required_norm):
        text = sections_text.get(norm)
        if text is None:
            continue  # already reported as missing
        folded_text = fold_heading(text)
        for criterion in section.get("criteria", []):
            anchor = criterion.get("content_anchor") if isinstance(criterion, dict) else None
            if anchor and fold_heading(anchor) not in folded_text:
                result.errors.append(
                    f"La sección '{section['title']}' no cumple el criterio requerido "
                    f"en structure: {criterion.get('text')}"
                )

        limits = section.get("limits") or {}
        words = limits.get("words")
        if words is not None and text is not None:
            count = len(text.split())
            max_words = words.get("max") if isinstance(words, dict) else words
            min_words = words.get("min") if isinstance(words, dict) else None
            if max_words is not None and count > max_words:
                result.errors.append(
                    f"La sección '{section['title']}' excede el límite de palabras "
                    f"({count} > {max_words})"
                )
            if min_words is not None and count < min_words:
                result.errors.append(
                    f"La sección '{section['title']}' no alcanza el mínimo de palabras "
                    f"({count} < {min_words})"
                )
    return result


def metadata_validation(config: ReportConfig) -> ValidationResult:
    """Check report.yml metadata against the report's document route.

    The required set is route-dependent (see ``ROUTE_REQUIRED_METADATA`` in
    report_config). Routes B–D forbid the academic shell, so demanding
    `subject`/`teacher` there left users with one escape: inventing fake
    academic metadata — exactly what the routing contract exists to prevent.

    When a ``format:`` is chosen, its own metadata requirements are checked
    too (``FORMAT_REQUIRED_METADATA``): `ape` and `acd` count placeholder fill-in
    marks ("X", "XXX", "00X", "[...]") as missing, and `libre` requires a
    non-empty ``format_spec:`` description.
    """
    result = ValidationResult()
    if not config.route_is_known:
        # No metadata verdict is possible without a route, and guessing one
        # would reintroduce the silent fallback to Route A.
        result.errors.append(unknown_route_message(config.route))
        return result
    chosen_format = config.format
    if chosen_format is not None and not config.format_is_known:
        # Same rule for the format choice: no verdict on top of a typo.
        result.errors.append(unknown_format_message(chosen_format))
        return result

    meta = config.metadata
    missing = [key for key in config.required_metadata if not str(meta.get(key) or "").strip()]
    if missing:
        result.errors.append("Metadata incompleta en report.yml: " + ", ".join(missing))

    placeholder = [
        key
        for key in config.required_metadata
        if str(meta.get(key) or "").strip() and PLACEHOLDER_RE.match(str(meta.get(key)).strip())
    ]
    if placeholder:
        result.errors.append(
            "Metadata con valores de ejemplo en report.yml: " + ", ".join(placeholder)
        )

    # Group mode is declared by carrying a `members` list (any alias) or an
    # explicit group flag. In group mode the membership must be complete and
    # concrete; an absent, empty or placeholder-filled roster is rejected and
    # the missing members are named.
    members = meta.get("members")
    if members is None:
        members = meta.get("integrantes") or meta.get("miembros")
    group_flag = str(meta.get("group") or meta.get("grupal") or "").strip().lower()
    if members is not None or group_flag in {"true", "1", "yes", "si", "sí", "on"}:
        if not isinstance(members, list) or not members:
            result.errors.append(
                "El reporte es grupal pero metadata.members no trae la nómina "
                "completa de integrantes"
            )
        else:
            missing_members = [
                repr(str(member).strip())
                for member in members
                if not str(member or "").strip() or PLACEHOLDER_RE.match(str(member).strip())
            ]
            if missing_members:
                result.errors.append(
                    "Integrantes con valores vacíos o de ejemplo en metadata.members: "
                    + ", ".join(missing_members)
                )

    if config.route != "academic":
        declared = [key for key in ACADEMIC_ONLY_METADATA if str(meta.get(key) or "").strip()]
        if declared:
            result.warnings.append(
                f"La ruta '{config.route}' no es académica pero report.yml declara "
                "metadata académica: " + ", ".join(declared)
            )

    if config.format_is_known:
        # The teacher's APE table and the ACD session block print the
        # identification fields verbatim, so a leftover fill-in mark ("XXX") is
        # as useless as an empty field.
        if config.format in ("ape", "acd"):
            format_missing = [
                key
                for key in config.format_required_metadata
                if not str(meta.get(key) or "").strip() or is_placeholder_value(meta.get(key))
            ]
        else:
            format_missing = [
                key
                for key in config.format_required_metadata
                if not str(meta.get(key) or "").strip()
            ]
        if format_missing:
            result.errors.append(
                f"Metadata incompleta para el formato '{config.format}' en report.yml: "
                + ", ".join(format_missing)
            )
        if config.format == "libre" and not config.format_spec:
            result.errors.append(
                "El formato 'libre' requiere una descripción del formato deseado "
                "en format_spec: (report.yml)"
            )

    result.errors.extend(structure_validation(config).errors)
    result.errors.extend(section_structure_validation(config).errors)
    return result


# Fixed, ordered body sections per document format. Only level-1 headings
# count; a section's subsections (##, ###, ...) are the author's. Each entry is
# (title, kind):
#   REQUIRED_SECTION   must be present, in this position
#   OPTIONAL_SECTION   may be absent; when present it keeps this position
#   BIBLIOGRAPHY_SLOT  the bibliography; the template prints it
#                      (\printbibliography), so it is never required as an
#                      authored heading, but an authored one (any title the
#                      renderer treats as a bibliography heading) keeps its slot
# Headings outside a format's list are not checked.
REQUIRED_SECTION = "required"
OPTIONAL_SECTION = "optional"
BIBLIOGRAPHY_SLOT = "bibliography"

# APE (new-report-flow): with `format: ape` the body's level-1 headings are the
# teacher's, not the author's. Section 1 ("Datos de Identificación del
# Estudiante y la Práctica") is generated by the builder from metadata (see
# ape_identification_table), so body.md carries exactly the remaining fixed
# sections. The IEEE bibliography printed between Recomendaciones and Anexos is
# biblatex machinery, not an authored heading. "Anexos" may be empty, but it
# must exist: its heading is what moves its content after the bibliography.
SECTION_SPECS: dict[str, tuple[tuple[str, str], ...]] = {
    "ape": (
        ("Objetivo(s) de la Práctica", REQUIRED_SECTION),
        ("Materiales, Reactivos, Equipos y Herramientas", REQUIRED_SECTION),
        ("Procedimiento / Metodología Ejecutada", REQUIRED_SECTION),
        ("Resultados", REQUIRED_SECTION),
        ("Preguntas de Control", REQUIRED_SECTION),
        ("Conclusiones", REQUIRED_SECTION),
        ("Recomendaciones", REQUIRED_SECTION),
        ("Anexos", REQUIRED_SECTION),
    ),
    "aa": (
        ("Objetivo(s)", REQUIRED_SECTION),
        ("Introducción", REQUIRED_SECTION),
        ("Desarrollo", REQUIRED_SECTION),
        ("Conclusiones", REQUIRED_SECTION),
        ("Referencias", BIBLIOGRAPHY_SLOT),
        ("Anexos", OPTIONAL_SECTION),
        ("Declaración de uso de IA", OPTIONAL_SECTION),
    ),
    "acd": (
        ("Objetivo(s)", REQUIRED_SECTION),
        ("Síntesis de contenidos abordados", REQUIRED_SECTION),
        ("Actividades desarrolladas en clase", REQUIRED_SECTION),
        ("Análisis / reflexión", REQUIRED_SECTION),
        ("Conclusiones", REQUIRED_SECTION),
        ("Referencias", BIBLIOGRAPHY_SLOT),
        ("Anexos", OPTIONAL_SECTION),
    ),
}

APE_BODY_HEADINGS: tuple[str, ...] = tuple(title for title, _ in SECTION_SPECS["ape"])


def section_structure_validation(config: ReportConfig) -> ValidationResult:
    """Require the fixed section order of the report's format in body.md.

    Active only for the formats in ``SECTION_SPECS`` (``ape``, ``aa``,
    ``acd``); every other format keeps free section choice. Like
    ``structure_validation``, only top-level (H1) headings count: the body must
    name every required section under its exact title, in the format's order,
    and missing sections are reported together so one pass names every fix
    instead of just the first one. Optional sections may be absent but keep
    their position when present.

    ``ape_omit_sections`` / ``ape_omit_fields`` are APE-only knobs: they are
    read and validated for ``format: ape`` and ignored for every other format.
    """
    result = ValidationResult()
    spec = SECTION_SPECS.get(config.format or "")
    if spec is None:
        return result
    label = config.format.upper()

    from build_latex_report import BIBLIOGRAPHY_HEADINGS, fold_heading

    body = (
        config.body_path.read_text(encoding="utf-8", errors="ignore")
        if config.body_path.exists()
        else ""
    )
    body_heads = [
        fold_heading(match.group(2))
        for match in (BODY_HEADING_RE.match(line) for line in body.splitlines())
        if match
    ]
    skipped: set[str] = set()
    if config.format == "ape":
        # A teacher may drop a fixed section (``ape_omit_sections`` in report.yml).
        omitted = config.raw.get("ape_omit_sections") or []
        if not isinstance(omitted, list) or not all(isinstance(t, str) for t in omitted):
            result.errors.append("ape_omit_sections debe ser una lista de títulos de sección")
            omitted = []
        known = {fold_heading(title) for title, _ in spec}
        for title in omitted:
            if fold_heading(title) not in known:
                result.errors.append(f"ape_omit_sections: '{title}' no es una sección del formato APE")
        from report_config import APE_OMITTABLE_FIELDS

        omitted_fields = config.raw.get("ape_omit_fields") or []
        if not isinstance(omitted_fields, list):
            result.errors.append("ape_omit_fields debe ser una lista de campos de metadata")
            omitted_fields = []
        for field in omitted_fields:
            if field not in APE_OMITTABLE_FIELDS:
                result.errors.append(f"ape_omit_fields: '{field}' no es un campo omitible del formato APE")
        skipped = {fold_heading(title) for title in omitted}

    # (title, kind, folded titles that stand for it)
    sections = [
        (title, kind, BIBLIOGRAPHY_HEADINGS if kind == BIBLIOGRAPHY_SLOT else {fold_heading(title)})
        for title, kind in spec
        if fold_heading(title) not in skipped
    ]

    missing = [
        title for title, kind, norms in sections
        if kind == REQUIRED_SECTION and not norms & set(body_heads)
    ]
    if missing:
        result.errors.append(f"Faltan secciones del formato {label} en body.md: " + ", ".join(missing))

    positions = {norm: index for index, norm in enumerate(body_heads)}
    last_seen = -1
    for title, _kind, norms in sections:
        found = [positions[norm] for norm in norms if norm in positions]
        if not found:
            continue
        position = min(found)
        if position < last_seen:
            result.errors.append(
                f"La sección '{title}' está fuera del orden requerido por el "
                f"formato {label} en body.md"
            )
            break
        last_seen = position
    return result


def ape_structure_validation(config: ReportConfig) -> ValidationResult:
    """The APE slice of ``section_structure_validation`` (inert for any other format)."""
    if config.format != "ape":
        return ValidationResult()
    return section_structure_validation(config)


_INLINE_CODE = re.compile(r"(`+)(.+?)\1")
# Whitespace plus the listing wrap mark: pdftotext extracts the builder's
# ``postbreak`` ($\hookrightarrow$) as "↪→", usually on a line of its own.
_PDF_LAYOUT_NOISE = re.compile(r"[\s↪→]+")
# How far (in non-blank characters) past a listing's last matched text the rest
# of one of its lines may land: pdftotext can move an aligned comment column
# below the code lines it belongs to, but never into distant prose.
_LISTING_WINDOW = 400


def _markdown_code_fragments(body: str) -> tuple[list[list[str]], list[str]]:
    """The lines of every fenced code block, and every inline code span, in ``body``.

    Fences follow the builder's own rule, so a line counts as code exactly when
    the PDF renders it inside a listing.
    """
    from build_latex_report import CODE_FENCE_RE, is_closing_fence

    lines = body.splitlines()
    blocks: list[list[str]] = []
    prose: list[str] = []
    index = 0
    while index < len(lines):
        fence = CODE_FENCE_RE.match(lines[index].strip())
        if fence:
            marker = fence.group("marker")[0]
            closing = next(
                (j for j in range(index + 1, len(lines)) if is_closing_fence(lines[j], marker)),
                None,
            )
            if closing is not None:
                blocks.append(lines[index + 1 : closing])
                index = closing + 1
                continue
        prose.append(lines[index])
        index += 1
    spans = [match.group(2) for match in _INLINE_CODE.finditer("\n".join(prose))]
    return blocks, spans


def _pdf_text_without_code(pdf_text: str, blocks: list[list[str]], spans: list[str]) -> str:
    """``pdf_text`` with the code it renders cut out, everything else as extracted.

    Matching ignores whitespace and wrap marks, so a listing line that wraps,
    or carries a line number, still matches; the cut itself is made on the
    extracted text, so a ``\\`` ending one line is never joined with the next
    word. Listing lines are found in document order. pdftotext may extract an
    aligned trailing comment as a column of its own, so a line it does not
    hold whole is tried again as the pieces its runs of spaces separate, and
    once a listing is located the rest of it is looked for only within
    ``_LISTING_WINDOW``. Text the PDF does not hold there (a dropped or altered
    listing) removes nothing, so its commands stay counted instead of
    cancelling a defect in the prose.
    """
    kept = [index for index, char in enumerate(pdf_text) if not _PDF_LAYOUT_NOISE.match(char)]
    stream = "".join(pdf_text[index] for index in kept)
    cut = [False] * len(pdf_text)

    def take(text: str, start: int, end: int) -> int | None:
        """Cut the first ``text`` in ``stream[start:end]``; where the match ends."""
        nonlocal stream
        needle = _PDF_LAYOUT_NOISE.sub("", text)
        at = stream.find(needle, start, end) if needle else -1
        if at < 0:
            return None
        for position in range(at, at + len(needle)):
            cut[kept[position]] = True
        # NUL never occurs in extracted text, so a cut span cannot match again.
        stream = stream[:at] + "\0" * len(needle) + stream[at + len(needle):]
        return at + len(needle)

    cursor = 0
    for lines in blocks:
        located = False
        for line in lines:
            for pieces in ([line], re.split(r"\s{2,}", line.strip())):
                found = False
                for piece in pieces:
                    end = take(piece, cursor, cursor + _LISTING_WINDOW if located else len(stream))
                    if end is not None and not found:
                        cursor, located, found = end, True, True
                if found:
                    break
    for span in spans:
        take(span, 0, len(stream))

    # A separator keeps the text on both sides of a cut apart.
    return re.sub("\0+", "\n", "".join("\0" if cut[i] else char for i, char in enumerate(pdf_text)))


def _cover_value_pattern(value: object) -> re.Pattern[str] | None:
    """Whole-word, case-insensitive match of a cover value in flattened PDF text.

    Words may be split across lines with a hyphen (``pro- yecto`` once the page
    text is flattened), so a hyphen plus space is allowed between any two
    letters. The value never matches inside a longer word.
    """
    words = str(value or "").split()
    if not words:
        return None
    word_patterns = [r"(?:-\s)?".join(re.escape(char) for char in word) for word in words]
    return re.compile(r"(?<!\w)" + r"\s+".join(word_patterns) + r"(?!\w)", re.IGNORECASE)


def common_validation(config: ReportConfig) -> ValidationResult:
    result = ValidationResult()
    metadata_result = metadata_validation(config)
    result.errors.extend(metadata_result.errors)
    result.warnings.extend(metadata_result.warnings)

    if not config.body_path.exists() and config.backend in {"latex", "html"}:
        result.errors.append(f"No existe body.md: {config.body_path}")

    if config.output_format == "pdf" and not config.pdf_path.exists():
        result.errors.append(f"No existe PDF final esperado: {config.pdf_path}")

    outputs = config.folder / "outputs"
    local_outputs = outputs.resolve()
    global_outputs = GLOBAL_OUTPUTS.resolve()
    final_pdf = config.pdf_path.resolve()
    if config.output_format == "pdf" and config.pdf_path.exists():
        in_local_outputs = local_outputs in final_pdf.parents
        in_global_outputs = global_outputs in final_pdf.parents
        if not (in_local_outputs or in_global_outputs):
            expected_global_exists = False
            if config.publish_global:
                subject_slug = infer_subject_for_path(config.pdf_path, config.metadata)
                if subject_slug:
                    expected_global = GLOBAL_OUTPUTS / subject_slug / config.pdf_path.name
                    expected_global_exists = expected_global.exists()
            if not expected_global_exists:
                result.warnings.append("El PDF final no está dentro de outputs/")
        if targets_local_outputs(config):
            # Defence in depth: load_report_config already refuses a declared
            # path here, so reaching this branch means the PDF landed in the
            # forbidden folder some other way (an implicit default, a stale
            # copy, a builder writing outside its configuration).
            #
            # The condition is the shared predicate, not a second spelling of
            # it: this branch used to repeat the underscore exemption inline,
            # which is two places to keep in step for one rule.
            result.errors.append(LOCAL_OUTPUTS_ERROR)

    if outputs.exists():
        dirty = [p.name for p in outputs.iterdir() if p.is_file() and p.suffix.lower() not in {".pdf", ".docx"}]
        if dirty:
            result.warnings.append("outputs/ contiene intermedios; deberían ir a backups/ o build/: " + ", ".join(dirty[:8]))

    if (
        config.publish_global
        and config.output_format == "pdf"
        and config.pdf_path.exists()
        and not (
            config.route_is_known
            and config.pdf_path.resolve().parent
            == (GLOBAL_OUTPUTS / config.output_folder_slug).resolve()
        )
    ):
        subject_slug = infer_subject_for_path(config.pdf_path, config.metadata)
        if subject_slug:
            expected_global = GLOBAL_OUTPUTS / subject_slug / config.pdf_path.name
            if not expected_global.exists():
                result.warnings.append(
                    "No existe copia global filtrada por materia: "
                    + relative_label(expected_global, GLOBAL_OUTPUTS.parent)
                )
        else:
            result.warnings.append("No pude inferir la materia para publicar en outputs/<materia>/")

    if GLOBAL_OUTPUTS.exists():
        loose_items = [p.name for p in GLOBAL_OUTPUTS.iterdir() if p.is_file() and p.name != ".gitkeep"]
        loose_finals = [name for name in loose_items if Path(name).suffix.lower() in FINAL_EXTENSIONS]
        loose_intermediates = [name for name in loose_items if Path(name).suffix.lower() not in FINAL_EXTENSIONS]
        non_delivery = [
            str(p.relative_to(GLOBAL_OUTPUTS))
            for p in GLOBAL_OUTPUTS.rglob("*")
            if p.is_file() and p.name != ".gitkeep" and p.suffix.lower() not in FINAL_EXTENSIONS
        ]
        if loose_finals:
            result.warnings.append("outputs/ global tiene finales sueltos; deben ir en outputs/<materia>/: " + ", ".join(loose_finals[:8]))
        if loose_intermediates:
            result.warnings.append("outputs/ global tiene intermedios sueltos; deben ir a backups/: " + ", ".join(loose_intermediates[:8]))
        if non_delivery:
            result.warnings.append("outputs/ global contiene archivos que no son PDF/DOCX; deben ir a backups/: " + ", ".join(non_delivery[:8]))

    text = "\n".join(pdf_text_pages(config.pdf_path)) if config.pdf_path.exists() else ""
    banned = config.academic_value("conclusions", "banned_openers", default=["Se concluye", "En conclusión", "En conclusion"])
    found = [item for item in banned if item.lower() in text.lower()]
    if found:
        result.errors.append("Conclusión inicia/usa fórmulas prohibidas: " + ", ".join(found))

    if config.pdf_path.exists():
        pages = pdf_text_pages(config.pdf_path)
        blank_pages = [str(i + 1) for i, page in enumerate(pages) if i < len(pages) - 1 and len(page.strip()) < 20]
        if blank_pages:
            result.errors.append("Posibles páginas vacías accidentales: " + ", ".join(blank_pages))

        if config.cover_value("required", default=True) and len(pages) < 2:
            result.errors.append("La portada es obligatoria pero el PDF tiene menos de 2 páginas")

        # CRITICAL: detect LaTeX commands rendered as literal text in PDF
        full_text = "\n".join(pages)
        latex_escaped_patterns = [
            (r"\quad", "\\quad"),
            (r"\qquad", "\\qquad"),
            (r"\frac", "\\frac"),
            (r"\boxed", "\\boxed"),
            (r"\sqrt", "\\sqrt"),
            (r"\pi", "\\pi"),
            (r"\sin", "\\sin"),
            (r"\cos", "\\cos"),
            (r"\tan", "\\tan"),
            (r"\pm", "\\pm"),
            (r"\cdot", "\\cdot"),
            (r"\Longrightarrow", "\\Longrightarrow"),
            (r"\left", "\\left"),
            (r"\right", "\\right"),
            (r"\begin", "\\begin"),
            (r"\end", "\\end"),
            (r"\textbackslash", "\\textbackslash"),
        ]
        # Code listings and inline code may carry these commands on purpose
        # (#81: `title('cos(\pi/3)')` in an Octave plot); only what remains
        # once the PDF's rendered code is cut out is a rendering defect.
        prose_text = _pdf_text_without_code(
            full_text,
            *_markdown_code_fragments(
                config.body_path.read_text(encoding="utf-8", errors="ignore") if config.body_path.exists() else ""
            ),
        )
        found = []
        for display_name, search_pattern in latex_escaped_patterns:
            count = prose_text.count(search_pattern)
            if count > 0:
                found.append(f"{display_name} ({count} vez/veces)")
        if found:
            result.errors.append(
                "COMANDOS LATEX RENDERIZADOS COMO TEXTO LITERAL EN EL PDF: "
                + ", ".join(found) + ". "
                "Indica que latex_escape() en build_latex_report.py está "
                "escapando comandos que deberían estar dentro de $...$ o $$...$$."
            )

    return result


def asset_validation(_config: ReportConfig) -> ValidationResult:
    """Validate that system-level build assets (logo, background) exist.

    This checks the automation root's assets/ folder, not the report folder.
    Every LaTeX pipeline run needs these files; warn early if they drift.
    """
    result = ValidationResult()
    from build_latex_report import ASSETS_DIR, EXPECTED_ASSETS

    for filename, description in EXPECTED_ASSETS:
        path = ASSETS_DIR / filename
        if not path.exists():
            result.errors.append(
                f"Asset faltante: {description} ({filename}) — esperado en {ASSETS_DIR}"
            )
        elif path.stat().st_size < 1_000:
            result.errors.append(f"Asset sospechosamente pequeño: {path}")
    return result


def pdf_layout_validation(config: ReportConfig) -> ValidationResult:
    result = ValidationResult()
    if not config.pdf_path.exists():
        result.errors.append(f"No existe PDF para validar layout: {config.pdf_path}")
        return result

    info = pdfinfo(config.pdf_path)
    page_count = int(info.get("Pages", "0") or 0)
    if page_count < 1:
        result.errors.append("PDF sin páginas o pdfinfo no pudo leer conteo")

    page_size = info.get("Page size", "")
    numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", page_size)[:2]]
    if len(numbers) == 2:
        w, h = numbers
        is_a4 = abs(w - A4_WIDTH) < 3 and abs(h - A4_HEIGHT) < 3
        is_a4_landscape = abs(w - A4_HEIGHT) < 3 and abs(h - A4_WIDTH) < 3
        if not (is_a4 or (config.backend == "visual" and is_a4_landscape)):
            result.warnings.append(f"Tamaño de página no parece A4 estándar: {page_size}")

    try:
        images = run(["pdfimages", "-list", str(config.pdf_path)]).stdout.splitlines()
        image_rows = [line for line in images if re.match(r"^\s*\d+\s+\d+\s+image", line)]
        if config.cover_value("logo_required", default=True) and not image_rows:
            result.errors.append("PDF no parece tener imágenes embebidas; revisar logo UNL")
    except FileNotFoundError:
        result.warnings.append("pdfimages no disponible; no se validó logo/imágenes")

    pages = pdf_text_pages(config.pdf_path)
    body_page = config.cover_value("body_starts_on_page", default=2)
    body_page_index = body_page - 1  # 0-indexed
    # The cover/body boundary only exists when there IS a cover. A report that
    # declared `cover: {required: false}` starts its body on page 1, and the
    # markers below are academic Spanish — a business report opening on
    # "Resumen ejecutivo" can never match one, so the warning fired on every
    # build and taught the reader to skip warnings entirely.
    # Route-derived (#23): a non-academic route defaults to no cover, so the
    # academic cover/body boundary markers never apply to it.
    # The APE format has no cover: page 1 is the identification table, and
    # its unit name may well read "Introducción al ...".
    has_cover = bool(config.cover_value("required", default=True)) and config.format != "ape"
    if has_cover and len(pages) > body_page_index:
        first = pages[0].lower()
        body_content = pages[body_page_index].lower()
        body_markers = [
            "introducción",
            "introduccion",
            "tema",
            "antecedentes",
            "descripción",
            "descripcion",
            "desarrollo",
            "ejercicio",
            "ejercicios",
        ]
        body_marker_pattern = r"\b(" + "|".join(re.escape(marker) for marker in body_markers) + r")\b"
        cover_body_markers = [
            "introducción",
            "introduccion",
            "tema",
            "antecedentes",
            "descripción",
            "descripcion",
            "desarrollo",
        ]
        cover_body_marker_pattern = r"\b(" + "|".join(re.escape(marker) for marker in cover_body_markers) + r")\b"
        # The cover must print the title and subject, so a marker inside them
        # ("Desarrollo Basado en Plataformas") is not body text on page 1.
        cover_text = " ".join(first.split())
        for field in ("title", "subject"):
            pattern = _cover_value_pattern(config.metadata.get(field))
            if pattern is not None:
                cover_text = pattern.sub(" ", cover_text)
        if re.search(cover_body_marker_pattern, cover_text) and not config.raw.get("allow_body_on_cover", False):
            result.errors.append("La portada parece mezclada con el cuerpo; el cuerpo debe iniciar en página 2")
        # The marker vocabulary is academic Spanish (#23's numbering contract).
        # Non-academic routes render unnumbered, route-specific headings by
        # contract (routing.md, routes B-D), so requiring one of
        # these words there is a false positive, not a real signal.
        if (
            config.route == DEFAULT_ROUTE
            and not re.search(body_marker_pattern, body_content)
            and config.backend == "latex"
        ):
            result.warnings.append(f"No detecté inicio claro del cuerpo en página {body_page}; revisar portada/cuerpo")

    # Orphan headings are a pagination defect, not a cover concern: this loop
    # only ever needed `pages`. It used to sit inside the cover/body branch,
    # which meant a report without a cover — or one whose body legitimately
    # starts later — silently lost the check.
    # A table cell that closes a page is table content, never a heading.
    body_text = config.body_path.read_text(encoding="utf-8", errors="ignore") if config.body_path.exists() else ""
    table_cells = {
        " ".join(cell.split())
        for row in body_text.splitlines() if row.strip().startswith("|")
        for cell in row.strip().strip("|").split("|")
    }
    for idx, page in enumerate(pages[:-1], start=1):
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        if not lines:
            continue
        last = lines[-1]
        if " ".join(last.split()) in table_cells:
            continue
        looks_heading = (
            bool(re.match(r"^(\d+(?:\.\d+)*)?\s*[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ\s]{3,70}$", last))
            and not last.endswith((".", ":", ";", ","))
        )
        if looks_heading:
            # Reduce false positives from pdftotext fragments: a heading
            # should have a number prefix, span multiple words, or be at
            # least 8 characters (single short words like "Manten" are
            # typically split-word artifacts, not real headings).
            has_number = bool(re.match(r"^\d+(?:\.\d+)*", last))
            has_space = " " in last.strip()
            if not (has_number or has_space or len(last.strip()) >= 8):
                looks_heading = False
        if looks_heading:
            result.errors.append(f"Posible título huérfano al final de página {idx}: {last}")

    return result


def latex_log_validation(config: ReportConfig) -> ValidationResult:
    result = ValidationResult()
    log = config.log_path.read_text(encoding="utf-8", errors="ignore") if config.log_path.exists() else ""
    tex = config.tex_path.read_text(encoding="utf-8", errors="ignore") if config.tex_path.exists() else ""
    if not config.tex_path.exists():
        result.errors.append(f"No existe main.tex: {config.tex_path}")
        return result

    required_snippets = ["hyperref", "Needspace", "onehalfspacing", "parindent"]
    missing = [snippet for snippet in required_snippets if snippet not in tex]
    if missing:
        result.errors.append("LaTeX template sin reglas obligatorias: " + ", ".join(missing))

    if log:
        fatal_patterns = [
            r"! LaTeX Error",
            r"Undefined control sequence",
            r"Citation `[^']+' undefined",
            r"Reference `[^']+' undefined",
            r"There were undefined (?:references|citations)",
            r"Package biblatex Warning: Please \(re\)run Biber",
        ]
        found = [pattern for pattern in fatal_patterns if re.search(pattern, log)]
        if found:
            result.errors.append("Log LaTeX contiene errores/referencias sin resolver")
        overfull = overfull_validation(parse_overfull_boxes(log))
        result.errors.extend(overfull.errors)
        result.warnings.extend(overfull.warnings)
    else:
        result.warnings.append("No existe log LaTeX todavía; se validó solo el .tex")

    return result


BOLD_PSEUDO_HEADING_RE = re.compile(r"^\s*\*\*[^*]{4,}\*\*\s*$")


def bold_pseudo_heading_lines(body: str) -> list[tuple[int, str]]:
    """``(line number, line)`` for each bold-only line used as a heading.

    Shared by ``source_layout_validation`` and the pre-approval body check so
    both apply the same rule.
    """
    return [(n, line) for n, line in enumerate(body.splitlines(), start=1) if BOLD_PSEUDO_HEADING_RE.match(line)]


def source_layout_validation(config: ReportConfig) -> ValidationResult:
    result = ValidationResult()
    body = config.body_path.read_text(encoding="utf-8", errors="ignore") if config.body_path.exists() else ""
    bad_bold_titles = [line for _, line in bold_pseudo_heading_lines(body)]
    if bad_bold_titles:
        result.errors.append("Usar headings Markdown (#, ##) para títulos, no negrita manual: " + bad_bold_titles[0][:80])
    return result


def visual_validation(config: ReportConfig) -> ValidationResult:
    result = ValidationResult()
    figures_yml = config.folder / "figures" / "figures.yml"
    if not figures_yml.exists():
        figures_yml = config.folder / "figures.yml"
    if not figures_yml.exists():
        result.warnings.append("Trabajo visual sin figures.yml; no se pudo validar captions/fuentes de figuras")
        return result
    metadata_result = validate_visual_manifest(
        figures_yml.parent, figures_yml, report_folder=config.folder
    )
    result.errors.extend(metadata_result.errors)
    result.warnings.extend(metadata_result.warnings)
    for figure_path in figures_yml.parent.rglob("*"):
        if figure_path.is_file() and figure_path.suffix.lower() in {".svg", ".png", ".pdf"} and figure_path.stat().st_size < 4_000:
            result.warnings.append(f"Figura parece demasiado pequeña: {figure_path}")
    return result


def connector_final_size_validation(config: ReportConfig) -> ValidationResult:
    """Independent final-print-size connector audit for every diagram SVG a
    LaTeX report embeds (issue #10).

    ``tools/visual_builder.py validate`` is the isolated precheck; this is the
    mandatory, independent final-stage run the spec requires — neither
    substitutes for the other. Like every gate in this function, it never
    grants ``VISUAL_PASS`` itself (see academic-report-flow/SKILL.md: no
    script, validator, or auditor ever does); it only blocks the earlier
    gates ``VISUAL_PASS`` depends on. An unresolved figure or unaudited SVG
    is reported, never silently skipped.
    """
    result = ValidationResult()
    if config.backend != "latex" or not config.body_path.exists():
        return result

    from build_latex_report import (
        normalize_template_key,
        resolve_figure,
        resolve_template,
        sized_figure_references,
        template_key_for,
    )
    from connector_geometry import run_geometry_audit
    from connector_pdf_stage import audit_svg_at_final_size
    from visual_pdf_auditor import FAILURE as CONNECTOR_FAILURE

    build_dir = config.tex_path.parent
    markdown = config.body_path.read_text(encoding="utf-8")
    svg_figures: list[tuple[Path, dict[str, float]]] = []
    for reference, size in sized_figure_references(markdown):
        resolved = resolve_figure(reference, build_dir)
        if resolved is None:
            result.warnings.append(
                f"No se pudo resolver la figura '{reference}' para el gate de conectores en tamaño final; queda sin auditar"
            )
            continue
        candidate = resolved if resolved.suffix.lower() == ".svg" else resolved.with_suffix(".svg")
        if candidate.exists():
            svg_figures.append((candidate, size))
        else:
            result.warnings.append(
                f"No se encontró '{candidate.name}' junto a '{resolved.name}' para el gate de conectores en tamaño final; queda sin auditar"
            )
    if not svg_figures:
        return result

    try:
        template_path = resolve_template(normalize_template_key(template_key_for(config)))
        tex_source = template_path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        result.errors.append(f"No se pudo resolver la plantilla LaTeX para el gate de conectores en tamaño final: {exc}")
        return result

    for svg_path, size in svg_figures:
        # ANY geometry exception (malformed XML, corrupted path/point data)
        # becomes a reported finding here, through the same guard
        # visual_builder.py's isolated validate command uses (#43 T2) — the
        # two entry points can no longer diverge on which exceptions are
        # safe to catch.
        issues = run_geometry_audit(svg_path.name, lambda svg_path=svg_path, size=size: audit_svg_at_final_size(svg_path, tex_source, size))
        for issue in issues:
            if issue.level == CONNECTOR_FAILURE:
                result.errors.append(f"[tamaño final] {issue.tag}: {issue.detail} ({svg_path.name})")
    return result


def docx_validation(config: ReportConfig) -> ValidationResult:
    """Validate the DOCX artefact itself, not merely that a file exists.

    Severity follows the enforcement key documented at the top of
    ``templates/academic_format.yml``, so this validator does not invent a
    stricter contract than the format file declares:

    * lost or unreadable content, a degenerate table and a figure that never
      made it into the package are ERRORS — they are missing deliverable, not
      styling;
    * ``page.size`` is annotated ``[ENFORCED]``, so a document that is not the
      declared size is an ERROR;
    * margins, body font and body size are annotated ``[GUIDANCE]``/
      ``[TEST-GATED]`` ("set in the .tex template"), so a mismatch is a
      WARNING. A DOCX restyled by a task-specific script (restyle_docx_aa1.py)
      legitimately differs there and must not be failed for it.
    """
    result = ValidationResult()
    if not config.docx_path.exists():
        result.errors.append(f"No existe DOCX final esperado: {config.docx_path}")
        return result
    if config.docx_path.stat().st_size < 10_000:
        result.warnings.append("DOCX demasiado pequeño; revisar que no esté vacío")

    try:
        from docx import Document as DocxDocument
    except ImportError:
        result.warnings.append(
            "python-docx no está instalado; no pude validar el contenido del DOCX"
        )
        return result

    try:
        document = DocxDocument(str(config.docx_path))
    except Exception as exc:
        result.errors.append(
            f"No se pudo abrir el DOCX ({config.docx_path}): {exc}. "
            "El archivo está corrupto o no es un documento de Word."
        )
        return result

    filled = [p for p in document.paragraphs if p.text.strip()]
    if not filled and not document.tables:
        result.errors.append(
            f"El DOCX está sin contenido: {config.docx_path} no tiene párrafos "
            "con texto ni tablas"
        )
        return result

    if not any(p.style is not None and p.style.name.startswith("Heading") for p in document.paragraphs):
        result.warnings.append(
            "El DOCX no tiene títulos con estilo Heading; el documento no será navegable en Word"
        )

    section = document.sections[0]
    expected_size = str(config.academic_value("page", "size", default="A4")).strip().upper()
    width_cm = section.page_width / 360000
    height_cm = section.page_height / 360000
    if expected_size == "A4" and not (
        abs(width_cm - 21.0) < 0.2 and abs(height_cm - 29.7) < 0.2
    ):
        result.errors.append(
            f"El DOCX no está en A4: {width_cm:.2f} x {height_cm:.2f} cm "
            f"(esperado 21.00 x 29.70 cm)"
        )

    allowed_margins = config.academic_value("page", "margins", "allowed_cm", default=[2.5, 3.0])
    margins_cm = {
        "superior": section.top_margin / 360000,
        "inferior": section.bottom_margin / 360000,
        "izquierdo": section.left_margin / 360000,
        "derecho": section.right_margin / 360000,
    }
    off_contract = [
        f"{name} {value:.2f} cm"
        for name, value in margins_cm.items()
        if not any(abs(value - float(allowed)) < 0.1 for allowed in allowed_margins)
    ]
    if off_contract:
        result.warnings.append(
            "Márgenes del DOCX fuera de los permitidos "
            f"({', '.join(str(m) for m in allowed_margins)} cm): " + ", ".join(off_contract)
        )

    normal = document.styles["Normal"]
    preference = config.academic_value("body_text", "font_preference", default=[]) or []
    expected_font = str(preference[0]) if preference else "Times New Roman"
    if normal.font.name and normal.font.name != expected_font:
        result.warnings.append(
            f"Fuente base del DOCX: '{normal.font.name}'; el formato declara '{expected_font}'"
        )
    expected_pt = float(config.academic_value("body_text", "size_pt", default=12))
    if normal.font.size is not None and abs(normal.font.size.pt - expected_pt) > 0.1:
        result.warnings.append(
            f"Tamaño base del DOCX: {normal.font.size.pt} pt; el formato declara {expected_pt} pt"
        )

    for index, table in enumerate(document.tables, start=1):
        if not table.rows or not table.columns:
            result.errors.append(f"Tabla {index} del DOCX quedó sin filas o sin columnas")
            continue
        empty_rows = [
            position
            for position, row in enumerate(table.rows, start=1)
            if not any(cell.text.strip() for cell in row.cells)
        ]
        if empty_rows:
            result.errors.append(
                f"Tabla {index} del DOCX tiene filas totalmente vacías: "
                + ", ".join(str(position) for position in empty_rows)
            )

    if config.body_path.exists():
        body = config.body_path.read_text(encoding="utf-8", errors="ignore")
        local_figures = [
            reference
            for reference in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", body)
            if not reference.strip().startswith(("http://", "https://", "data:"))
        ]
        if local_figures and not document.inline_shapes:
            result.errors.append(
                "El body.md referencia imágenes pero el DOCX no tiene ninguna incrustada: "
                + ", ".join(local_figures[:5])
            )

    return result


def visual_pdf_validation(config: ReportConfig) -> ValidationResult:
    """Validate PDF visual quality using visual_pdf_auditor.py.
    
    Runs the heuristic page-image analysis (pdftoppm + PIL) on the final PDF.
    Requires poppler-utils (pdftoppm) and Pillow.
    Only runs when config.output_format == 'pdf' and the PDF exists.
    """
    result = ValidationResult()

    if config.output_format != "pdf":
        result.warnings.append("visual_pdf: saltado — formato no es PDF")
        return result

    pdf = config.pdf_path
    if not pdf.exists():
        result.errors.append(f"visual_pdf: no existe PDF para auditar: {pdf}")
        return result

    if not VISUAL_AUDITOR_AVAILABLE:
        result.warnings.append(
            "visual_pdf: visual_pdf_auditor no disponible; "
            "ejecutá manual: python tools/visual_pdf_auditor.py <pdf>"
        )
        return result

    try:
        audit_result = audit_pdf(pdf, default_output_dir(pdf))

        for finding in audit_result.findings:
            for issue in page_issues(finding, audit_result.total_pages):
                line = f"visual_pdf [Página {finding.page}]: {issue.tag}"
                if issue.detail:
                    line += f" ({issue.detail})"
                if issue.level == FAILURE:
                    result.errors.append(line)
                elif issue.level == WARNING:
                    result.warnings.append(line)
                # INFO stays out: it is context for a human reading the audit,
                # not something a build gate should speak about.

    except Exception as exc:
        result.warnings.append(f"visual_pdf: error ejecutando auditor: {exc}")

    return result


def table_style_receipts_validation(config: ReportConfig) -> tuple[list[SelectionReceipt], ValidationResult]:
    """Re-resolve every directed table's SelectionReceipt, read-only, from body.md.

    Issue #13 acceptance gap: the design's ``tools/validate_report.py``
    file-change entry ("Persist receipts and coordinate post-render
    evidence") was never implemented -- ``SelectionReceipt`` was computed
    correctly by ``build_latex_report.py``/``build_docx_report.py`` but
    discarded after rendering. Rather than thread a receipt collector
    through both renderers, this re-derives the identical receipt
    ``resolve_table_style`` is pure: same body.md + same report.yml/
    academic_format.yml always resolves the same style, teacher/institution
    override precedence included. A no-op (``[]``, no errors) for a report
    that never opted into ``table_styles: {enabled: true}`` -- every
    existing report's validation evidence stays byte-for-byte unchanged.
    ``tools/build_report.py`` (the HTML preview tool) has no ``ReportConfig``
    at all, so it is out of scope here by construction (see
    odd/tasks/contextual-table-styles.md).

    A catalog load failure (a malformed ``templates/table_styles.yml``)
    becomes a reported finding instead of aborting validation -- the same
    contract every other check in this module already honours (issue #52).
    """
    result = ValidationResult()
    if not config.table_styles_enabled or not config.body_path.exists():
        return [], result

    markdown = config.body_path.read_text(encoding="utf-8", errors="ignore")
    try:
        blocks = parse_table_blocks(markdown)
    except TableDirectiveError as exc:
        result.errors.append(f"Directiva de estilo de tabla inválida en body.md: {exc}")
        return [], result

    try:
        table_styles = TableStylesContext.from_config(config)
    except CatalogError as exc:
        result.errors.append(f"No se pudo cargar el catálogo de estilos de tabla: {exc}")
        return [], result

    receipts: list[SelectionReceipt] = []
    for block in blocks:
        if block.table_key is None or block.context is None:
            continue  # undirected -- build_latex_report/build_docx_report already block this
        request = table_styles.request_for(block.table_key, block.context)
        try:
            receipts.append(resolve_table_style(request, table_styles.catalog))
        except (OverrideRejectedError, UnsupportedContextError) as exc:
            result.errors.append(f"Estilo de tabla '{block.table_key}': {exc}")
    return receipts, result


def write_table_style_receipts(config: ReportConfig, receipts: list[SelectionReceipt]) -> None:
    """Persist every table's SelectionReceipt as path-free, byte-stable JSON evidence.

    Design: "Receipts beside quality evidence... JSON receipts for
    deterministic machine comparison and human-readable rationale without
    leaking paths." ``SelectionReceipt``/``TableContext`` carry no
    filesystem path by construction; sorted by ``table_key`` so the same
    body.md always produces identical bytes regardless of dict iteration
    order.

    Idempotent by design: called on every ``validate()`` run regardless of
    ``table_styles.enabled``, so the file on disk always reflects the
    current build. An empty ``receipts`` list (styles disabled, or no table
    carries a directive) removes a previously written file instead of
    leaving stale evidence behind (issue #52).
    """
    path = config.table_style_receipts_path
    if not receipts:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(receipts, key=lambda receipt: receipt.table_key)
    payload = {
        "catalog_version": ordered[0].catalog_version if ordered else None,
        "tables": [
            {
                "table_key": receipt.table_key,
                "style_id": receipt.style_id,
                "precedence_source": receipt.precedence_source,
                "rationale": receipt.rationale,
                "context": dataclasses.asdict(receipt.context),
            }
            for receipt in ordered
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_quality_report(config: ReportConfig, validation: ReportValidation) -> None:
    path = config.quality_report_path
    path.parent.mkdir(parents=True, exist_ok=True)
    status = "APROBADO" if not validation.errors else "FALLÓ"
    lines = [
        f"# Quality report — {config.folder.name}",
        "",
        "## Resultado",
        status,
        "",
        "## Validaciones ejecutadas",
    ]
    lines.extend(f"- {check}" for check in validation.checks)
    if validation.table_style_receipts:
        lines.extend(["", "## Estilos de tabla"])
        lines.extend(
            f"- {receipt.table_key}: {receipt.style_id} ({receipt.precedence_source}) — {receipt.rationale}"
            for receipt in sorted(validation.table_style_receipts, key=lambda receipt: receipt.table_key)
        )
    if validation.errors:
        lines.extend(["", "## Errores", *[f"- {error}" for error in validation.errors]])
    if validation.warnings:
        lines.extend(["", "## Advertencias", *[f"- {warning}" for warning in validation.warnings]])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate(config: ReportConfig) -> ReportValidation:
    validators = config.validators
    validation = ReportValidation()
    # These gates are policy, not report.yml preferences. ReportConfig rejects
    # attempts to disable them; keeping the dispatch unconditional prevents a
    # future alternate config implementation from silently bypassing them.
    validation.add("common", common_validation(config))
    if config.backend == "latex":
        validation.add("assets", asset_validation(config))
        validation.add("connector_final_size", connector_final_size_validation(config))
    if config.output_format == "pdf":
        validation.add("pdf_layout", pdf_layout_validation(config))
    if validators.get("ieee", True):
        validation.add("ieee", validate_ieee(config))
    if validators.get("latex", False):
        validation.add("source_layout", source_layout_validation(config))
    if validators.get("latex_log", False):
        validation.add("latex_log", latex_log_validation(config))
    if validators.get("visual", False):
        validation.add("visual", visual_validation(config))
    if validators.get("visual_pdf", False):
        validation.add("visual_pdf", visual_pdf_validation(config))
    if validators.get("docx", False):
        validation.add("docx", docx_validation(config))

    # A non-boolean `table_styles.enabled` (report.yml malformed by a typo,
    # e.g. `"yes"`) must never crash validation before the quality report is
    # written -- it becomes a reported finding, same as any other config
    # error in this function (issue #52).
    try:
        table_styles_enabled = config.table_styles_enabled
    except ValueError as exc:
        validation.errors.append(f"table_styles.enabled inválido: {exc}")
        table_styles_enabled = False

    receipts: list[SelectionReceipt] = []
    if table_styles_enabled:
        receipts, table_style_result = table_style_receipts_validation(config)
        validation.add("table_style_receipts", table_style_result)
    validation.table_style_receipts = receipts
    # Always idempotent: rewrites current evidence, or removes a stale file
    # left by a previous build that had styles enabled (issue #52).
    write_table_style_receipts(config, receipts)

    write_quality_report(config, validation)
    return validation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path, help="Carpeta del reporte con report.yml")
    args = parser.parse_args()
    config = load_report_config(args.folder)
    result = validate(config)
    if result.errors:
        raise SystemExit("VALIDATION FAILED:\n- " + "\n- ".join(result.errors) + f"\n\nReporte: {config.quality_report_path}")
    if result.warnings:
        print("VALIDATION PASSED WITH WARNINGS:\n- " + "\n- ".join(result.warnings))
    else:
        print("VALIDATION PASSED")
    print(f"Reporte: {config.quality_report_path}")


if __name__ == "__main__":
    main()
