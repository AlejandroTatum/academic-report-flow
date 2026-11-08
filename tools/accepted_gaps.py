#!/usr/bin/env python3
"""The human waiver of named ``partial`` requirements (accepted-partial-gaps).

Some ``partial`` requirements only a person outside the flow can close (a
diagram the teacher agreed to skip, data the lab never produced). Without a way
to accept them the verify gate blocks forever. ``accepted-gaps.yml`` is that
way, and it is deliberately narrow: a human names each ``partial`` requirement
and the reason, the file binds those words to the exact ``body.md``,
``rubric.yml``, bibliography and recorded ``requirements`` of
``content-check.yml``, and ``content_check_state`` re-reads and re-validates it
on every call. Nothing is copied into ``content-check.yml``: the recorded
statuses stay ``partial``/``falta`` and ``rubric_grade`` still weighs the
partial at half.

What the waiver never does: cover a ``missing`` requirement, cover a mechanical
failure, survive an edit of any bound input, or apply to a requirement it does
not name. Like ``approval.yml`` and ``final-review.yml`` it is human-only: the
agent runs ``accept`` only after the person names the requirement and the
reason, and a bounded edit does not carry it (a changed body is a new check).

``accepted_gaps_state``/``waived_requirements``/``applied_gaps`` are pure and
read-only: they never write and never raise for a bad file (it is ``malformed``
or ``stale`` data the caller reports, never repaired here). ``accept`` is the
only writer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from approval_marker import BODY_NAME, sha256_file, utc_now, write_files_atomically
from report_config import ReportConfig, read_yaml

ACCEPTED_GAPS_NAME = "accepted-gaps.yml"
CONTENT_CHECK_NAME = "content-check.yml"
RUBRIC_NAME = "rubric.yml"
SCHEMA = "academic.accepted-gaps/v1"
_BINDING_KEYS = ("body_sha256", "rubric_sha256", "bib_sha256", "requirements_sha256")
_GAP_KEYS = ("criterion", "requirement", "gap", "reason")


@dataclass(frozen=True)
class AcceptedGapsState:
    """The waiver as derived from disk.

    ``state`` is exactly one of ``current|absent|stale|malformed``; ``detail``
    names the offending file or key. ``gaps`` is filled only when ``current``:
    each record carries ``criterion``, ``requirement``, ``gap``, ``reason`` and
    ``accepted_by`` (the gap's own, else the file's).
    """

    state: str
    detail: str = ""
    gaps: tuple[dict, ...] = ()

    @property
    def ok(self) -> bool:
        return self.state == "current"


def requirements_digest(requirements: object) -> str:
    """SHA-256 of the canonical JSON of the recorded ``requirements`` list.

    The same function hashes the in-memory list when ``content-check.yml`` is
    written and the list read back from it, so the binding survives the round trip.
    """
    text = json.dumps(requirements, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _blank(value: object) -> bool:
    return not isinstance(value, str) or not value.strip()


def _digest_or_empty(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return sha256_file(path)
    except OSError:
        return ""


def _bib_path(folder: Path) -> Path | None:
    try:
        return ReportConfig(folder=folder, raw=read_yaml(folder / "report.yml")).bib_path
    except Exception:
        return None


def _marker_requirements(folder: Path) -> list | None:
    """The ``requirements`` recorded in ``content-check.yml``, or ``None`` when unreadable."""
    try:
        data = yaml.safe_load((folder / CONTENT_CHECK_NAME).read_text(encoding="utf-8"))
    except Exception:
        return None
    requirements = data.get("requirements") if isinstance(data, dict) else None
    return requirements if isinstance(requirements, list) else None


def _stale(detail: str) -> AcceptedGapsState:
    return AcceptedGapsState("stale", detail)


def _malformed(detail: str) -> AcceptedGapsState:
    return AcceptedGapsState("malformed", detail)


def _derive(folder: Path, requirements: list | None) -> AcceptedGapsState:
    path = folder / ACCEPTED_GAPS_NAME
    if not path.is_file():
        return AcceptedGapsState("absent", f"{ACCEPTED_GAPS_NAME} missing")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return _malformed(f"{ACCEPTED_GAPS_NAME} is not a mapping")
    if data.get("schema") != SCHEMA:
        return _malformed(f"{ACCEPTED_GAPS_NAME} schema must be {SCHEMA}")
    for key in ("accepted_at", "accepted_by"):
        if _blank(data.get(key)):
            return _malformed(f"{ACCEPTED_GAPS_NAME} missing or blank {key}")
    for key in _BINDING_KEYS:
        if not isinstance(data.get(key), str):
            return _malformed(f"{ACCEPTED_GAPS_NAME} missing {key}")
    raw_gaps = data.get("gaps")
    if not isinstance(raw_gaps, list) or not raw_gaps:
        return _malformed(f"{ACCEPTED_GAPS_NAME} gaps must be a non-empty list")
    gaps: list[dict] = []
    for index, gap in enumerate(raw_gaps, start=1):
        if not isinstance(gap, dict):
            return _malformed(f"{ACCEPTED_GAPS_NAME} gap {index} is not a mapping")
        for key in _GAP_KEYS:
            if _blank(gap.get(key)):
                return _malformed(f"{ACCEPTED_GAPS_NAME} gap {index} missing or blank {key}")
        if "accepted_by" in gap and _blank(gap["accepted_by"]):
            return _malformed(f"{ACCEPTED_GAPS_NAME} gap {index} blank accepted_by")
        gaps.append({**{key: gap[key] for key in _GAP_KEYS}, "accepted_by": gap.get("accepted_by") or data["accepted_by"]})

    def bound(key: str, actual: str) -> bool:
        return str(data[key]).strip().lower() == actual

    if not bound("body_sha256", _digest_or_empty(folder / BODY_NAME)):
        return _stale(f"{ACCEPTED_GAPS_NAME} body_sha256 does not match {BODY_NAME}")
    rubric = folder / RUBRIC_NAME
    if not bound("rubric_sha256", _digest_or_empty(rubric if rubric.is_file() else None)):
        return _stale(f"{ACCEPTED_GAPS_NAME} rubric_sha256 does not match {RUBRIC_NAME}")
    if not bound("bib_sha256", _digest_or_empty(_bib_path(folder))):
        return _stale(f"{ACCEPTED_GAPS_NAME} bib_sha256 does not match the bibliography")
    recorded = _marker_requirements(folder) if requirements is None else requirements
    if recorded is None or not bound("requirements_sha256", requirements_digest(recorded)):
        return _stale(f"{ACCEPTED_GAPS_NAME} requirements_sha256 does not match {CONTENT_CHECK_NAME}")
    return AcceptedGapsState("current", "", tuple(gaps))


def accepted_gaps_state(report_dir: Path, requirements: list | None = None) -> AcceptedGapsState:
    """Derive the waiver state without touching disk; never raises.

    ``requirements`` is the list the caller is about to record or has just read
    from ``content-check.yml``; without it the file is read here.
    """
    try:
        return _derive(Path(report_dir), requirements)
    except Exception:
        return _malformed(f"{ACCEPTED_GAPS_NAME} unreadable")


def applied_gaps(report_dir: Path, requirements: list | None = None) -> list[dict]:
    """The accepted gaps of a current waiver that name a ``partial`` requirement in ``requirements``."""
    folder = Path(report_dir)
    try:
        recorded = _marker_requirements(folder) if requirements is None else requirements
        state = accepted_gaps_state(folder, recorded)
        if not state.ok or not isinstance(recorded, list):
            return []
        partial = {
            (str(r.get("criterion")), str(r.get("requirement")))
            for r in recorded
            if isinstance(r, dict) and r.get("status") == "partial"
        }
        return [g for g in state.gaps if (g["criterion"], g["requirement"]) in partial]
    except Exception:
        return []


def waived_requirements(report_dir: Path, requirements: list | None = None) -> frozenset[tuple[str, str]]:
    """``(criterion, requirement)`` of every ``partial`` a current, valid waiver accepts."""
    return frozenset((g["criterion"], g["requirement"]) for g in applied_gaps(report_dir, requirements))


def only_partials_block(report_dir: Path) -> bool:
    """True when the check fails only on ``partial`` requirements nobody accepted.

    No ``missing`` requirement, every mechanical check ok, at least one
    unaccepted ``partial``: the one situation where the human may waive.
    """
    folder = Path(report_dir)
    try:
        data = yaml.safe_load((folder / CONTENT_CHECK_NAME).read_text(encoding="utf-8"))
        requirements = data["requirements"]
        records = [r for r in requirements if isinstance(r, dict)]
        if len(records) != len(requirements) or any(r.get("status") not in ("found", "partial") for r in records):
            return False
        if any(not isinstance(m, dict) or m.get("ok") is not True for m in data["mechanical"]):
            return False
        waived = waived_requirements(folder, requirements)
        return any(
            r.get("status") == "partial" and (str(r.get("criterion")), str(r.get("requirement"))) not in waived
            for r in records
        )
    except Exception:
        return False


def _match(requirements: list, text: str, criterion: str | None) -> dict:
    """The one ``partial`` record whose requirement text is exactly ``text``; ``ValueError`` otherwise."""
    records = [r for r in requirements if isinstance(r, dict) and r.get("requirement") == text]
    if criterion is not None:
        owned = [r for r in records if str(r.get("criterion")) == criterion]
        if records and not owned:
            raise ValueError(f'requirement "{text}" does not belong to criterion {criterion}')
        records = owned
    if not records:
        raise ValueError(f'no requirement in {CONTENT_CHECK_NAME} has the exact text "{text}"')
    partial = [r for r in records if r.get("status") == "partial"]
    if len(partial) > 1:
        raise ValueError(f'requirement "{text}" is partial in several criteria; name one with --criterion')
    if partial:
        return partial[0]
    if any(r.get("status") == "found" for r in records):
        raise ValueError(f'requirement "{text}" is found: there is no gap to accept')
    raise ValueError(f'requirement "{text}" is missing: a missing requirement cannot be accepted; the draft must cover it')


def record_accepted_gaps(
    work_folder: Path, accepted_by: str, entries: list[tuple[str | None, str, str]]
) -> Path:
    """Append ``(criterion, requirement, reason)`` entries to ``accepted-gaps.yml``.

    Call it only after a human named each requirement and the reason. Raises
    ``ValueError`` (writing nothing) for a blank name or reason, a
    ``content-check.yml`` that is absent, stale or malformed, and any
    requirement that is not currently ``partial`` by exact text. A current
    waiver is extended (a repeated requirement takes the new reason); a stale or
    malformed one is replaced.
    """
    import content_check  # lazy: content_check imports this module

    folder = Path(work_folder)
    name = (accepted_by or "").strip()
    if not name:
        raise ValueError("--by must name the accepting human")
    if not entries:
        raise ValueError("--requirement is required")
    for _criterion, text, reason in entries:
        if not (text or "").strip():
            raise ValueError("--requirement must carry the exact requirement text")
        if not (reason or "").strip():
            raise ValueError(f'--reason must say why "{text}" is accepted')
    state = content_check.content_check_state(folder)
    if state in ("absent", "stale", "malformed"):
        raise ValueError(f"{CONTENT_CHECK_NAME} is {state}: run the verifier and content_check.py first")
    requirements = _marker_requirements(folder)
    if requirements is None:
        raise ValueError(f"{CONTENT_CHECK_NAME} has no requirement matrix")

    current = accepted_gaps_state(folder, requirements)
    merged: dict[tuple[str, str], dict] = {
        (g["criterion"], g["requirement"]): dict(g) for g in (current.gaps if current.ok else ())
    }
    for criterion, text, reason in entries:
        record = _match(requirements, text, criterion)
        merged[(str(record["criterion"]), text)] = {
            "criterion": str(record["criterion"]),
            "requirement": text,
            "gap": str(record.get("gap") or ""),
            "reason": reason.strip(),
            "accepted_by": name,
        }
    if any(not g["gap"].strip() for g in merged.values()):
        raise ValueError("a partial requirement without a recorded gap cannot be accepted")

    bib = _bib_path(folder)
    rubric = folder / RUBRIC_NAME
    data = {
        "schema": SCHEMA,
        "accepted_at": utc_now(),
        "accepted_by": name,
        "body_sha256": sha256_file(folder / BODY_NAME),
        "rubric_sha256": _digest_or_empty(rubric if rubric.is_file() else None),
        "bib_sha256": _digest_or_empty(bib),
        "requirements_sha256": requirements_digest(requirements),
        "gaps": list(merged.values()),
    }
    path = folder / ACCEPTED_GAPS_NAME
    write_files_atomically(
        [(path, yaml.safe_dump(data, sort_keys=False, allow_unicode=True).encode("utf-8"))]
    )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record the human acceptance of named partial requirements (never a missing one)."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    accept = commands.add_parser(
        "accept",
        help="write accepted-gaps.yml; only after the human names the requirement and the reason",
    )
    accept.add_argument("folder", type=Path)
    accept.add_argument("--by", required=True, help="the accepting human's name")
    accept.add_argument("--requirement", action="append", required=True,
                        help="the exact requirement text, as in content-check.yml (repeatable, paired with --reason)")
    accept.add_argument("--reason", action="append", required=True,
                        help="why the gap is acceptable (one per --requirement)")
    accept.add_argument("--criterion", action="append",
                        help="the owning criterion id when the text is ambiguous (none, or one per --requirement)")
    args = parser.parse_args(argv)
    if len(args.requirement) != len(args.reason):
        parser.error("give one --reason for every --requirement")
    if args.criterion and len(args.criterion) != len(args.requirement):
        parser.error("give --criterion for every --requirement, or for none")
    criteria = args.criterion or [None] * len(args.requirement)
    try:
        path = record_accepted_gaps(
            args.folder, args.by, list(zip(criteria, args.requirement, args.reason))
        )
    except (ValueError, OSError) as exc:
        print(f"accepted gaps not recorded: {exc}", file=sys.stderr)
        return 1
    print(f"recorded {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
