#!/usr/bin/env python3
"""Per-course memory: the teacher rubric, the feedback log and the AI declaration (S5).

A course is the report's delivery subject slug (``ReportConfig.delivery_subject_slug``);
its memory lives in the content root under ``academic-sources/<course-slug>/``:

    rubrics/*.yml   schema academic.course-rubric/v1: source, criteria[] of
                    {id, title, weight, levels[{points, descriptor}]}
    feedback.yml    schema academic.course-feedback/v1: optional
                    ai_declaration: include|omit, deliveries[] of
                    {work, date, grade, max, comments[], predicted?}

``course_memory.py <work-folder>`` is read-only: it prints the course's teacher criteria
as a ready ``origin: teacher`` block for rubric.yml, the graded deliveries with their
comments and the AI declaration decision. Anything missing or malformed is a
``warning:`` line and the exit code is always 0 (S2: it informs, it never blocks).
``--add-delivery`` appends one graded delivery to feedback.yml, its only write;
``--predicted`` stores the leveled grade /10 the report had at delivery, and the read
prints the mean absolute difference between predicted and teacher grades (S8,
orientative calibration, never a gate).
"""
from __future__ import annotations

import argparse
import math
import sys
from fractions import Fraction
from pathlib import Path

import yaml

import rubric_plan
from report_config import ReportConfig, read_yaml, resolve_content_root

RUBRIC_SCHEMA = "academic.course-rubric/v1"
FEEDBACK_SCHEMA = "academic.course-feedback/v1"
DECISIONS = ("include", "omit")


def course_slug(config: ReportConfig) -> str | None:
    """The course a report belongs to: its delivery subject slug, or ``None``."""
    try:
        return config.delivery_subject_slug
    except Exception:
        return None


def course_dir(slug: str) -> Path:
    return resolve_content_root() / "academic-sources" / slug


def _criterion_errors(data: object) -> list[str]:
    """Course-rubric errors, checked by the rubric.yml schema the criteria are copied into."""
    if not isinstance(data, dict) or data.get("schema") != RUBRIC_SCHEMA:
        return [f"schema must be '{RUBRIC_SCHEMA}'"]
    criteria = data.get("criteria")
    if not isinstance(criteria, list) or not criteria or not all(isinstance(c, dict) for c in criteria):
        return ["criteria must be a non-empty list of mappings"]
    missing = [f"criterion {i} levels missing" for i, c in enumerate(criteria, 1) if "levels" not in c]
    plan = {
        "schema": rubric_plan.RUBRIC_SCHEMA,
        "source": data.get("source"),
        "criteria": [{**c, "section": "-", "origin": "teacher"} for c in criteria],
    }
    prefix = rubric_plan.RUBRIC_NAME + " "
    problems = rubric_plan.validate_rubric(plan) + rubric_plan.rubric_warnings(plan)
    return missing + [e.removeprefix(prefix) for e in problems]


def course_rubrics(slug: str) -> tuple[list[tuple[str, dict]], list[str]]:
    """``[(relative file, data)]`` of the valid course rubrics, plus warnings. Never raises."""
    found, warnings = [], []
    for path in sorted((course_dir(slug) / "rubrics").glob("*.yml")):
        name = f"rubrics/{path.name}"
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            warnings.append(f"warning: {name} malformed: not readable YAML")
            continue
        errors = _criterion_errors(data)
        if errors:
            warnings.append(f"warning: {name} malformed: {errors[0]}")
        else:
            found.append((name, data))
    return found, warnings


def course_rubric_count(config: ReportConfig) -> int:
    """How many teacher criteria the report's course rubric holds (0 when none). Never raises."""
    slug = course_slug(config)
    if not slug:
        return 0
    try:
        return sum(len(data["criteria"]) for _, data in course_rubrics(slug)[0])
    except Exception:
        return 0


def _load_feedback(path: Path) -> tuple[dict | None, str]:
    """``(data, error)`` of feedback.yml; ``(None, "")`` when the file is absent."""
    if not path.is_file():
        return None, ""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None, "not readable YAML"
    if not isinstance(data, dict) or data.get("schema") != FEEDBACK_SCHEMA:
        return None, f"schema must be '{FEEDBACK_SCHEMA}'"
    if not isinstance(data.get("deliveries", []), list):
        return None, "deliveries must be a list"
    if "ai_declaration" in data and data["ai_declaration"] not in DECISIONS:
        return None, "ai_declaration must be 'include' or 'omit'"
    return data, ""


def _valid_delivery(entry: object) -> bool:
    if not isinstance(entry, dict) or not all(entry.get(k) not in (None, "") for k in ("work", "date")):
        return False
    return all(isinstance(entry.get(k), (int, float)) and not isinstance(entry.get(k), bool) for k in ("grade", "max"))


def _predicted(entry: dict) -> float | None:
    value = entry.get("predicted")
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _calibration(entries: list[dict]) -> list[str]:
    """Mean absolute difference between the predicted leveled grade and the teacher's, both /10."""
    pairs = [(Fraction(str(_predicted(e))), Fraction(str(e["grade"])) * 10 / Fraction(str(e["max"])))
             for e in entries if _predicted(e) is not None and e["max"]]
    if not pairs:
        return []
    mean = sum((abs(p - g) for p, g in pairs), Fraction(0)) / len(pairs)
    rounded = math.floor(mean * 10 + Fraction(1, 2)) / 10
    return [f"calibration: mean absolute difference {rounded:.1f}/10 between the leveled grade and the teacher's grade "
            f"(n={len(pairs)}; orientative, never a gate)"]


def _ai_lines(decision: str | None, config: ReportConfig) -> list[str]:
    """The course decision and how report.yml compares; informs only, changes nothing."""
    from doc_status import _ai_declaration_decided

    lines = [f"ai_declaration: {decision} (course decision in feedback.yml)"] if decision else [
        "ai_declaration: include (default; no course decision)",
        "warning: no AI declaration decision for this course; record ai_declaration: include|omit in feedback.yml",
    ]
    decision = decision or "include"
    opted_out = any(config.raw.get(key) is False for key in ("ai_declaration", "declaracion_ia"))
    if not _ai_declaration_decided(config):
        state = "no ai_declaration yet" if decision == "include" else "no ai_declaration: false yet"
        lines.append(f"warning: course decision is {decision} but report.yml has {state}")
    elif decision == "include" and opted_out:
        lines.append("warning: course decision is include but report.yml has ai_declaration: false")
    elif decision == "omit" and not opted_out:
        lines.append("warning: course decision is omit but report.yml carries an ai_declaration")
    return lines


def _config(folder: Path) -> ReportConfig:
    try:
        raw = read_yaml(folder / "report.yml")
    except Exception:
        raw = {}
    return ReportConfig(folder=folder, raw=raw)


def report(folder: Path) -> list[str]:
    """Every line the read prints. Never writes, never raises on course data."""
    config = _config(folder)
    slug = course_slug(config)
    if not slug:
        return ["warning: no course for this report (academic route with metadata.subject needed); no course memory read"]
    rel = f"academic-sources/{slug}"
    lines = [f"course: {slug} ({rel})"]
    rubrics, warnings = course_rubrics(slug)
    lines += warnings
    if not rubrics:
        lines.append(
            f"warning: no course rubric in {rel}/rubrics/ (save the teacher's rubric there once, schema {RUBRIC_SCHEMA})"
        )
    for name, data in rubrics:
        count = len(data["criteria"])
        lines.append(f"teacher rubric: {name} ({count} {'criterion' if count == 1 else 'criteria'}, source: {data['source']})")
        lines.append("add to rubric.yml criteria (set each section: to the body heading that answers it):")
        block = [
            {"id": c["id"], "title": c["title"], "section": "", "origin": "teacher"}
            | ({"weight": c["weight"]} if "weight" in c else {})
            | {"levels": c["levels"]}
            for c in data["criteria"]
        ]
        lines += yaml.safe_dump(block, sort_keys=False, allow_unicode=True).splitlines()
    feedback, error = _load_feedback(course_dir(slug) / "feedback.yml")
    if error:
        lines.append(f"warning: feedback.yml malformed: {error}")
    elif feedback is None:
        lines.append("warning: no feedback.yml for this course yet; after the teacher grades a delivery, record it with --add-delivery")
    else:
        entries = feedback.get("deliveries") or []
        good = [e for e in entries if _valid_delivery(e)]
        for index, entry in enumerate(entries, 1):
            if not _valid_delivery(entry):
                lines.append(f"warning: feedback.yml delivery {index} malformed (needs work, date, grade, max)")
        lines.append(f"deliveries: {len(good)} in feedback.yml")
        for entry in good:
            predicted = f" (predicted {_predicted(entry)})" if _predicted(entry) is not None else ""
            lines.append(f"- {entry['work']} {entry['date']}: {entry['grade']}/{entry['max']}{predicted}")
            lines += [f"  comment: {c}" for c in entry.get("comments") or [] if isinstance(c, str)]
        lines += _calibration(good)
    return lines + _ai_lines((feedback or {}).get("ai_declaration"), config)


def add_delivery(folder: Path, work: str | None, date: str | None, grade: str | None, maximum: str,
                 comments: list[str], predicted: str | None = None) -> list[str]:
    """Append one graded delivery to the course's feedback.yml; warn and write nothing on bad input."""
    config = _config(folder)
    slug = course_slug(config)
    if not slug:
        return ["warning: no course for this report (academic route with metadata.subject needed); delivery not recorded"]
    try:
        points, top = float(grade or ""), float(maximum)
    except ValueError:
        points = top = None
    if not date or points is None:
        return ["warning: --add-delivery needs --date and a numeric --grade; delivery not recorded"]
    try:
        leveled = float(predicted) if predicted is not None else None
    except ValueError:
        return ["warning: --predicted must be a number (the leveled grade /10); delivery not recorded"]
    path = course_dir(slug) / "feedback.yml"
    data, error = _load_feedback(path)
    if error:
        return [f"warning: feedback.yml malformed: {error}; delivery not recorded"]
    data = data or {"schema": FEEDBACK_SCHEMA}
    work = work or folder.name
    data["deliveries"] = list(data.get("deliveries") or []) + [
        {"work": work, "date": date, "grade": points, "max": top, "comments": list(comments)}
        | ({"predicted": leveled} if leveled is not None else {})
    ]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    except OSError as exc:  # S2: an unwritable log is a warning, never a failure
        return [f"warning: feedback.yml could not be written ({exc.__class__.__name__}); delivery not recorded"]
    note = f" (predicted {leveled})" if leveled is not None else ""
    return [f"recorded: {work} {date} {points}/{top:g}{note} in academic-sources/{slug}/feedback.yml"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path)
    parser.add_argument("--add-delivery", action="store_true", help="append one graded delivery to feedback.yml")
    parser.add_argument("--work", help="delivery name (default: the work folder name)")
    parser.add_argument("--date")
    parser.add_argument("--grade")
    parser.add_argument("--max", default="10")
    parser.add_argument("--predicted", help="the leveled grade /10 at delivery (rubric-grade.md), for calibration")
    parser.add_argument("--comment", action="append", default=[], help="one teacher comment (repeatable)")
    args = parser.parse_args(argv)
    folder = args.folder.expanduser().resolve()
    if args.add_delivery:
        lines = add_delivery(folder, args.work, args.date, args.grade, args.max, args.comment, args.predicted)
    else:
        lines = report(folder)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
