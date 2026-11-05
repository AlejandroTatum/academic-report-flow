#!/usr/bin/env python3
"""Rubric trace: which body sections cover each rubric criterion (skill-rubric-improvements T3, S1).

Read-only. For every criterion of ``rubric.yml`` it reports the weight, the body
sections that cover it (the planned section plus the sections holding the
verifier's evidence quotes), the deterministic checks that pass, and the
requirements the current verification found. It lists the uncovered criteria and
exits 1 when there are any, so the same command serves every point of the flow:
at plan (no body yet: all red), per section while drafting (``--section``), in
the approval packet, and in validate against ``body.typeset.md`` (``--body``)
and the final PDF text (``--pdf``).

Weights come from the rubric; when any criterion has none, every criterion gets
weight 1 and the report says so (a missing weight is never invented). The module
also owns the PDF text lookup that ``rubric_grade.py`` and ``validate_report.py``
share. Exit codes: 0 covered, 1 uncovered criteria, 2 input error.
"""
from __future__ import annotations

import argparse
import bisect
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import rubric_checks
import rubric_plan
from report_config import read_yaml

BODY_NAME = "body.md"
CONTENT_CHECK_NAME = "content-check.yml"
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_TOKEN_RE = re.compile(r"[^\W_]+")
_PDF_TEXT_CHECKS = {"contains": "text", "verbatim_from_guide": "text", "heading_present": "section"}


def load_criteria(folder: Path) -> list[dict]:
    return rubric_plan.load_rubric(Path(folder))


def effective_weights(criteria: list[dict]) -> tuple[dict[str, Fraction], str]:
    """Return ``({id: weight}, "rubric"|"equal")``: equal weights unless every criterion has one."""
    if criteria and all(c.get("weight") is not None for c in criteria):
        return {str(c["id"]): Fraction(str(c["weight"])) for c in criteria}, "rubric"
    return {str(c["id"]): Fraction(1) for c in criteria}, "equal"


def format_number(value: Fraction | float | int) -> str:
    """A weight as a short decimal: ``40``, ``2.5``."""
    number = Fraction(value)
    if number.denominator == 1:
        return str(number.numerator)
    return f"{float(number):.4f}".rstrip("0").rstrip(".")


# --- PDF text ---------------------------------------------------------------


def pdf_pages(pdf: Path) -> list[str]:
    """The text of each PDF page (``pdftotext``); empty when it cannot be read."""
    try:
        result = subprocess.run(["pdftotext", str(pdf), "-"], text=True, capture_output=True, check=False)
    except (OSError, ValueError):
        return []
    if result.returncode != 0:
        return []
    pages = result.stdout.split("\f")
    return pages[:-1] if pages and not pages[-1].strip() else pages


def squeeze(text: str) -> str:
    """Letters and digits only, folded: robust to line breaks, hyphenation and ligatures."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in folded if c.isalnum())


class PdfText:
    """Page-aware search over the squeezed text of a PDF."""

    def __init__(self, pages: list[str]) -> None:
        self.pages = pages
        self._starts: list[int] = []
        chunks: list[str] = []
        offset = 0
        for page in pages:
            self._starts.append(offset)
            chunk = squeeze(page)
            chunks.append(chunk)
            offset += len(chunk)
        self._text = "".join(chunks)

    @property
    def available(self) -> bool:
        return bool(self._text)

    def find(self, text: str) -> int | None:
        """The 1-based page where ``text`` starts, or None (long quotes also match by their start)."""
        needle = squeeze(text)
        if not needle or not self._text:
            return None
        index = self._text.find(needle)
        if index < 0 and len(needle) > 60:
            index = self._text.find(needle[:60])
        return bisect.bisect_right(self._starts, index) if index >= 0 else None

    def contains(self, text: str) -> bool:
        needle = squeeze(text)
        return bool(needle) and needle in self._text


# --- body structure ---------------------------------------------------------


def _own_sections(body: str) -> list[tuple[str, str]]:
    """``(heading, own text)`` for every ATX heading; own text stops at the next heading of any level."""
    sections: list[tuple[str, list[str]]] = []
    fence = False
    for line in body.splitlines():
        if _FENCE_RE.match(line):
            fence = not fence
        match = None if fence else _HEADING_RE.match(line)
        if match:
            sections.append((match.group(2).strip(), []))
        elif sections:
            sections[-1][1].append(line)
    return [(title, "\n".join(lines)) for title, lines in sections]


def section_of_quote(body: str, quote: str) -> str | None:
    """The innermost heading whose own text holds ``quote`` (whitespace-normalized)."""
    needle = " ".join(quote.split())
    if not needle:
        return None
    for title, text in _own_sections(body):
        if needle in " ".join(text.split()):
            return title
    return None


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text)]


def quote_in_text(quote: str, text: str) -> bool:
    """True when the word tokens of ``quote`` appear contiguously in ``text`` (markup ignored)."""
    needle, haystack = _tokens(quote), _tokens(text)
    size = len(needle)
    return bool(needle) and any(haystack[i:i + size] == needle for i in range(len(haystack) - size + 1))


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold()) if not unicodedata.combining(c)).strip()


# --- the trace --------------------------------------------------------------


@dataclass
class CriterionTrace:
    id: str
    title: str
    section: str
    weight: Fraction
    sections: list[str] = field(default_factory=list)
    checks_ok: int = 0
    checks_total: int = 0
    failed_checks: list[str] = field(default_factory=list)
    requirements: list[dict] = field(default_factory=list)  # status, requirement, evidence, section
    reasons: list[str] = field(default_factory=list)

    @property
    def covered(self) -> bool:
        return not self.reasons

    def counts(self) -> tuple[int, int, int]:
        """``(found, partial, total)`` over this criterion's verified requirements."""
        statuses = [r["status"] for r in self.requirements]
        return statuses.count("found"), statuses.count("partial"), len(statuses)


@dataclass
class Trace:
    body_name: str
    weights: str
    criteria: list[CriterionTrace]
    notes: list[str] = field(default_factory=list)

    @property
    def uncovered(self) -> list[CriterionTrace]:
        return [c for c in self.criteria if not c.covered]


def _verification(folder: Path) -> tuple[list[dict] | None, str]:
    """The current verification's requirements, or ``(None, note)`` when unusable."""
    import content_check  # lazy: content_check imports validate_report, which imports this module

    state = content_check.content_check_state(folder)
    if state == "absent":
        return None, ""
    if state not in ("pass", "fail"):
        return None, f"verification {state}: requirements not shown; re-run the verifier"
    try:
        data = read_yaml(folder / CONTENT_CHECK_NAME)
    except Exception:
        return None, "verification malformed: requirements not shown"
    records = [r for r in data.get("requirements") or [] if isinstance(r, dict)]
    if not records:
        return None, "verification has no requirement matrix (legacy marker): requirements not shown"
    return records, ""


def _check_sections(criterion: dict) -> list[str]:
    return [c["section"] for c in criterion.get("checks") or [] if isinstance(c, dict) and isinstance(c.get("section"), str)]


def serves_section(criterion: dict, name: str) -> bool:
    wanted = _fold(name)
    return any(_fold(s) == wanted for s in [str(criterion.get("section", "")), *_check_sections(criterion)])


def pdf_losses(folder: Path, criterion: dict, pdf: PdfText) -> list[str]:
    """Checked text (a ``contains``/verbatim phrase, a heading) that is absent from the PDF text."""
    lost = []
    for index, check in enumerate(criterion.get("checks") or [], start=1):
        key = _PDF_TEXT_CHECKS.get(check.get("type"))
        if key and isinstance(check.get(key), str) and not pdf.contains(check[key]):
            lost.append(f"check {index} ({check['type']}) '{check[key]}'")
    return lost


def build_trace(folder: Path, body_text: str | None, *, body_name: str = BODY_NAME,
                evidence_text: str | None = None, pdf: PdfText | None = None,
                section: str | None = None) -> Trace:
    """Trace every criterion over ``body_text`` (None = no body yet); read-only.

    ``evidence_text`` is where the verifier's quotes live (``body.md``); it
    defaults to ``body_text``. ``pdf`` adds the checked text lost in the PDF.
    """
    folder = Path(folder)
    criteria = load_criteria(folder)
    weights, source = effective_weights(criteria)
    notes = ["equal weights: rubric.yml has no weight on every criterion"] if source == "equal" else []
    records, note = _verification(folder)
    if note:
        notes.append(note)
    chosen = [c for c in criteria if section is None or serves_section(c, section)]
    body = body_text or ""
    evidence = body if evidence_text is None else evidence_text
    results = rubric_checks.run_checks(folder, chosen, body) if body_text is not None else []
    traces: list[CriterionTrace] = []
    for criterion in chosen:
        cid = str(criterion["id"])
        trace = CriterionTrace(cid, str(criterion.get("title", "")), str(criterion["section"]), weights[cid])
        own = [r for r in results if r.criterion_id == cid]
        trace.checks_total = len(criterion.get("checks") or [])
        trace.checks_ok = sum(r.ok for r in own)
        trace.failed_checks = [f"check {r.check_index} ({r.type}): {r.detail}" for r in own if not r.ok]
        for requirement in (r for r in records or [] if str(r.get("criterion")) == cid):
            quote = str(requirement.get("evidence") or "")
            located = section_of_quote(evidence, quote) if quote else None
            trace.requirements.append({
                "status": str(requirement.get("status")),
                "requirement": str(requirement.get("requirement") or ""),
                "evidence": quote,
                "section": located,
                "gap": str(requirement.get("gap") or ""),
            })
        if body_text is None:
            trace.reasons.append(f"{body_name} missing")
        else:
            if rubric_checks.has_section(body, trace.section):
                trace.sections.append(trace.section)
            else:
                trace.reasons.append(f"section '{trace.section}' missing")
            for requirement in trace.requirements:
                if requirement["status"] in ("found", "partial") and requirement["section"] \
                        and requirement["section"] not in trace.sections:
                    trace.sections.append(requirement["section"])
            trace.reasons.extend(trace.failed_checks)
            trace.reasons.extend(
                f"requirement {r['status']}: {r['requirement']}" + (f" (gap: {r['gap']})" if r["gap"] else "")
                for r in trace.requirements if r["status"] != "found")
            if pdf is not None and pdf.available:
                trace.reasons.extend(f"lost in the PDF: {loss}" for loss in pdf_losses(folder, criterion, pdf))
        traces.append(trace)
    return Trace(body_name, source, traces, notes)


# --- rendering --------------------------------------------------------------

TABLE_HEADER = ["| Rubric criterion | Weight | Sections | Checks | Requirements | Status |", "|---|---|---|---|---|---|"]


def _cell(value: object) -> str:
    return " ".join(str(value).split()).replace("|", "\\|")


def table_lines(trace: Trace) -> list[str]:
    rows = []
    for c in trace.criteria:
        found, partial, total = c.counts()
        requirements = "-" if not total else f"{found}/{total}" + (f" (+{partial} partial)" if partial else "")
        checks = f"{c.checks_ok}/{c.checks_total}" if c.checks_total else "-"
        rows.append(f"| {_cell(c.id)} | {format_number(c.weight)} | {_cell(', '.join(c.sections) or '-')} | "
                    f"{checks} | {requirements} | {'cumple' if c.covered else 'falta'} |")
    return [*TABLE_HEADER, *rows]


def summary_line(trace: Trace) -> str:
    return f"uncovered: {len(trace.uncovered)}/{len(trace.criteria)}"


def render(trace: Trace, folder: Path) -> str:
    lines = [f"# Rubric trace: {Path(folder).name}", "", f"body: {trace.body_name}", "", *table_lines(trace), "",
             summary_line(trace)]
    if trace.uncovered:
        lines += ["", "Uncovered:"]
        lines += [f"- {c.id}: {reason}" for c in trace.uncovered for reason in c.reasons]
    if trace.notes:
        lines += ["", "Notes:", *[f"- {note}" for note in trace.notes]]
    return "\n".join(lines) + "\n"


# --- CLI --------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Map each rubric criterion to the body sections that cover it (read-only).")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--section", help="only the criteria that body section serves (draft, section by section)")
    parser.add_argument("--body", default=BODY_NAME, help="body file to trace, relative to the folder (default body.md)")
    parser.add_argument("--pdf", type=Path, help="final PDF: also report checked text that never reached its text")
    args = parser.parse_args(argv)
    folder = args.folder
    if not (folder / rubric_plan.RUBRIC_NAME).is_file() or not load_criteria(folder):
        print(f"rubric trace input error: {rubric_plan.RUBRIC_NAME} missing or malformed in {folder}", file=sys.stderr)
        return 2
    body_path = folder / args.body
    try:
        body_text = body_path.read_text(encoding="utf-8") if body_path.is_file() else None
        evidence_path = folder / BODY_NAME
        evidence_text = evidence_path.read_text(encoding="utf-8") if evidence_path.is_file() else None
    except (OSError, UnicodeError) as exc:
        print(f"rubric trace input error: {exc}", file=sys.stderr)
        return 2
    pdf = PdfText(pdf_pages(args.pdf)) if args.pdf else None
    trace = build_trace(folder, body_text, body_name=body_path.name, evidence_text=evidence_text,
                        pdf=pdf, section=args.section)
    if args.section and not trace.criteria:
        print(f"rubric trace input error: no criterion maps to section '{args.section}'", file=sys.stderr)
        return 2
    if pdf is not None and not pdf.available:
        trace.notes.append("PDF text unavailable: PDF checks not run")
    print(render(trace, folder), end="")
    return 1 if trace.uncovered else 0


if __name__ == "__main__":
    sys.exit(main())
