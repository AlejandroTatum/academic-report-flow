#!/usr/bin/env python3
"""Final-size connector audit (issue #10, slice 3).

Re-runs the ``connector_geometry`` checks at the scale a diagram is actually
printed at, not just its isolated SVG. Obstruction, crossing and direction are
scale-invariant by construction (a uniform scale never changes topology), so
this stage re-runs them unchanged — independent enforcement, not a precheck
substitute. Clearance is the one rule final print size can change the verdict
of: it is measured here against a fixed physical minimum in PDF points
(``MIN_CLEARANCE_PRINT_PT``), not simply the 0.80 SVG-unit threshold scaled by
the same factor. A diagram whose source geometry keeps a comfortable 0.80-unit
gap can still fail here once that gap is shrunk far enough for print.

Scope note (investigated, not invented): this pipeline records no per-figure
placement receipt anywhere — no final page number, no exact PDF box, no PDF
hash. LaTeX's own float placement decides page and position at compile time,
and there is no cheap, stdlib-only way to recover them after the fact (poppler
gives page/size/embedded-image counts via ``pdfimages``/``pdfinfo``, never a
per-image bounding box). What IS derivable from data the pipeline already has
is the print SCALE: ``build_latex_report.py`` sizes every figure with a
closed-form rule (``FIGURE_WIDTH_FRACTION``/``FIGURE_MAX_HEIGHT_FRACTION``,
``keepaspectratio``) against the active template's own
``\\usepackage[...]{geometry}`` margins. This module recomputes that same rule
— importing the constants rather than restating them, so the two can never
drift — to get the uniform SVG-unit-to-PDF-point scale, and audits connector
geometry at that scale. Page-level and position-level placement receipts stay
out of scope; ``validate_report.py`` reports that limitation explicitly rather
than inventing a receipt this pipeline cannot actually produce.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from build_latex_report import FIGURE_MAX_HEIGHT_FRACTION, FIGURE_WIDTH_FRACTION
from connector_geometry import (
    CONNECTOR_CLEARANCE,
    CONNECTOR_DIRECTION_NO_SOURCE,
    Diagram,
    crossing_issues,
    direction_issues,
    load_link_directions,
    obstruction_issues,
    pairwise_clearances,
    parse_svg,
)
from visual_pdf_auditor import FAILURE, INFO, PageIssue

# PDF points per unit, PostScript-point convention (72pt/inch) — the same one
# validate_report.py's A4_WIDTH/A4_HEIGHT already assume, matching what
# pdfinfo/the compiled PDF's MediaBox report.
PT_PER_CM = 72.0 / 2.54
PT_PER_MM = PT_PER_CM / 10.0
PT_PER_IN = 72.0
A4_WIDTH_PT = 595.28
A4_HEIGHT_PT = 841.89

# Fixed physical minimum separation at final print size: roughly the width of
# a printed connector stroke at typical academic-report scale. Below this, two
# lines — or a line and a label — visually merge regardless of their SVG-space
# distance, which is the defect issue #10's second occurrence actually
# reported (labels unreadable at final rendered size).
MIN_CLEARANCE_PRINT_PT = 2.0

_UNIT_RE = re.compile(r"(-?[\d.]+)\s*(cm|mm|in|pt)")
_GEOMETRY_RE = re.compile(r"\\usepackage\[([^\]]*)\]\{geometry\}")
_VIEWBOX_RE = re.compile(r'viewBox="[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)"')


def _to_pt(value: str) -> float:
    match = _UNIT_RE.match(value.strip())
    if not match:
        raise ValueError(f"unrecognized geometry length: {value!r}")
    number, unit = float(match.group(1)), match.group(2)
    return {"cm": PT_PER_CM, "mm": PT_PER_MM, "in": PT_PER_IN, "pt": 1.0}[unit] * number


@dataclass(frozen=True)
class TemplateGeometry:
    text_width_pt: float
    text_height_pt: float


def parse_template_geometry(tex_source: str) -> TemplateGeometry:
    """Derive \\textwidth/\\textheight from the template's own geometry options.

    Supports the two forms the checked-in templates use: a uniform ``margin=``
    and explicit ``left=``/``right=``/``top=``/``bottom=``. Every template in
    this repo declares ``a4paper``; a different paper size is unsupported and
    raises rather than silently assuming A4.
    """
    match = _GEOMETRY_RE.search(tex_source)
    if not match:
        raise ValueError("template declares no \\usepackage[...]{geometry}")
    options = dict(
        (key.strip(), value.strip())
        for key, value in (opt.split("=", 1) for opt in match.group(1).split(",") if "=" in opt)
    )
    if "a4paper" not in match.group(1):
        raise ValueError(f"unsupported paper size in geometry options: {match.group(1)!r} (only a4paper is known)")
    if "margin" in options:
        left = right = top = bottom = _to_pt(options["margin"])
    else:
        missing = [key for key in ("left", "right", "top", "bottom") if key not in options]
        if missing:
            raise ValueError(f"geometry options carry no margin= and are missing {missing}: {options}")
        left, right = _to_pt(options["left"]), _to_pt(options["right"])
        top, bottom = _to_pt(options["top"]), _to_pt(options["bottom"])
    return TemplateGeometry(
        text_width_pt=A4_WIDTH_PT - left - right,
        text_height_pt=A4_HEIGHT_PT - top - bottom,
    )


def final_print_scale(
    source_width: float, source_height: float, geometry: TemplateGeometry, size: dict[str, float] | None = None
) -> float:
    """Uniform SVG-unit -> PDF-point scale, replaying ``figure_includegraphics_options``.

    Width-bound by default (``FIGURE_WIDTH_FRACTION`` of ``\\textwidth``);
    height-capped instead when that width would exceed
    ``FIGURE_MAX_HEIGHT_FRACTION`` of ``\\textheight`` — exactly how
    ``keepaspectratio`` resolves it in the compiled PDF. ``size`` is the
    figure's own ``{width=NN%}``/``{height=NN%}`` override (#103).
    """
    size = size or {}
    if source_width <= 0 or source_height <= 0:
        raise ValueError(f"non-positive source dimensions: {source_width}x{source_height}")
    width_pt = geometry.text_width_pt * size.get("width", FIGURE_WIDTH_FRACTION)
    scale = width_pt / source_width
    max_height_pt = geometry.text_height_pt * size.get("height", FIGURE_MAX_HEIGHT_FRACTION)
    if source_height * scale > max_height_pt:
        scale = max_height_pt / source_height
    return scale


def _final_clearance_issues(diagram: Diagram, obstructed_pairs: set[tuple[str, str]], scale: float) -> list[PageIssue]:
    issues: list[PageIssue] = []
    for edge_id, kind, other_id, dist_svg in pairwise_clearances(diagram, obstructed_pairs):
        dist_pt = dist_svg * scale
        if dist_pt < MIN_CLEARANCE_PRINT_PT:
            issues.append(
                PageIssue(
                    FAILURE, CONNECTOR_CLEARANCE,
                    f"edge '{edge_id}' is {dist_pt:.2f}pt ({dist_svg:.3f} SVG units x {scale:.4f}) from "
                    f"{kind} '{other_id}' at final print size (minimum {MIN_CLEARANCE_PRINT_PT}pt)",
                )
            )
    return issues


def audit_final_size(
    diagram: Diagram, scale: float, link_directions: dict[tuple[str, str], list[bool]] | None = None
) -> list[PageIssue]:
    """Re-run the connector audit at final print scale.

    *link_directions* carries the same #43 T1 declared-direction map
    ``audit_connector_geometry`` derives from the diagram's ``.mmd``
    source; ``None`` keeps the pre-#43 strict direction/marker rule, exactly
    as the isolated stage does when no source is found.
    """
    obstruction, obstructed_pairs = obstruction_issues(diagram)
    return (
        list(diagram.parse_issues)
        + obstruction
        + crossing_issues(diagram)
        + _final_clearance_issues(diagram, obstructed_pairs, scale)
        + direction_issues(diagram, link_directions)
    )


def _viewbox_size(text: str) -> tuple[float, float]:
    match = _VIEWBOX_RE.search(text)
    if not match:
        raise ValueError("SVG carries no viewBox; cannot derive its final print scale")
    return float(match.group(1)), float(match.group(2))


def audit_svg_at_final_size(
    svg_path: Path, tex_source: str, size: dict[str, float] | None = None
) -> list[PageIssue]:
    """Parse *svg_path* and audit it at the print scale *tex_source*'s
    template geometry implies, from the SVG's own ``viewBox`` dimensions."""
    text = svg_path.read_text(encoding="utf-8")
    diagram = parse_svg(text)
    width, height = _viewbox_size(text)
    geometry = parse_template_geometry(tex_source)
    scale = final_print_scale(width, height, geometry, size)
    link_directions = load_link_directions(svg_path)
    issues = audit_final_size(diagram, scale, link_directions)
    if link_directions is None:
        issues.append(
            PageIssue(
                INFO, CONNECTOR_DIRECTION_NO_SOURCE,
                f"'{svg_path.name}': no '.mmd' source found (sibling or mirrored visuals/specs tree); direction/marker check ran in strict mode",
            )
        )
    return issues
