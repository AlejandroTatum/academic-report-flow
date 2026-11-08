#!/usr/bin/env python3
"""Print the single approval packet for a report folder (verify-concise-drafts T8, S2).

One compact Markdown message holds what the approver needs: clickable links to
the plain draft PDF preview, ``body.md`` and the latest DOCX draft, the verify result,
one row per criterion (cumple/falta, found/total), the missing items, the
deletion candidates and the findings, then the rubric trace (weight, covering
sections, checks and requirements per criterion). The per-requirement evidence matrix is
for agents: it stays in ``content-check.yml`` and is linked, never pasted (#64). It is read-only: it never runs the verifier, builds or approves.
A stale or absent verification shows no matrix, so an old verdict is never
presented as current.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import accepted_gaps
import content_check
import pdf_viewer
import rubric_plan
import rubric_trace
import yaml
from approval_marker import BODY_NAME, draft_preview_is_fresh, draft_preview_path
from draft_docx import DRAFT_DIR

_DOCX_VERSION = re.compile(r"-borrador-v(\d+)\.docx$")


def preview_pdf(folder: Path) -> Path:
    """The plain temporary draft (``draft_pdf.py``), never the course-template PDF."""
    return draft_preview_path(folder)


def _link(path: Path) -> str:
    return f"[{path.name}]({path.resolve().as_uri()})"


def _latest_docx(folder: Path) -> Path | None:
    drafts = [(int(m.group(1)), p) for p in (folder / DRAFT_DIR).glob("*.docx")
              if (m := _DOCX_VERSION.search(p.name))]
    return max(drafts)[1] if drafts else None


def _cell(value: object) -> str:
    return " ".join(str(value or "").split()).replace("|", "\\|")


def _files_section(folder: Path) -> list[str]:
    pdf, body = preview_pdf(folder), folder / BODY_NAME
    rebuild = "draft_pdf.py"
    if not pdf.is_file():
        pdf_line = f"- Draft PDF: missing: build the draft with {rebuild}"
    elif not draft_preview_is_fresh(folder):
        pdf_line = f"- Draft PDF: {_link(pdf)} STALE: rebuild the draft with {rebuild}"
    else:
        pdf_line = f"- Draft PDF: {_link(pdf)}"
    lines = [pdf_line, f"- {BODY_NAME}: {_link(body)}"]
    docx = _latest_docx(folder)
    if docx is not None:
        lines.append(f"- DOCX draft: {_link(docx)}")
    return lines


def _listing(title: str, items: list[str]) -> list[str]:
    return ["", f"### {title} ({len(items)})", *([f"- {item}" for item in items] or ["- none"])]


def _verify_section(folder: Path) -> list[str]:
    state = content_check.content_check_state(folder)
    if state == "absent":
        return ["## Verify: absent: run the verifier first (content_check.py --verify-brief)"]
    if state == "stale":
        return ["## Verify: stale: re-run the verifier (content_check.py --verify-brief --since verification.yml)"]
    if state not in ("pass", "fail"):
        return [f"## Verify: {state}: content-check.yml cannot be read; re-run the verifier"]
    marker_path = folder / content_check.CONTENT_CHECK_NAME
    marker = yaml.safe_load(marker_path.read_text(encoding="utf-8")) or {}
    requirements = [r for r in marker.get("requirements") or [] if isinstance(r, dict)]
    counts: dict[str, list[int]] = {}
    for r in requirements:
        found_total = counts.setdefault(_cell(r.get("criterion")), [0, 0])
        found_total[0] += r.get("status") == "found"
        found_total[1] += 1
    found = sum(f for f, _ in counts.values())
    lines = [f"## Verify: {state} ({found}/{len(requirements)} requirements found)", "",
             "| Criterion | Status | Found |", "|---|---|---|"]
    lines += [f"| {criterion} | {'cumple' if f == t else 'falta'} | {f}/{t} |" for criterion, (f, t) in counts.items()]
    lines += ["", f"Full requirement matrix (for agents): {_link(marker_path)}"]
    missing = [f"{r.get('criterion')}: {r.get('requirement')}" for r in requirements
               if r.get("status") not in ("found", "partial")]
    partial = [f"{r.get('criterion')}: {r.get('requirement')} (gap: {r.get('gap')})" for r in requirements
               if r.get("status") == "partial"]
    lines += _listing("Missing", missing)
    lines += _listing("Partial", partial) if partial else []
    # The table above stays honest (a partial criterion is `falta`); the human's
    # acceptance is listed apart, with its reason and who gave it.
    accepted = [f"{g['criterion']}: {g['requirement']} (gap: {g['gap']}; reason: {' '.join(g['reason'].split())}; "
                f"accepted by {' '.join(g['accepted_by'].split())})" for g in accepted_gaps.applied_gaps(folder, requirements)]
    lines += _listing("Accepted gaps (human-accepted partial requirements; the criteria above stay falta)",
                      accepted) if accepted else []
    lines += _listing("Deletion candidates", [str(p) for p in marker.get("unmapped_paragraphs") or []])
    lines += _listing("Findings", [str(f) for f in marker.get("findings") or []])
    return lines


def _rubric_section(folder: Path) -> list[str]:
    """Weight and trace per criterion (skill-rubric-improvements S1); nothing without a valid rubric."""
    if rubric_plan.rubric_state(folder) != "valid":
        return []
    body = folder / BODY_NAME
    try:
        text = body.read_text(encoding="utf-8") if body.is_file() else None
    except (OSError, UnicodeError):
        text = None
    trace = rubric_trace.build_trace(folder, text)
    return ["", "## Rubric trace", "", *rubric_trace.table_lines(trace), "", rubric_trace.summary_line(trace),
            *[f"Note: {note}" for note in trace.notes]]


def render(folder: Path) -> str:
    folder = Path(folder)
    return "\n".join([f"# Approval packet: {folder.name}", "", *_files_section(folder), "",
                      *_verify_section(folder), *_rubric_section(folder)]) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print the approval packet (preview links, verify matrix, missing items); read-only."
    )
    parser.add_argument("folder", type=Path)
    parser.add_argument("--open", action="store_true",
                        help="also open the preview PDF for the reviewer, only when it is fresh")
    args = parser.parse_args(argv)
    if not (args.folder / "report.yml").is_file():
        print(f"approval packet input error: report folder not found: {args.folder}", file=sys.stderr)
        return 2
    try:
        print(render(args.folder), end="")
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"approval packet input error: {exc}", file=sys.stderr)
        return 2
    if args.open:
        _open_preview(args.folder)
    return 0


def _open_preview(folder: Path) -> None:
    pdf = preview_pdf(folder)
    if not pdf.is_file() or not draft_preview_is_fresh(folder):
        print("preview not opened: rebuild the preview first (draft_pdf.py)", file=sys.stderr)
        return
    error = pdf_viewer.open_pdf(pdf)
    print(f"preview not opened: {error}" if error else f"opened {pdf.resolve()}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
