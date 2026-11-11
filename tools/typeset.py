#!/usr/bin/env python3
"""Typeset phase: format the plain-text body in its own file (issue #96).

Backend formatting is applied in ``body.typeset.md``, never in ``body.md``.
Binding a formatted copy does not assert human approval.

``typeset.yml`` binds ``body.typeset.md`` to the sha256 of the ``body.md`` it
formats. ``bind`` creates the typeset body as a copy of ``body.md`` when it is
missing (an existing one keeps its text) and records the binding plus a
``typeset-source.md`` snapshot of the bound ``body.md``; after an edit of
``body.md``, it refuses while the words the edit inserted are missing from
the typeset body or the text it removed is still there (issue #98).
``auto`` binds the same way and then applies the deterministic formatting
(``typeset_auto``: tables from ``- a; b; c`` lines, ``Figura:`` lines, bare
URLs) to a typeset body that is still an untouched copy of ``body.md``; it
never rewrites one that was already formatted, and lists what it leaves.
``check`` reports and never edits a body (it only appends
its duration to ``timings.yml``): the binding
matches the current ``body.md``, the typeset body passes the rendering rules
and the format's fixed headings, and it cites exactly the keys ``body.md``
cites. Builds render ``body.typeset.md`` while its binding is current
(``ReportConfig.body_path``).

An ``approval.yml`` without ``typeset: required`` predates this phase: its
``body.md`` is already formatted and renders as before, unless a typeset body
was bound anyway; then the build renders it and the same checks apply.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

import timings
import typeset_auto
from approval_marker import BODY_NAME, MARKER_NAME, utc_now, write_files_atomically
from content_check import body_format_problems
from report_config import (
    TYPESET_BINDING_NAME,
    TYPESET_BODY_NAME,
    ReportConfig,
    read_yaml,
    typeset_binding_current,
)
from validate_ieee_refs import cited_keys
from validate_report import SECTION_SPECS, section_structure_validation

BINDING_SCHEMA = "academic.typeset/v1"
SOURCE_NAME = "typeset-source.md"
_TOKEN_RE = re.compile(r"[^\W_]+")


def typeset_required(folder: Path) -> bool:
    """True when the approval marker was recorded under the plain-text contract."""
    try:
        marker = read_yaml(Path(folder) / MARKER_NAME)
    except Exception:
        return False
    return str(marker.get("typeset") or "").strip() == "required"


def typeset_in_use(folder: Path) -> bool:
    """True when the build renders ``body.typeset.md``: required, or bound on a legacy report."""
    return not (Path(folder) / MARKER_NAME).is_file() or typeset_required(folder) or typeset_binding_current(folder)


def _tokens(text: str) -> list[str]:
    """Lowercase word tokens; formatting marks (``**``, ``$``, ``\\``) drop out."""
    return [token.lower() for token in _TOKEN_RE.findall(text)]


def _occurrences(needle: list[str], haystack: list[str]) -> int:
    size = len(needle)
    return sum(haystack[i : i + size] == needle for i in range(len(haystack) - size + 1))


def unapplied_edit(source: str, body: str, typeset_text: str) -> list[str]:
    """What of the ``source`` -> ``body`` edit is not in ``typeset_text``; empty when applied.

    Inserted word runs must appear in the typeset body; a removed run, with one
    word of context on each side, must not appear there more often than in
    ``body``. Words are compared as tokens, so formatting around them is free.
    """
    old, new = source.split(), body.split()
    typeset_tokens, body_tokens = _tokens(typeset_text), _tokens(body)
    missing: list[str] = []
    present: list[str] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        inserted = " ".join(new[j1:j2])
        if _tokens(inserted) and not _occurrences(_tokens(inserted), typeset_tokens):
            missing.append(f"«{inserted}»")
        if i2 > i1:
            removed = " ".join(old[max(i1 - 1, 0) : i2 + 1])
            needle = _tokens(removed)
            if needle and _occurrences(needle, typeset_tokens) > _occurrences(needle, body_tokens):
                present.append(f"«{removed}»")
    problems = []
    if missing:
        problems.append("missing: " + ", ".join(missing))
    if present:
        problems.append("still present: " + ", ".join(present))
    return problems


def bind(folder: Path) -> Path:
    """Bind a formatted copy to the current body without asserting approval.

    A missing body is an input error. An edit since the last bind must be
    applied in the formatted copy before rebinding.
    """
    folder = Path(folder)
    body = (folder / BODY_NAME).read_bytes()
    target = folder / TYPESET_BODY_NAME
    source = folder / SOURCE_NAME
    if target.is_file() and source.is_file():
        problems = unapplied_edit(
            source.read_text(encoding="utf-8"), body.decode("utf-8"), target.read_text(encoding="utf-8")
        )
        if problems:
            raise ValueError(
                f"the {BODY_NAME} edit is not in {TYPESET_BODY_NAME} ({'; '.join(problems)}): "
                f"apply it there, then bind again"
            )
    binding = (
        f"schema: {BINDING_SCHEMA}\n"
        f"body_sha256: {hashlib.sha256(body).hexdigest()}\n"
        f"bound_at: {utc_now()}\n"
    ).encode("utf-8")
    files = [] if target.is_file() else [(target, body)]
    write_files_atomically([*files, (source, body), (folder / TYPESET_BINDING_NAME, binding)])
    return target


def auto(folder: Path) -> tuple[Path, dict[str, int] | None]:
    """Bind, then format a typeset body that is still an untouched copy of the body.

    Returns the typeset path and the conversion counts, or ``None`` instead of
    the counts when the typeset body already differed and was left unchanged.
    """
    folder = Path(folder)
    body = (folder / BODY_NAME).read_bytes()
    target = folder / TYPESET_BODY_NAME
    untouched = not target.is_file() or target.read_bytes() == body
    # Decode before binding: an unreadable body must refuse without writing anything.
    formatted, counts = typeset_auto.auto_format(body.decode("utf-8"))
    bind(folder)
    if not untouched:
        return target, None
    write_files_atomically([(target, formatted.encode("utf-8"))])
    return target, counts


def _result(check: str, problems: list[str], passed: str) -> dict:
    return {"check": check, "ok": not problems, "detail": "; ".join(problems) or passed}


def check_results(folder: Path) -> list[dict]:
    """The typeset checks as ``check``/``ok``/``detail`` entries; read-only."""
    folder = Path(folder)
    target = folder / TYPESET_BODY_NAME
    if not target.is_file():
        return [_result("binding", [f"{TYPESET_BODY_NAME} missing"], "")]
    binding_problems = []
    if not typeset_binding_current(folder):
        binding_problems.append(
            f"{BODY_NAME} changed since typeset (or {TYPESET_BINDING_NAME} is missing): apply the same "
            f"change to {TYPESET_BODY_NAME}, then run typeset.py bind"
        )
    results = [_result("binding", binding_problems, f"{TYPESET_BODY_NAME} formats the current {BODY_NAME}")]
    text = target.read_text(encoding="utf-8")
    results.append(_result("body_format", body_format_problems(text), "level-1 headings, no Unicode sub/superscripts"))
    results.append(
        _result(
            "table_headers",
            [f"line {number}: table without column names" for number, _ in typeset_auto.empty_table_headers(text)],
            "every table names its columns",
        )
    )
    config = ReportConfig(folder=folder, raw={**read_yaml(folder / "report.yml"), "body": TYPESET_BODY_NAME})
    if config.format in SECTION_SPECS:
        results.append(
            _result(
                f"{config.format}_structure",
                section_structure_validation(config).errors,
                f"fixed {config.format.upper()} headings present and in order",
            )
        )
    source = cited_keys((folder / BODY_NAME).read_text(encoding="utf-8"))
    typeset_keys = cited_keys(text)
    citation_problems = []
    if source - typeset_keys:
        citation_problems.append("missing: " + ", ".join(sorted(source - typeset_keys)))
    if typeset_keys - source:
        citation_problems.append("added: " + ", ".join(sorted(typeset_keys - source)))
    results.append(_result("citations_match", citation_problems, f"same {len(source)} cited keys as {BODY_NAME}"))
    return results


def build_gate(folder: Path) -> str | None:
    """Why a final build must wait for typeset, or ``None`` when it may run."""
    if not typeset_in_use(folder):
        return None
    failed = [item for item in check_results(folder) if not item["ok"]]
    if not failed:
        return None
    return "; ".join(f"{item['check']}: {item['detail']}" for item in failed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Format body.md in body.typeset.md without draft approval.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (
        ("bind", "create body.typeset.md if missing and bind it to the current body.md"),
        (
            "auto",
            "bind, then format an untouched body.typeset.md: tables from '- a; b; c' lines, "
            "'Figura:' lines and bare URLs; lists what it leaves for you",
        ),
        ("check", "report the typeset checks; never edits a body (records timings.yml)"),
    ):
        commands.add_parser(name, help=text).add_argument("folder", type=Path)
    args = parser.parse_args(argv)
    if args.command == "bind":
        try:
            target = bind(args.folder)
        except (ValueError, OSError) as exc:
            print(f"typeset not bound: {exc}", file=sys.stderr)
            return 1
        print(f"bound {target} to {BODY_NAME}; format it there, never in {BODY_NAME}")
    if args.command == "auto":
        try:
            target, counts = auto(args.folder)
        except (ValueError, OSError) as exc:
            print(f"typeset not bound: {exc}", file=sys.stderr)
            return 1
        if counts is None:
            print(
                f"bound {target} to {BODY_NAME}; {TYPESET_BODY_NAME} already differs from {BODY_NAME}, "
                f"auto left it unchanged"
            )
        else:
            print(
                f"bound {target} to {BODY_NAME}; auto formatted {counts['tables']} table(s), "
                f"{counts['figures']} figure(s), {counts['urls']} URL(s)"
            )
        for item in typeset_auto.pending(target.read_text(encoding="utf-8")):
            print(f"  left for you: {item}")
    try:
        # A refused bind wrote nothing and returned above; only a real check is timed.
        with timings.timed(args.folder, "typeset", "typeset.py"):
            results = check_results(args.folder)
    except (OSError, ValueError, TypeError) as exc:
        print(f"typeset check input error: {exc}", file=sys.stderr)
        return 2
    for item in results:
        print(f"  [{'ok' if item['ok'] else 'FAIL'}] {item['check']}: {item['detail']}")
    if args.command in ("bind", "auto"):
        return 0
    return 0 if all(item["ok"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
