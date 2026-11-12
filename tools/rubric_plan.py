#!/usr/bin/env python3
"""The rubric-plan artifact: the teacher's rubric as a machine-checkable plan.

new-report-flow T3 makes the plan phase produce ``rubric.yml`` (schema
``academic.rubric/v1``): one criterion per rubric item, each mapped to the
``body.md`` heading that satisfies it. The draft writes against this plan and
the content check (``tools/content_check.py``) judges one criterion at a time,
so the schema here is the contract between those two phases.

``validate_rubric`` is the pure shape checker; ``rubric_state`` is the
folder-level predicate (``absent|malformed|valid``) status tools consume, and
``load_rubric`` returns the criteria of a valid plan. ``inventory_problems`` is the
evidence-coverage check against the guide inventory (``guide_facts.py``): every
inventory item (``G1``...) must be named by some criterion's ``deliverables:`` or
``covers:`` (an id, or the item's text) or by a top-level ``not_applicable:``
entry ``{item, reason}``; it never judges whether the criterion is good enough.
``rubric_matrix_sha256`` hashes the plan without its ``max_words`` ceilings, so a
ceilings-only change is recognizable after the plan is frozen. Like every marker
predicate in this repo, ``rubric_state`` never raises and never writes: an
unreadable, non-UTF-8 or non-mapping file is ``malformed`` data the caller can
report, never a crash and never something this module "repairs".
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

import guide_facts
from report_config import read_yaml

RUBRIC_NAME = "rubric.yml"
RUBRIC_SCHEMA = "academic.rubric/v1"

# Criterion ids are slugs: they name judgments in content-check.yml and the
# agent's judgments file, so they stay lowercase ASCII with hyphens.
_ID_PATTERN = re.compile(r"[a-z0-9-]+")


def _is_text(value: object) -> bool:
    """A required text key must be a string carrying visible content."""
    return isinstance(value, str) and value.strip() != ""


CHECK_PARAMS = {
    "heading_present": (("section",), ()),
    "contains": (("text",), ("section",)),
    "matches": (("pattern",), ("section",)),
    "verbatim_from_guide": (("section", "source", "text"), ()),
    "ordered_list": (("section",), ("min_items",)),
    "min_citations": (("count",), ("section",)),
    "figure_referenced": ((), ("section", "count")),
    "link_present": ((), ("section", "pattern")),
    "keywords_from_section": (("section", "from_section"), ("min",)),
}


# Numeric parameters: presence is checked with the required keys, the value by
# the positive-integer rule below.
_INT_KEYS = ("count", "min_items", "min")


# A literal ``text`` runs on three texts with opposite rules: the plain-text
# ``body.md``, the backend ``body.typeset.md`` and the PDF text. A formula, a
# Unicode superscript or a figure path cannot read the same in all three, so a
# check that names one is red in at least one of them whatever the draft says.
# A ``pattern`` never runs on the PDF text and can accept every notation, so it
# is the tolerant way to check one. These mirror the detectors in
# ``content_check.py`` (which imports this module, so it cannot be imported back).
_SCRIPT_CHARS_RE = re.compile("[\u2070-\u209f\u00b9\u00b2\u00b3]")
_MATH_RE = re.compile(r"\$\$|\$(?=\S)[^$\n]*(?<=\S)\$(?!\d)|\\\(|\\\[|\\[A-Za-z]+|\^")
_WINDOWS_PATH_RE = re.compile(
    r"(?<!\S)(?:"
    r"(?:[A-Za-z]:|\.{1,2}|\\)\\\S*"
    r"|[\w.-]+\\[\w.-]+\\\S*"
    r"|[\w.-]+\\[\w-]+\.[A-Za-z0-9]{1,5}\b"
    r")"
)
_FIGURE_RE = re.compile(r"!\[|\.(?:png|jpe?g|svg|gif|webp)\b", re.IGNORECASE)
_TYPESET_HINTS = {
    "formula": "check the words around the formula, or a matches pattern that accepts every notation",
    "Unicode superscript/subscript": "check the text without the superscript or subscript",
    "figure path": "use a figure_referenced check instead",
}


def _typeset_breaking(text: str) -> str | None:
    """Name what in a literal ``text`` cannot survive typeset, or None when it can."""
    if _SCRIPT_CHARS_RE.search(text):
        return "Unicode superscript/subscript"
    if _FIGURE_RE.search(text):
        return "figure path"
    return "formula" if _MATH_RE.search(_WINDOWS_PATH_RE.sub("", text)) else None


def count_checked_criteria(criteria: list[dict]) -> int:
    """Count criteria that carry at least one deterministic check."""
    return sum(bool(c.get("checks")) for c in criteria)


def _check_errors(check: object, label: str) -> list[str]:
    if not isinstance(check, dict):
        return [f"{label} must be a mapping"]
    kind = check.get("type")
    if kind not in CHECK_PARAMS:
        return [f"{label} unknown type '{kind}'"]
    required, optional = CHECK_PARAMS[kind]
    errors = []
    for key in required:
        if key in _INT_KEYS:
            if key not in check:
                errors.append(f"{label} {key} is required")
        elif not _is_text(check.get(key)):
            errors.append(f"{label} {key} must be a non-empty string")
    for key in ("section", "source", "text", "from_section", "pattern"):
        if key in check and not _is_text(check[key]):
            errors.append(f"{label} {key} must be a non-empty string")
    for key in _INT_KEYS:
        if key in check and (type(check[key]) is not int or check[key] <= 0):
            errors.append(f"{label} {key} must be a positive integer")
    for key in check.keys() - {"type", *required, *optional}:
        errors.append(f"{label} unexpected parameter '{key}'")
    if kind in ("matches", "link_present") and isinstance(check.get("pattern"), str):
        try:
            re.compile(check["pattern"])
        except re.error as exc:
            errors.append(f"{label} invalid regex: {exc}")
    reason = _typeset_breaking(check["text"]) if _is_text(check.get("text")) else None
    if reason:
        errors.append(
            f"{label} text cannot pass after typeset ({reason}): a text check runs on "
            f"body.md, body.typeset.md and the PDF text; {_TYPESET_HINTS[reason]}"
        )
    return errors


def _deliverable_errors(criterion: dict, index: int) -> list[str]:
    """Every deliverable the guide states needs its own non-heading check:
    a heading proves a section exists, never that a link or table is in it."""
    deliverables = criterion["deliverables"]
    if not isinstance(deliverables, list) or not deliverables or not all(_is_text(d) for d in deliverables):
        return [f"{RUBRIC_NAME} criterion {index} deliverables must be a non-empty list of strings"]
    checks = criterion.get("checks")
    checks = checks if isinstance(checks, list) else []
    real = sum(1 for c in checks if isinstance(c, dict) and c.get("type") != "heading_present")
    if real < len(deliverables):
        return [
            f"{RUBRIC_NAME} criterion {index} has {len(deliverables)} deliverables but "
            f"{real} non-heading checks (one non-heading check per deliverable)"
        ]
    return []


def _text_list_errors(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not all(_is_text(v) for v in value):
        return [f"{label} must be a list of non-empty strings"]
    return []


def _not_applicable_errors(entries: object) -> list[str]:
    if not isinstance(entries, list):
        return [f"{RUBRIC_NAME} not_applicable must be a list of {{item, reason}} mappings"]
    errors = []
    for index, entry in enumerate(entries, start=1):
        label = f"{RUBRIC_NAME} not_applicable {index}"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be a mapping with item and reason")
            continue
        for key in ("item", "reason"):
            if not _is_text(entry.get(key)):
                errors.append(f"{label} {key} must be a non-empty string")
        for key in entry.keys() - {"item", "reason"}:
            errors.append(f"{label} unexpected key '{key}'")
    return errors


def _is_positive_int(value: object) -> bool:
    # A word ceiling: a whole number above zero (bool is an int subclass).
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate_rubric(data: object) -> list[str]:
    """Return the schema errors of a parsed ``rubric.yml`` (empty = valid)."""
    if not isinstance(data, dict):
        return [f"{RUBRIC_NAME} must be a YAML mapping"]

    errors: list[str] = []
    if data.get("schema") != RUBRIC_SCHEMA:
        errors.append(f"{RUBRIC_NAME} schema must be '{RUBRIC_SCHEMA}'")
    if not _is_text(data.get("source")):
        errors.append(f"{RUBRIC_NAME} source must be a non-empty string")
    if "max_words" in data and not _is_positive_int(data["max_words"]):
        errors.append(f"{RUBRIC_NAME} max_words must be a positive integer")

    if "not_applicable" in data:
        errors.extend(_not_applicable_errors(data["not_applicable"]))

    criteria = data.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        errors.append(f"{RUBRIC_NAME} criteria must be a non-empty list")
        return errors

    seen: set[str] = set()
    for index, criterion in enumerate(criteria, start=1):
        if not isinstance(criterion, dict):
            errors.append(f"{RUBRIC_NAME} criterion {index} must be a mapping")
            continue
        cid = criterion.get("id")
        if not isinstance(cid, str) or not _ID_PATTERN.fullmatch(cid):
            errors.append(f"{RUBRIC_NAME} criterion {index} id must match [a-z0-9-]+")
        elif cid in seen:
            errors.append(f"{RUBRIC_NAME} duplicate criterion id '{cid}'")
        else:
            seen.add(cid)
        for key in ("title", "section"):
            if not _is_text(criterion.get(key)):
                errors.append(f"{RUBRIC_NAME} criterion {index} {key} must be a non-empty string")
        weight = criterion.get("weight")
        if weight is not None:
            # bool is an int subclass: a True/False weight is never a number > 0.
            if isinstance(weight, bool) or not isinstance(weight, (int, float)):
                errors.append(f"{RUBRIC_NAME} criterion {index} weight must be a number greater than 0")
            elif weight <= 0:
                errors.append(f"{RUBRIC_NAME} criterion {index} weight must be greater than 0")
        if "max_words" in criterion and not _is_positive_int(criterion["max_words"]):
            errors.append(f"{RUBRIC_NAME} criterion {index} max_words must be a positive integer")
        if "covers" in criterion:
            errors.extend(_text_list_errors(criterion["covers"], f"{RUBRIC_NAME} criterion {index} covers"))
        if "deliverables" in criterion:
            errors.extend(_deliverable_errors(criterion, index))
        if "checks" in criterion:
            checks = criterion["checks"]
            if not isinstance(checks, list):
                errors.append(f"{RUBRIC_NAME} criterion {index} checks must be a list")
            else:
                for check_index, check in enumerate(checks, start=1):
                    errors.extend(_check_errors(check, f"criterion {index} check {check_index}"))
    return errors


def rubric_state(report_dir: Path) -> str:
    """Derive the plan state of a report folder without touching anything.

    Exactly one of ``absent|malformed|valid``; a file that cannot be read or
    parsed, or whose parsed shape fails ``validate_rubric``, is ``malformed``.
    """
    folder = Path(report_dir)
    path = folder / RUBRIC_NAME
    if not path.is_file():
        return "absent"

    try:
        data = read_yaml(path)
    except Exception:
        return "malformed"
    if validate_rubric(data):
        return "malformed"
    return "valid"


def load_rubric(report_dir: Path) -> list[dict]:
    """Return the criteria of a valid plan, in file order (empty otherwise)."""
    folder = Path(report_dir)
    if rubric_state(folder) != "valid":
        return []
    try:
        data = read_yaml(folder / RUBRIC_NAME)
    except Exception:
        return []
    criteria = data.get("criteria")
    return [criterion for criterion in criteria if isinstance(criterion, dict)]


def load_max_words(report_dir: Path) -> int | None:
    """Return the plan's total word ceiling (``max_words``), or None."""
    folder = Path(report_dir)
    if rubric_state(folder) != "valid":
        return None
    try:
        data = read_yaml(folder / RUBRIC_NAME)
    except Exception:
        return None
    value = data.get("max_words")
    return value if _is_positive_int(value) else None


def rubric_matrix_sha256(report_dir: Path) -> str:
    """Hash of the parsed plan without its word ceilings (faster-verify-loop S4).

    ``max_words`` (top level and per criterion) never changes the requirement
    matrix, so two plans that differ only there hash the same. The exact
    ``rubric_sha256`` binding and its staleness rule are untouched: this hash only
    lets ``content_check --since`` carry unchanged sections across a ceilings-only
    change. ``""`` for a plan that is not valid. Never raises, never writes.
    """
    folder = Path(report_dir)
    if rubric_state(folder) != "valid":
        return ""
    try:
        data = dict(read_yaml(folder / RUBRIC_NAME))
    except Exception:
        return ""
    data.pop("max_words", None)
    data["criteria"] = [
        {key: value for key, value in criterion.items() if key != "max_words"} if isinstance(criterion, dict)
        else criterion
        for criterion in data["criteria"]
    ]
    try:
        canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return ""
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_ITEM_ID = re.compile(r"\bG\d+\b")


def _fold(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower().split())


def _is_mapped(item: dict, references: list[str], waivers: list[str]) -> bool:
    """Whether a criterion names the item (id or text) or a ``not_applicable:`` entry waives it."""
    text = _fold(item["text"])
    if any(item["id"] in _ITEM_ID.findall(ref) or text in _fold(ref) for ref in references):
        return True
    return any(w.strip().upper() == item["id"] or _fold(w) == text for w in waivers)


def inventory_problems(report_dir: Path) -> list[str]:
    """One line per guide inventory item no criterion names and no ``not_applicable:`` entry waives.

    Empty without a declared guide, an empty inventory or a valid rubric (a
    malformed rubric is reported by ``rubric_state``). Never raises, never writes.
    """
    folder = Path(report_dir)
    if rubric_state(folder) != "valid":
        return []
    try:
        data = read_yaml(folder / RUBRIC_NAME)
        inventory = guide_facts.load_guide_inventory(folder, read_yaml(folder / "report.yml"))
    except Exception:
        return []
    references = [
        text for criterion in data["criteria"] if isinstance(criterion, dict)
        for key in ("deliverables", "covers") for text in criterion.get(key) or [] if isinstance(text, str)
    ]
    waivers = [entry["item"] for entry in data.get("not_applicable") or []]
    return [
        f"{item['id']}: {item['kind']}: \"{item['text']}\" has no criterion (deliverables: or covers:) "
        "and no not_applicable: entry with a reason"
        for item in inventory if not _is_mapped(item, references, waivers)
    ]


def main(argv: list[str] | None = None) -> int:
    """CLI: validate ``<folder>/rubric.yml``; print problems, exit 1 on failure."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: rubric_plan.py <report-folder>")
        return 2
    path = Path(args[0]) / RUBRIC_NAME
    if not path.is_file():
        print(f"{RUBRIC_NAME} missing in {args[0]}")
        return 1
    try:
        problems = validate_rubric(read_yaml(path))
    except Exception as exc:
        problems = [f"{RUBRIC_NAME} unreadable: {exc}"]
    if problems:
        print("rubric_malformed:\n- " + "\n- ".join(problems))
        return 1
    unmapped = inventory_problems(Path(args[0]))
    if unmapped:
        print("guide_inventory_unmapped:\n- " + "\n- ".join(unmapped))
        return 1
    print(f"{RUBRIC_NAME} OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
