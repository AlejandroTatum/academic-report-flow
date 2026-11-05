#!/usr/bin/env python3
"""Final rubric grade table: a mechanical estimate over the verified requirements (skill-rubric-improvements T3, S2).

``rubric_grade.py <folder>`` writes ``rubric-grade.yml`` and ``rubric-grade.md`` in the
working folder (never the delivery folder) and prints the table. Per criterion:
weight, evidence location (body section and, when the final PDF exists, its page),
estimated score ``weight * (found + 0.5 * partial) / total`` over the requirements of
the current verification, and the gap. A red deterministic check zeroes its criterion.
The total is shown over the rubric total and as a share in %.

The verifier never scores; this tool computes the score from the matrix the verifier
recorded. It is informational: nothing blocks on it, and it is not the teacher's grade.
Exit codes: 0 written (or no rubric to grade), 2 input error.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import sys
from fractions import Fraction
from pathlib import Path

import rubric_plan
import rubric_trace
import yaml
from report_config import TYPESET_BODY_NAME, ReportConfig, read_yaml, typeset_binding_current

GRADE_SCHEMA = "academic.rubric-grade/v1"
GRADE_YML = "rubric-grade.yml"
GRADE_MD = "rubric-grade.md"
LABEL = "This is a mechanical estimate, not the teacher's grade: the tool computes it from the verifier's requirement matrix."


def round_half_up(value: Fraction, places: int) -> float:
    scale = 10 ** places
    return math.floor(value * scale + Fraction(1, 2)) / scale


def _score(criterion: rubric_trace.CriterionTrace) -> Fraction:
    found, partial, total = criterion.counts()
    if criterion.failed_checks or not total:
        return Fraction(0)
    return criterion.weight * (found + Fraction(1, 2) * partial) / total


def _gap(criterion: rubric_trace.CriterionTrace) -> str:
    parts = [f"{r['status']}: {r['requirement']}" + (f" (gap: {r['gap']})" if r.get("gap") else "")
             for r in criterion.requirements if r["status"] != "found"]
    parts += criterion.failed_checks
    if not criterion.requirements:
        parts.append("no requirements verified")
    return "; ".join(parts)


def _evidence(criterion: rubric_trace.CriterionTrace, pdf: rubric_trace.PdfText | None) -> list[dict]:
    entries: list[dict] = []
    for r in criterion.requirements:
        if r["status"] == "missing" or not r["evidence"]:
            continue
        entry = {"section": r["section"] or criterion.section,
                 "page": pdf.find(r["evidence"]) if pdf is not None and pdf.available else None}
        if entry not in entries:
            entries.append(entry)
    return entries


def _evidence_text(entries: list[dict]) -> str:
    return "; ".join(e["section"] + (f", p. {e['page']}" if e["page"] else "") for e in entries) or "-"


def build_grade(folder: Path, trace: rubric_trace.Trace, pdf_path: Path | None,
                pdf: rubric_trace.PdfText | None) -> dict:
    total_weight = sum((c.weight for c in trace.criteria), Fraction(0))
    scores = [_score(c) for c in trace.criteria]
    score = sum(scores, Fraction(0))
    rows = [{
        "id": c.id, "title": c.title, "section": c.section,
        "weight": float(c.weight) if c.weight.denominator != 1 else int(c.weight),
        "evidence": _evidence(c, pdf),
        "found": c.counts()[0], "partial": c.counts()[1], "total": c.counts()[2],
        "score": round_half_up(s, 2), "gap": _gap(c),
    } for c, s in zip(trace.criteria, scores)]
    return {
        "schema": GRADE_SCHEMA,
        "estimate": "mechanical",
        "weights": trace.weights,
        "body": trace.body_name,
        "pdf": pdf_path.name if pdf_path else None,
        "pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest() if pdf_path else None,
        "score": round_half_up(score, 2),
        "total": round_half_up(total_weight, 2),
        "percentage": round_half_up(score / total_weight * 100, 1) if total_weight else 0.0,
        "criteria": rows,
    }


def render_md(grade: dict, folder: Path, notes: list[str]) -> str:
    lines = [f"# Rubric grade: {folder.name}", "", LABEL, "",
             "| Criterion | Weight | Evidence | Estimated score | Gap |", "|---|---|---|---|---|"]
    for c in grade["criteria"]:
        cells = [f"{c['title']} ({c['id']})", rubric_trace.format_number(Fraction(str(c["weight"]))),
                 _evidence_text(c["evidence"]), f"{c['score']:.2f}", c["gap"]]
        lines.append("| " + " | ".join(rubric_trace._cell(cell) for cell in cells) + " |")
    lines += ["", f"Score: {grade['score']:.2f} / {grade['total']:.2f} ({grade['percentage']:.1f}%)", "",
              f"Body: {grade['body']}. PDF: {grade['pdf'] or 'none yet (pages need the final PDF)'}; pages are PDF pages."]
    lines += [f"Note: {note}" for note in notes]
    return "\n".join(lines) + "\n"


def _config(folder: Path) -> ReportConfig | None:
    try:
        return ReportConfig(folder=folder, raw=read_yaml(folder / "report.yml"))
    except Exception:
        return None


def _inside_delivery(folder: Path, config: ReportConfig | None) -> bool:
    try:
        delivery = config.delivery_dir if config is not None else None
    except ValueError:
        return False
    if delivery is None:
        return False
    target = delivery.expanduser().resolve()
    return folder.resolve() == target or target in folder.resolve().parents


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the mechanical rubric grade table in the working folder.")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--body", help="body to run the checks on, relative to the folder "
                                       "(default: body.typeset.md while bound, else body.md)")
    parser.add_argument("--pdf", type=Path, help="final PDF for page lookup (default: the report's PDF when it exists)")
    args = parser.parse_args(argv)
    folder = args.folder
    if not (folder / rubric_plan.RUBRIC_NAME).is_file():
        print(f"no {rubric_plan.RUBRIC_NAME} in {folder}: nothing to grade")
        return 0
    if not rubric_trace.load_criteria(folder):
        print(f"rubric grade input error: {rubric_plan.RUBRIC_NAME} malformed in {folder}", file=sys.stderr)
        return 2
    config = _config(folder)
    if _inside_delivery(folder, config):
        print("rubric grade input error: refusing to write into the delivery folder; "
              "run it on the working folder", file=sys.stderr)
        return 2
    import content_check  # lazy: content_check imports validate_report

    state = content_check.content_check_state(folder)
    if state not in ("pass", "fail"):
        print(f"rubric grade input error: verification {state}: run the verifier and "
              "content_check.py --verification first", file=sys.stderr)
        return 2
    body_name = args.body or (TYPESET_BODY_NAME if typeset_binding_current(folder) else rubric_trace.BODY_NAME)
    try:
        body_text = (folder / body_name).read_text(encoding="utf-8")
        evidence_text = (folder / rubric_trace.BODY_NAME).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(f"rubric grade input error: {exc}", file=sys.stderr)
        return 2
    pdf_path = args.pdf or (config.pdf_path if config is not None and config.output_format == "pdf" else None)
    pdf_path = pdf_path if pdf_path is not None and Path(pdf_path).is_file() else None
    pdf = rubric_trace.PdfText(rubric_trace.pdf_pages(pdf_path)) if pdf_path else None
    trace = rubric_trace.build_trace(folder, body_text, body_name=body_name, evidence_text=evidence_text, pdf=None)
    notes = list(trace.notes)
    if pdf is not None and not pdf.available:
        notes.append("PDF text unavailable: evidence located by section only")
    grade = build_grade(folder, trace, pdf_path, pdf)
    text = render_md(grade, folder, notes)
    (folder / GRADE_YML).write_text(yaml.safe_dump(grade, sort_keys=False, allow_unicode=True), encoding="utf-8")
    (folder / GRADE_MD).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
