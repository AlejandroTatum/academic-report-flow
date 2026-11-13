#!/usr/bin/env python3
"""Editorial technical figures: style tokens, two layouts and a print-size check (#63).

The house style for report figures (``skills/academic-visual-builder/references/
editorial-style.md``): one ink plus one accent, a serif title that matches the
report body, sans labels in three weights, hairline nodes with a category bar,
straight connectors with open tips, and no pastel rainbow, rounded "pill" cards
or chip legends.

    editorial_svg.py render <spec.yml> --out <figure.svg>
    editorial_svg.py check <figure.svg> [--print-width-cm 13.5] [--min-pt 5.5]

``render`` builds an ``actor_map`` (users above a system panel with a numbered
process timeline, external actors below, related services at the foot) or a
``concept_map`` (a central concept fanning out through labelled links to 2-4
branch concepts with their sub-concepts). At the default 13.5 cm print width a
figure wider than about 860 SVG units prints its 12.5-unit labels below 5.5 pt. ``check`` converts every ``font-size`` to
printed points for the figure's printed width and warns below the minimum
(``warning: print size check: FAIL ...`` on stderr, exit 0; unreadable input exits 2).
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

SANS = "Noto Sans, sans-serif"
SERIF = "Noto Serif, serif"
INK = "#1D2433"
MUTED = "#5B6472"
HAIRLINE = "#C9CED6"
ACCENT = "#1F5F8B"
PANEL = "#F3F6F9"
LINE = "#4B5563"
CATEGORIES = {
    "principal": ("USUARIO PRINCIPAL", ACCENT),
    "responsable": ("RESPONSABLE", INK),
    "secundario": ("USUARIO SECUNDARIO", "#6F8FA8"),
    "externo": ("ACTOR EXTERNO", "#A39A8C"),
    "sistema": ("SISTEMA RELACIONADO", "#B4BAC3"),
}
# A figure printed at 0.86 of the UNL text width is about 13.5 cm wide.
DEFAULT_PRINT_WIDTH_CM = 13.5
DEFAULT_MIN_PT = 5.5
SIZE_META, SIZE_BODY, SIZE_NAME = 12.5, 14, 16


class SpecError(ValueError):
    """The figure spec is missing a field or breaks a layout limit."""


def text(x, y, value, size=SIZE_BODY, weight=400, fill=INK, anchor="middle", family=SANS, style="normal", spacing=0):
    letter = f' letter-spacing="{spacing}"' if spacing else ""
    return (f'<text x="{x:g}" y="{y:g}" font-family="{family}" font-size="{size:g}" font-weight="{weight}" '
            f'font-style="{style}" fill="{fill}" text-anchor="{anchor}"{letter}>{escape(str(value))}</text>')


def node(x, y, w, h, name, lines=(), label="", bar=ACCENT, dashed=False):
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    left = x + 20
    parts = [f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="2" fill="#FFFFFF" stroke="{HAIRLINE}" stroke-width="1.2"{dash}/>',
             f'<rect x="{x:g}" y="{y:g}" width="5" height="{h:g}" fill="{bar}"/>']
    top = y + 24
    if label:
        parts.append(text(left, top, label, SIZE_META, 600, MUTED, "start", spacing=1.0))
        top += 24
    parts.append(text(left, top, name, SIZE_NAME, 600, INK, "start"))
    for index, line in enumerate(l for l in lines if l):
        parts.append(text(left, top + 24 + index * 19, line, SIZE_BODY, 300, INK, "start"))
    return "\n".join(parts)


def connector(x1, y1, x2, y2, direction="out", dashed=False):
    """``out`` points at (x2, y2); ``both`` adds a tip at the start."""
    start = ' marker-start="url(#tip-start)"' if direction == "both" else ""
    dash = ' stroke-dasharray="6 5"' if dashed else ""
    return (f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" stroke="{LINE}" stroke-width="1.4"'
            f'{dash}{start} marker-end="url(#tip-end)"/>')


def _open(width, height):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:g}" height="{height:g}" viewBox="0 0 {width:g} {height:g}">',
            '<defs>',
            '<marker id="tip-end" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto">'
            f'<path d="M1,1 L9,5 L1,9" fill="none" stroke="{LINE}" stroke-width="1.6"/></marker>',
            '<marker id="tip-start" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="9" markerHeight="9" orient="auto">'
            f'<path d="M9,1 L1,5 L9,9" fill="none" stroke="{LINE}" stroke-width="1.6"/></marker>',
            '</defs>',
            f'<rect width="{width:g}" height="{height:g}" fill="#FFFFFF"/>']


def _require(spec: dict, key: str):
    if key not in spec or spec[key] in (None, "", []):
        raise SpecError(f"spec needs '{key}'")
    return spec[key]


def _lines(item: dict) -> list[str]:
    return [str(line) for line in item.get("lines") or []][:2]


def actor_map(spec: dict) -> str:
    """Three users above a system panel, three actors below, up to two services at the foot."""
    top, bottom = _require(spec, "top"), _require(spec, "bottom")
    steps = _require(spec, "steps")
    if len(top) != 3 or len(bottom) != 3:
        raise SpecError("actor_map needs exactly 3 'top' and 3 'bottom' actors")
    if not 2 <= len(steps) <= 6:
        raise SpecError("actor_map needs 2 to 6 'steps'")
    services = spec.get("services") or []
    if len(services) > 2:
        raise SpecError("actor_map takes at most 2 'services'")
    for actor in [*top, *bottom]:
        if actor.get("category", "") not in CATEGORIES:
            raise SpecError(f"unknown category for {actor.get('name')!r}; use one of {sorted(CATEGORIES)}")

    width, box_w, box_h = 840, 230, 104
    columns = (15, 305, 595)
    top_y, panel_y0, panel_y1, bottom_y, services_y = 30, 196, 432, 498, 676
    height = services_y + (110 if services else -60)
    parts = _open(width, height)

    cx = width / 2
    parts.append(f'<rect x="15" y="{panel_y0}" width="{width - 30}" height="{panel_y1 - panel_y0}" rx="2" '
                 f'fill="{PANEL}" stroke="{ACCENT}" stroke-width="1.6"/>')
    parts.append(text(cx, panel_y0 + 40, _require(spec, "title"), 22, 600, INK, family=SERIF))
    if spec.get("scope"):
        parts.append(text(cx, panel_y0 + 64, str(spec["scope"]).upper(), 13, 600, ACCENT, spacing=1.4))
    first_x, last_x, line_y = 105, width - 105, panel_y0 + 112
    gap = (last_x - first_x) / (len(steps) - 1)
    parts.append(f'<line x1="{first_x}" y1="{line_y}" x2="{last_x}" y2="{line_y}" stroke="{ACCENT}" stroke-width="2"/>')
    for index, step in enumerate(steps):
        first, second = (list(step) + [""])[:2] if isinstance(step, (list, tuple)) else (str(step), "")
        x = first_x + index * gap
        parts.append(f'<circle cx="{x:g}" cy="{line_y}" r="15" fill="{ACCENT}"/>')
        parts.append(text(x, line_y + 5, index + 1, SIZE_BODY, 700, "#FFFFFF"))
        parts.append(text(x, line_y + 40, first, SIZE_BODY, 600, INK))
        if second:
            parts.append(text(x, line_y + 58, second, SIZE_BODY, 400, INK))
    if spec.get("note"):
        parts.append(text(cx, panel_y1 - 22, spec["note"], SIZE_BODY, 400, MUTED, family=SERIF, style="italic"))

    for row, row_y, upper in ((top, top_y, True), (bottom, bottom_y, False)):
        for actor, x in zip(row, columns):
            label, bar = CATEGORIES[actor["category"]]
            parts.append(node(x, row_y, box_w, box_h, _require(actor, "name"), _lines(actor), label, bar))
            link, mid = actor.get("link", "both"), x + box_w / 2
            toward_system = (mid, row_y + box_h, mid, panel_y0) if upper else (mid, row_y, mid, panel_y1)
            if link == "from_system":
                x1, y1, x2, y2 = toward_system
                parts.append(connector(x2, y2, x1, y1, "out"))
            else:
                parts.append(connector(*toward_system, "both" if link == "both" else "out"))
        if (spec.get("designates") or {}).get("top" if upper else "bottom"):
            gap_x0, gap_x1, mid_y = columns[1] + box_w, columns[2], row_y + box_h / 2
            parts.append(connector(gap_x1, mid_y, gap_x0, mid_y, "out"))
            parts.append(text((gap_x0 + gap_x1) / 2, mid_y + 20, spec.get("designates_label", "designa"), 13.5, 400, MUTED, style="italic"))

    lines_x = (262, 290)
    slots = ((15, 255), (280, 245))
    any_dashed = False
    for service, line_x, (x, w) in zip(services, lines_x, slots):
        dashed = bool(service.get("out_of_scope"))
        any_dashed |= dashed
        label, bar = CATEGORIES["sistema"]
        parts.append(node(x, services_y, w, 80, _require(service, "name"), _lines(service)[:1], label, bar, dashed))
        if service.get("link", "to_system") == "to_system":
            parts.append(connector(line_x, services_y, line_x, panel_y1, "out", dashed))
        else:
            parts.append(connector(line_x, panel_y1, line_x, services_y, "out", dashed))
    if any_dashed:
        key_x, key_y = 590, services_y + 28
        parts.append(f'<line x1="{key_x}" y1="{key_y}" x2="{key_x + 34}" y2="{key_y}" stroke="{LINE}" stroke-width="1.4" stroke-dasharray="6 5"/>')
        parts.append(text(key_x + 44, key_y + 5, spec.get("out_of_scope_label", "fuera del alcance"), 13.5, 400, MUTED, "start", style="italic"))
        parts.append(f'<line x1="{key_x}" y1="{key_y + 26}" x2="{key_x + 34}" y2="{key_y + 26}" stroke="{LINE}" stroke-width="1.4"/>')
        parts.append(text(key_x + 44, key_y + 31, spec.get("in_scope_label", "dentro del alcance"), 13.5, 400, MUTED, "start", style="italic"))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def concept_map(spec: dict) -> str:
    """A central concept fanning out through labelled links to 2-4 branch concepts."""
    center = _require(spec, "center")
    branches = _require(spec, "branches")
    if not 2 <= len(branches) <= 4:
        raise SpecError("concept_map needs 2 to 4 'branches' (split a larger map: wider figures print below the minimum size)")
    col_w, gap = 195, 20
    width = len(branches) * col_w + (len(branches) - 1) * gap + 20
    width = max(width, 560)
    left0 = (width - (len(branches) * col_w + (len(branches) - 1) * gap)) / 2
    center_w, center_h, center_y = 380, 84, 20
    branch_y = 230
    items_max = max(len(branch.get("items") or []) for branch in branches)
    if items_max > 5:
        raise SpecError("a branch takes at most 5 'items'")
    branch_h = 66 + 22 * items_max
    height = branch_y + branch_h + 30
    parts = _open(width, height)

    cx = width / 2
    parts.append(f'<rect x="{cx - center_w / 2:g}" y="{center_y}" width="{center_w}" height="{center_h}" rx="2" '
                 f'fill="{PANEL}" stroke="{ACCENT}" stroke-width="1.6"/>')
    parts.append(text(cx, center_y + 40, _require(center, "title"), 21, 600, INK, family=SERIF))
    if center.get("subtitle"):
        parts.append(text(cx, center_y + 64, str(center["subtitle"]).upper(), 12.5, 600, ACCENT, spacing=1.2))

    span = center_w - 60
    for index, branch in enumerate(branches):
        x = left0 + index * (col_w + gap)
        start_x = cx - span / 2 + (span * index / (len(branches) - 1))
        end_x = x + col_w / 2
        parts.append(connector(start_x, center_y + center_h, end_x, branch_y, "out"))
        label = _require(branch, "link")
        label_y = branch_y - 30
        t = (label_y - (center_y + center_h)) / (branch_y - (center_y + center_h))
        line_x = start_x + (end_x - start_x) * t
        right_side = end_x >= start_x
        parts.append(text(line_x + (10 if right_side else -10), label_y + 4, label, 13.5, 400, MUTED,
                          "start" if right_side else "end", style="italic"))
        parts.append(f'<rect x="{x:g}" y="{branch_y}" width="{col_w}" height="{branch_h}" rx="2" fill="#FFFFFF" '
                     f'stroke="{HAIRLINE}" stroke-width="1.2"/>')
        parts.append(f'<rect x="{x:g}" y="{branch_y}" width="{col_w}" height="4" fill="{ACCENT}"/>')
        parts.append(text(x + 18, branch_y + 34, _require(branch, "name"), SIZE_NAME, 600, INK, "start"))
        for row, item in enumerate(branch.get("items") or []):
            y = branch_y + 64 + row * 22
            parts.append(f'<rect x="{x + 18:g}" y="{y - 9}" width="6" height="6" fill="{ACCENT}"/>')
            parts.append(text(x + 32, y, item, SIZE_BODY, 300, INK, "start"))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


LAYOUTS = {"actor_map": actor_map, "concept_map": concept_map}


def render(spec: dict) -> str:
    kind = spec.get("kind")
    if kind not in LAYOUTS:
        raise SpecError(f"unknown kind {kind!r}; use one of {sorted(LAYOUTS)}")
    return LAYOUTS[kind](spec)


def printed_sizes(svg: str, print_width_cm: float = DEFAULT_PRINT_WIDTH_CM) -> list[tuple[float, str]]:
    """Every text's printed size in points, with its text, for a figure printed ``print_width_cm`` wide."""
    root = ET.fromstring(svg)
    view = root.get("viewBox")
    width = float(view.split()[2]) if view else float(re.sub(r"[^0-9.]", "", root.get("width", "0")) or 0)
    if width <= 0:
        raise SpecError("SVG has no usable width or viewBox")
    scale = print_width_cm / 2.54 * 72 / width
    sizes = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "text" and element.get("font-size"):
            sizes.append((float(element.get("font-size")) * scale, "".join(element.itertext())))
    return sizes


def check(svg: str, print_width_cm: float = DEFAULT_PRINT_WIDTH_CM, min_pt: float = DEFAULT_MIN_PT) -> list[str]:
    return [f"{size:.1f} pt < {min_pt} pt: {label!r}" for size, label in printed_sizes(svg, print_width_cm) if size < min_pt]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Editorial technical figures: render a spec or check print sizes.")
    sub = parser.add_subparsers(dest="command", required=True)
    render_cmd = sub.add_parser("render", help="render an actor_map or concept_map spec to SVG")
    render_cmd.add_argument("spec", type=Path)
    render_cmd.add_argument("--out", type=Path, required=True)
    check_cmd = sub.add_parser("check", help="warn when any text prints below the minimum size")
    check_cmd.add_argument("svg", type=Path)
    check_cmd.add_argument("--print-width-cm", type=float, default=DEFAULT_PRINT_WIDTH_CM)
    check_cmd.add_argument("--min-pt", type=float, default=DEFAULT_MIN_PT)
    args = parser.parse_args(argv)
    try:
        if args.command == "render":
            spec = yaml.safe_load(args.spec.read_text(encoding="utf-8")) or {}
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(render(spec), encoding="utf-8")
            print(f"rendered {args.out}")
            return 0
        problems = check(args.svg.read_text(encoding="utf-8"), args.print_width_cm, args.min_pt)
    except (OSError, SpecError, yaml.YAMLError, ET.ParseError) as error:
        print(f"editorial_svg: {error}", file=sys.stderr)
        return 2
    for problem in problems:
        print(problem)
    summary = f"({args.print_width_cm} cm wide, minimum {args.min_pt} pt)"
    if problems:
        # warn-only-gates S2: undersized text is a quality finding, not a block.
        print(f"warning: print size check: FAIL {summary}; enlarge the listed text. The flow continues.",
              file=sys.stderr)
    else:
        print(f"print size check: PASS {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
