"""The leveled grade: the teacher rubric graded by its levels (guide-vs-teacher-rubric T4, S7, S2).

An independent strict grader that sees only the ``origin: teacher`` criteria with
their ``levels`` and ``body.md`` writes ``leveled-grade.yml`` in the work folder:

    schema: academic.leveled-grade/v1
    grader: <who graded>
    body_sha256: <sha256 of the body.md bytes it read>
    criteria: [{id, points, descriptor, evidence, missing}]

``points`` must be one of the criterion's level points. ``evaluate`` reads it and
returns the per-criterion levels, the weighted total (rubric weights when every
teacher criterion has one, else each criterion counts its top points) and the
``warning:``/``note:`` lines. It never writes and never raises: every problem is a
line, nothing blocks (S2).
"""
from __future__ import annotations

import hashlib
from fractions import Fraction
from pathlib import Path

import yaml

import rubric_plan
import rubric_trace

SCHEMA = "academic.leveled-grade/v1"
FILE = "leveled-grade.yml"
NO_FILE = (f"warning: no {FILE}: run the independent strict grader "
           "(teacher criteria with levels and the body only) before review")


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _load(path: Path) -> tuple[dict | None, str]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None, "not readable YAML"
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return None, f"schema must be '{SCHEMA}'"
    if not isinstance(data.get("criteria"), list):
        return None, "criteria must be a list"
    return data, ""


def _body_sha256(folder: Path) -> str | None:
    try:
        return hashlib.sha256((folder / rubric_trace.BODY_NAME).read_bytes()).hexdigest()
    except OSError:
        return None


def _level_line(cid: str, points: object, top: object, missing: str) -> str | None:
    if points is None or points >= top:
        return None
    kind = "warning" if Fraction(str(points)) <= Fraction(str(top)) / 2 else "note"
    tail = f"; missing for the top level: {missing}" if missing else ""
    fmt = rubric_trace.format_number
    return f"{kind}: {cid} at level {fmt(Fraction(str(points)))} of {fmt(Fraction(str(top)))}{tail}"


def evaluate(folder: Path) -> tuple[dict | None, list[str]]:
    """``(result, lines)``; ``result`` is None when there is nothing to level or no usable file."""
    try:
        return _evaluate(Path(folder))
    except Exception as exc:  # never raises: an unexpected input is a warning
        return None, [f"warning: {FILE} could not be read ({exc.__class__.__name__}); no leveled grade"]


def _evaluate(folder: Path) -> tuple[dict | None, list[str]]:
    leveled = [c for c in rubric_plan.teacher_criteria(folder) if isinstance(c.get("levels"), list)]
    if not leveled:
        return None, []
    path = folder / FILE
    if not path.is_file():
        return None, [NO_FILE]
    data, error = _load(path)
    if error:
        return None, [f"warning: {FILE} malformed: {error}; no leveled grade"]
    lines = []
    if data.get("body_sha256") != _body_sha256(folder):
        lines.append(f"warning: {FILE} is stale: body.md changed since the grader read it; "
                     "re-run the independent strict grader")
    known = {str(c["id"]) for c in leveled}
    entries: dict[str, dict] = {}
    for index, entry in enumerate(data["criteria"], start=1):
        if not isinstance(entry, dict) or entry.get("id") in (None, ""):
            lines.append(f"warning: {FILE} entry {index} malformed (needs id and points)")
        elif str(entry["id"]) not in known:
            lines.append(f"warning: {FILE} grades {entry['id']}, not a teacher criterion with levels; ignored")
        else:
            entries.setdefault(str(entry["id"]), entry)
    weights, source = rubric_trace.effective_weights(leveled)
    rows, level_lines = [], []
    score = total = Fraction(0)
    for criterion in leveled:
        cid = str(criterion["id"])
        points_set = [lv["points"] for lv in criterion["levels"]]
        top = max(points_set)
        entry = entries.get(cid)
        points = entry.get("points") if entry else None
        if entry is None:
            lines.append(f"warning: {cid} not graded in {FILE}; counted as 0")
        elif not _number(points) or points not in points_set:
            levels = ", ".join(rubric_trace.format_number(Fraction(str(p))) for p in points_set)
            lines.append(f"warning: {cid} points {points} are not one of its levels ({levels}); counted as 0")
            points = None
        weight = weights[cid] if source == "rubric" else Fraction(str(top))
        if points is not None:
            score += weight * Fraction(str(points)) / Fraction(str(top))
        total += weight
        missing = str((entry or {}).get("missing") or "")
        line = _level_line(cid, points, top, missing)
        if line:
            level_lines.append(line)
        rows.append({"id": cid, "title": str(criterion.get("title", cid)), "weight": weight, "points": points,
                     "top": top, "descriptor": str((entry or {}).get("descriptor") or ""),
                     "evidence": str((entry or {}).get("evidence") or ""), "missing": missing})
    result = {"grader": data.get("grader"), "weights": source, "criteria": rows, "score": score, "total": total}
    return result, lines + level_lines
