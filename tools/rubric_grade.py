#!/usr/bin/env python3
"""Final rubric report: guide coverage and the leveled grade, apart (skill-rubric-improvements T3; guide-vs-teacher-rubric T4).

``rubric_grade.py <folder>`` writes ``rubric-grade.yml`` and ``rubric-grade.md`` in the
working folder (never the delivery folder) and prints them in two parts.

Guide coverage, a mechanical estimate over the criteria that are not ``origin: teacher``
(a legacy plan is all coverage). Per criterion:
weight, evidence location (body section and, when the final PDF exists, its page),
estimated score ``weight * (found + 0.5 * partial) / total`` over the requirements of
the current verification, and the gap. A red deterministic check zeroes its criterion.
The total is shown over the rubric total and as a share in %.

The verifier never scores; this tool computes the coverage from the matrix the verifier
recorded. Coverage measures what the body covers, never how well: it is not a grade.

Teacher rubric (leveled): the ``origin: teacher`` criteria at the level the independent
strict grader recorded in ``leveled-grade.yml`` (``leveled_grade.py``), the weighted total
and its /10 equivalent, with ``warning:``/``note:`` lines. Both parts are informational:
nothing blocks on them and neither is the teacher's grade.
Exit codes: 0 written (or no rubric to grade), 2 input error.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import sys
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import leveled_grade
import rubric_plan
import rubric_trace
import yaml
from report_config import TYPESET_BODY_NAME, ReportConfig, read_yaml, typeset_binding_current

GRADE_SCHEMA = "academic.rubric-grade/v1"
GRADE_YML = "rubric-grade.yml"
GRADE_MD = "rubric-grade.md"
LABEL = ("Guide coverage is a mechanical estimate, not the teacher's grade: the tool computes it from the "
         "verifier's requirement matrix; it measures what the body covers, never how well.")
LEVELED_LABEL = ("Leveled by the independent strict grader against the teacher's levels; "
                 "orientative, not the teacher's grade.")
NO_TEACHER = "No teacher criteria in rubric.yml: guide coverage only, no leveled grade."
EQUAL_NOTE = "equal weights: rubric.yml has no weight on every criterion"


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


def guide_coverage(folder: Path, trace: rubric_trace.Trace) -> rubric_trace.Trace:
    """The trace without the teacher criteria, reweighted over the guide criteria (a legacy plan is unchanged)."""
    teacher = {str(c["id"]) for c in rubric_plan.teacher_criteria(folder)}
    if not teacher:
        return trace
    guide = [c for c in rubric_trace.load_criteria(folder) if str(c["id"]) not in teacher]
    weights, source = rubric_trace.effective_weights(guide)
    notes = [n for n in trace.notes if n != EQUAL_NOTE]
    if source == "equal" and guide:
        notes.insert(0, "equal weights: the guide criteria do not all carry a weight")
    criteria = [replace(c, weight=weights[c.id]) for c in trace.criteria if c.id not in teacher]
    return replace(trace, weights=source, criteria=criteria, notes=notes)


def leveled_section(leveled: dict | None) -> dict | None:
    if leveled is None:
        return None
    total = leveled["total"]
    return {
        "grader": leveled["grader"], "weights": leveled["weights"],
        "score": round_half_up(leveled["score"], 2), "total": round_half_up(total, 2),
        "out_of_10": round_half_up(leveled["score"] / total * 10, 1) if total else 0.0,
        "criteria": [{**row, "weight": float(row["weight"])} for row in leveled["criteria"]],
    }


def build_grade(folder: Path, trace: rubric_trace.Trace, pdf_path: Path | None,
                pdf: rubric_trace.PdfText | None, leveled: dict | None = None) -> dict:
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
        "leveled": leveled_section(leveled),
    }


def _leveled_lines(grade: dict, teacher: bool, lines: list[str]) -> list[str]:
    out = ["", "## Teacher rubric (leveled)", ""]
    leveled = grade["leveled"]
    if not teacher:
        return out + [NO_TEACHER]
    if leveled is not None:
        fmt = rubric_trace.format_number
        out += [LEVELED_LABEL + (f" Grader: {leveled['grader']}." if leveled["grader"] else ""), "",
                "| Criterion | Weight | Level | Matched descriptor | Missing for the top level |",
                "|---|---|---|---|---|"]
        for c in leveled["criteria"]:
            level = (fmt(Fraction(str(c["points"]))) if c["points"] is not None else "-") + "/" + fmt(Fraction(str(c["top"])))
            cells = [f"{c['title']} ({c['id']})", fmt(Fraction(str(c["weight"]))), level,
                     c["descriptor"] or "-", c["missing"] or "-"]
            out.append("| " + " | ".join(rubric_trace._cell(cell) for cell in cells) + " |")
        out += ["", f"Leveled grade: {leveled['score']:.2f} / {leveled['total']:.2f} ({leveled['out_of_10']:.1f}/10)"]
    return out + ([""] + lines if lines else [])


def render_md(grade: dict, folder: Path, notes: list[str], teacher: bool = False,
              leveled_lines: list[str] | None = None) -> str:
    lines = [f"# Rubric report: {folder.name}", "", "## Guide coverage", "", LABEL, ""]
    if not grade["criteria"]:
        lines.append("No guide criteria in rubric.yml: nothing to cover mechanically.")
    else:
        lines += ["| Criterion | Weight | Evidence | Covered | Gap |", "|---|---|---|---|---|"]
    for c in grade["criteria"]:
        cells = [f"{c['title']} ({c['id']})", rubric_trace.format_number(Fraction(str(c["weight"]))),
                 _evidence_text(c["evidence"]), f"{c['score']:.2f}", c["gap"]]
        lines.append("| " + " | ".join(rubric_trace._cell(cell) for cell in cells) + " |")
    lines += ["", f"Coverage: {grade['score']:.2f} / {grade['total']:.2f} ({grade['percentage']:.1f}%)", "",
              f"Body: {grade['body']}. PDF: {grade['pdf'] or 'none yet (pages need the final PDF)'}; pages are PDF pages."]
    lines += [f"Note: {note}" for note in notes]
    lines += _leveled_lines(grade, teacher, leveled_lines or [])
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
    parser = argparse.ArgumentParser(description="Write guide coverage and the leveled grade in the working folder.")
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
    trace = guide_coverage(folder, rubric_trace.build_trace(
        folder, body_text, body_name=body_name, evidence_text=evidence_text, pdf=None))
    notes = list(trace.notes)
    if pdf is not None and not pdf.available:
        notes.append("PDF text unavailable: evidence located by section only")
    leveled, leveled_lines = leveled_grade.evaluate(folder)
    grade = build_grade(folder, trace, pdf_path, pdf, leveled)
    text = render_md(grade, folder, notes, bool(rubric_plan.teacher_criteria(folder)), leveled_lines)
    (folder / GRADE_YML).write_text(yaml.safe_dump(grade, sort_keys=False, allow_unicode=True), encoding="utf-8")
    (folder / GRADE_MD).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
