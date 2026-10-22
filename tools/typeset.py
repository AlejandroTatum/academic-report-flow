#!/usr/bin/env python3
"""Typeset phase: format the approved plain-text body in its own file (issue #96).

The draft ``body.md`` the user verifies and approves is plain text. After
approval, backend formatting (math, tables, figures, the format's fixed
headings) is applied only in ``body.typeset.md``, never in ``body.md``, so a
formatting fix never invalidates verified or approved content.

``typeset.yml`` binds ``body.typeset.md`` to the sha256 of the ``body.md`` it
formats. ``bind`` creates the typeset body as a copy of ``body.md`` when it is
missing (an existing one keeps its text) and records the binding plus a
``typeset-source.md`` snapshot of the bound ``body.md``; it refuses while
``body.md`` is not approved, and, after an edit of ``body.md``, while the words
the edit inserted are missing from the typeset body or the text it removed is
still there (issue #98). ``check`` reports, never edits: the binding
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

from approval_marker import BODY_NAME, MARKER_NAME, approval_state, utc_now, write_files_atomically
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
    return typeset_required(folder) or typeset_binding_current(folder)


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
    """Create ``body.typeset.md`` if missing and bind it to the current ``body.md``.

    Raises ``ValueError`` (writing nothing) while ``body.md`` is not approved,
    or while an edit of ``body.md`` since the last bind is not applied in
    ``body.typeset.md``.
    """
    folder = Path(folder)
    state = approval_state(folder)
    if state.state not in ("current", "carried"):
        raise ValueError(f"{BODY_NAME} is not approved ({state.detail})")
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
    parser = argparse.ArgumentParser(description="Format the approved body.md in body.typeset.md.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (
        ("bind", "create body.typeset.md if missing and bind it to the current body.md (after approval)"),
        ("check", "report the typeset checks; never edits"),
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
    try:
        results = check_results(args.folder)
    except (OSError, ValueError, TypeError) as exc:
        print(f"typeset check input error: {exc}", file=sys.stderr)
        return 2
    for item in results:
        print(f"  [{'ok' if item['ok'] else 'FAIL'}] {item['check']}: {item['detail']}")
    if args.command == "bind":
        return 0
    return 0 if all(item["ok"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
