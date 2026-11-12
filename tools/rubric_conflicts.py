#!/usr/bin/env python3
"""Plan for the top level: the guide-vs-rubric conflict list (guide-vs-teacher-rubric S6, S2).

``rubric_conflicts.py <work-folder>`` reads ``rubric.yml`` and the guide declared in
``report.yml``. For every ``origin: teacher`` criterion it prints the top level (the
highest ``points``) descriptor as the target the draft must evidence, then warns:

- ``no evidence planned for the top level``: the criterion has levels but no
  ``deliverables:``, ``covers:`` or non-heading ``checks:``;
- ``rubric-only``: significant terms of its title and top descriptor never appear in
  the guide text (the rubric scores something the guide does not ask as a step);
- ``no levels``: a teacher criterion without the teacher's levels.

Significant terms are accent-folded words of 4+ letters outside a small Spanish/English
stopword set; a trailing ``s`` is ignored so singular and plural match. Without a
declared guide the term check is skipped; without teacher criteria the tool prints one
line. It is read-only and always exits 0: every finding is a ``warning:`` line (S2).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import guide_facts
import rubric_plan
from report_config import read_yaml

PREFIX = "rubric_conflicts:"
_WORD = re.compile(r"[a-z]{4,}")
_STOPWORDS = frozenset(
    # Spanish function words and generic verbs.
    "para como este esta estos estas esto todo toda todos todas cada desde entre sobre segun tambien pero "
    "porque donde cuando sino otro otra otros otras mismo misma solo sola sean estan tiene tienen hace hacen "
    "debe deben puede pueden mediante traves manera forma parte nivel muestra presenta "
    "realiza incluye cual cuales hasta aunque ademas "
    # English function words.
    "with that this these those from have their there into each which when where what also been were will "
    "they them than then does uses using some more most such only very"
    .split()
)


def _stem(word: str) -> str:
    return word[:-1] if word.endswith("s") else word


def _terms(text: str) -> list[str]:
    """Significant folded terms of ``text``, deduplicated in order of first appearance."""
    seen: dict[str, None] = {}
    for word in _WORD.findall(rubric_plan._fold(text)):
        if word not in _STOPWORDS:
            seen.setdefault(word, None)
    return list(seen)


def _top_level(criterion: dict) -> dict | None:
    levels = rubric_plan.criterion_levels(criterion)
    if not levels:
        return None
    return max(levels, key=lambda level: level["points"])


def _has_evidence(criterion: dict) -> bool:
    if criterion.get("deliverables") or criterion.get("covers"):
        return True
    return any(check.get("type") != "heading_present" for check in criterion.get("checks") or [])


def _guide_stems(folder: Path) -> set[str] | None:
    try:
        text = guide_facts._guide_text(folder, read_yaml(folder / "report.yml"))
    except Exception:
        return None
    if text is None:
        return None
    return {_stem(word) for word in _WORD.findall(rubric_plan._fold(text))}


def conflicts(report_dir: Path) -> list[str]:
    """The lines ``rubric_conflicts.py`` prints for a work folder. Never raises, never writes."""
    try:
        return _conflicts(Path(report_dir))
    except Exception as exc:  # S2: an unexpected input is a warning, never a crash
        return [f"warning: rubric_conflicts could not finish ({exc.__class__.__name__}); no conflict list"]


def _conflicts(folder: Path) -> list[str]:
    criteria = rubric_plan.teacher_criteria(folder)
    if not criteria:
        return [f"{PREFIX} no teacher criteria in rubric.yml (absent, malformed or guide-only); nothing to compare"]
    lines = []
    guide = _guide_stems(folder)
    if guide is None:
        lines.append(f"{PREFIX} no guide declared in report.yml; rubric-only terms not checked")
    noun = "criterion" if len(criteria) == 1 else "criteria"
    lines.append(f"{PREFIX} {len(criteria)} teacher {noun}; the draft must evidence each top level")
    warned = False
    for criterion in criteria:
        cid = criterion["id"]
        top = _top_level(criterion)
        found = []
        if top is not None:
            highest = top["points"]
            lines.append(f"{cid}: top level {top['points']:g} of {highest:g}: {top['descriptor']}")
            if not _has_evidence(criterion):
                found.append(
                    f"warning: {cid}: no evidence planned for the top level; "
                    "add deliverables: with checks, covers: or a non-heading check"
                )
        if guide is not None:
            text = criterion["title"] + (" " + top["descriptor"] if top else "")
            missing = [term for term in _terms(text) if _stem(term) not in guide]
            if missing:
                found.append(
                    f"warning: {cid}: rubric-only: the guide never mentions {', '.join(missing)}; "
                    "the teacher scores it, so plan evidence for it anyway"
                )
        if top is None:
            found.append(f"warning: {cid}: no levels; copy the teacher's levels into rubric.yml to plan for the top level")
        lines.extend(found)
        warned = warned or bool(found)
    if not warned:
        lines.append(f"{PREFIX} no guide-vs-rubric conflicts")
    return lines


def main(argv: list[str] | None = None) -> int:
    """CLI: print the top-level targets and the conflict list; always exit 0 (S2)."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: rubric_conflicts.py <work-folder>")
        return 0
    print("\n".join(conflicts(Path(args[0]))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
