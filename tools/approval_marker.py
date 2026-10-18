#!/usr/bin/env python3
"""The shared approval-marker contract.

An approval is a file on disk, not a session variable: ``approval.yml`` binds a
human decision to the exact bytes of ``body.md`` through ``body_sha256``. Two
consumers share this predicate with different presentation: ``doc_status`` maps
the state onto a phase state and a blocked-reason token, and
``publish_validated_pdf`` maps it onto a user-facing abort message. Keeping the
predicate here -- and the presentation at each boundary -- is what stops the
routing layer and the irreversible publisher from disagreeing about approval.

A bounded edit made after the approval keeps it: ``record_approval`` writes
``approved-body.md`` next to the marker, and when ``body.md`` no longer matches
``body_sha256`` the approval is ``carried`` -- still valid -- only if that
snapshot hashes to ``body_sha256`` and the diff to the current ``body.md`` is
bounded (see ``bounded_edit``). Anything else is ``stale``, as before.

A marker that still carries a legacy ``preview_sha256`` key stays valid: keys
outside ``REQUIRED_KEYS`` are ignored data, and only ``body_sha256`` is checked.

``approval_state`` is pure and read-only: it never writes, never creates a
directory, and never raises for a bad marker (``record_approval`` is the only
writer, reached through the explicit-approval CLI): an unreadable or invalid marker
is ``malformed`` data the caller can report, never a crash and never something
this module "repairs".
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bounded_edit import bounded
from report_config import read_yaml

BODY_NAME = "body.md"
MARKER_NAME = "approval.yml"
SNAPSHOT_NAME = "approved-body.md"
MARKER_SCHEMA = "academic.doc-approval/v1"
REQUIRED_KEYS = ("body_sha256", "approved_at", "approved_by")

# The subset of REQUIRED_KEYS that binds a marker to a file's exact bytes,
# mapped to that file's name -- the single place a caller derives "which
# files does this marker bind" from, so a new bound file only has to be
# added here instead of re-listed at each call site.
BOUND_FILES = {"body_sha256": BODY_NAME}


def bound_file_names() -> tuple[str, ...]:
    """Return the files an approval marker binds, in REQUIRED_KEYS order."""
    return tuple(BOUND_FILES[key] for key in REQUIRED_KEYS if key in BOUND_FILES)


@dataclass(frozen=True)
class ApprovalState:
    """The approval marker as derived from disk.

    ``state`` is exactly one of ``current|carried|absent|stale|malformed``;
    ``reason`` is the bounded token ``"" | approval_marker_absent |
    approval_marker_stale | approval_marker_malformed``; ``detail`` is a short
    ASCII description naming the offending file or key (for ``carried``, the
    size of the bounded edit). ``ok`` is the one question every gate asks:
    ``current`` and ``carried`` both mean the approval holds.
    """

    state: str
    reason: str
    detail: str

    @property
    def ok(self) -> bool:
        return self.state in ("current", "carried")


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 of a file's raw bytes.

    Canonical home for the hash; ``publish_pdf`` re-exports it so existing
    callers (``build_report_auto.py``) keep working unchanged.
    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def draft_record_path(pdf_path: Path) -> Path:
    """Sidecar of a draft PDF holding the sha256 of the ``body.md`` it rendered."""
    pdf = Path(pdf_path)
    return pdf.with_name(f"{pdf.stem}.body.sha256")


def write_draft_record(pdf_path: Path, body_path: Path, digest: str | None = None) -> Path:
    """Record the ``body.md`` bytes a draft build rendered.

    ``digest`` is the hash taken before the build started, so an edit made
    while the build ran is not recorded as rendered.
    """
    record = draft_record_path(pdf_path)
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text((digest or sha256_file(body_path)) + "\n", encoding="utf-8")
    return record


# report.yml keys that only say where and what to publish; changing them after
# a build leaves the rendered PDF exactly as it was.
DELIVERY_ONLY_KEYS = ("delivery_dir", "deliver_bibliography")


def render_digest(report_yml: Path) -> str:
    """SHA-256 of the ``report.yml`` settings that shape the rendered PDF."""
    import json

    import yaml

    data = yaml.safe_load(Path(report_yml).read_text(encoding="utf-8")) or {}
    if isinstance(data, dict):
        data = {k: v for k, v in data.items() if k not in DELIVERY_ONLY_KEYS}
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render_record_path(folder: Path) -> Path:
    """Record of the ``report.yml`` settings the last build rendered."""
    return Path(folder) / "build" / "report.render.sha256"


def write_render_record(folder: Path, digest: str | None = None) -> Path:
    """Record the render settings a build used (``digest`` taken before it ran)."""
    record = render_record_path(folder)
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text((digest or render_digest(Path(folder) / "report.yml")) + "\n", encoding="utf-8")
    return record


def render_settings_unchanged(folder: Path) -> bool:
    """True when the last build recorded the current render settings of ``report.yml``."""
    record = render_record_path(folder)
    report_yml = Path(folder) / "report.yml"
    if not (record.is_file() and report_yml.is_file()):
        return False
    try:
        return record.read_text(encoding="utf-8").strip() == render_digest(report_yml)
    except Exception:
        return False


def draft_is_fresh(pdf_path: Path, body_path: Path) -> bool:
    """True when the draft PDF exists and its record matches the current ``body.md``."""
    record = draft_record_path(pdf_path)
    if not (Path(pdf_path).is_file() and record.is_file() and Path(body_path).is_file()):
        return False
    return record.read_text(encoding="utf-8").strip() == sha256_file(body_path)


def _malformed(detail: str) -> ApprovalState:
    return ApprovalState(state="malformed", reason="approval_marker_malformed", detail=detail)


def _is_missing_or_blank(value: object) -> bool:
    """A required key must be present and carry visible text."""
    return value is None or not str(value).strip()


def _carried(folder: Path, recorded: str) -> ApprovalState | None:
    """``carried`` when a trusted snapshot and the current body differ by a bounded edit.

    The snapshot is trusted only when its bytes hash to the approved
    ``body_sha256``; any other file is not evidence of what the human approved.
    """
    snapshot = folder / SNAPSHOT_NAME
    try:
        if not snapshot.is_file() or sha256_file(snapshot) != recorded:
            return None
        old = snapshot.read_text(encoding="utf-8")
        new = (folder / BODY_NAME).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    is_bounded, words = bounded(old, new)
    if not is_bounded:
        return None
    return ApprovalState(
        state="carried", reason="", detail=f"bounded edit since approval ({words} words)"
    )


def approval_state(work_folder: Path) -> ApprovalState:
    """Derive the approval state of a work folder without touching disk."""
    folder = Path(work_folder)
    marker_path = folder / MARKER_NAME

    if not marker_path.is_file():
        return ApprovalState(
            state="absent", reason="approval_marker_absent", detail=f"{MARKER_NAME} missing"
        )

    # A bad marker is data, not an exception: unreadable files and invalid YAML
    # both become `malformed` so a caller can fail closed with a named reason.
    try:
        data = read_yaml(marker_path)
    except Exception:
        return _malformed(f"{MARKER_NAME} is not valid YAML")

    for key in REQUIRED_KEYS:
        if _is_missing_or_blank(data.get(key)):
            return _malformed(f"{MARKER_NAME} missing or blank {key}")

    body_path = folder / BODY_NAME
    if not body_path.is_file():
        return _malformed(f"{BODY_NAME} missing")

    try:
        body_hash = sha256_file(body_path)
    except OSError:
        return _malformed(f"{BODY_NAME} unreadable")

    recorded = str(data["body_sha256"]).strip().lower()
    if recorded != body_hash:
        carried = _carried(folder, recorded)
        if carried is not None:
            return carried
        return ApprovalState(
            state="stale",
            reason="approval_marker_stale",
            detail=f"{MARKER_NAME} body_sha256 does not match {BODY_NAME}",
        )

    return ApprovalState(state="current", reason="", detail="")


def utc_now() -> str:
    """Current UTC time in the marker timestamp format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_files_atomically(files: list[tuple[Path, bytes]]) -> None:
    """Write every ``(path, data)`` through a temp file, then rename them in order.

    All temp files exist before the first rename, so a failure while writing
    leaves nothing behind; the marker goes last so it never exists without its
    snapshot.
    """
    staged: list[tuple[Path, Path]] = []
    try:
        for path, data in files:
            handle, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
            tmp = Path(name)
            staged.append((tmp, path))
            with os.fdopen(handle, "wb") as stream:
                stream.write(data)
        for tmp, path in staged:
            os.replace(tmp, path)
    finally:
        for tmp, _ in staged:
            tmp.unlink(missing_ok=True)


def record_approval(work_folder: Path, approved_by: str) -> Path:
    """Write ``approval.yml`` and ``approved-body.md`` from the current ``body.md``.

    Call it only for an explicit human approval of those exact bytes. Raises
    ``ValueError`` (writing nothing) for a blank name or a missing body.
    """
    folder = Path(work_folder)
    name = (approved_by or "").strip()
    if not name:
        raise ValueError("approved_by must name the approving human")
    body_path = folder / BODY_NAME
    if not body_path.is_file():
        raise ValueError(f"{BODY_NAME} missing in {folder}")
    data = body_path.read_bytes()
    marker = (
        f"schema: {MARKER_SCHEMA}\n"
        f"body_sha256: {hashlib.sha256(data).hexdigest()}\n"
        f"approved_at: {utc_now()}\n"
        f"approved_by: {json.dumps(name, ensure_ascii=False)}\n"
    )
    write_files_atomically(
        [(folder / SNAPSHOT_NAME, data), (folder / MARKER_NAME, marker.encode("utf-8"))]
    )
    return folder / MARKER_NAME


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record the human approval of body.md.")
    commands = parser.add_subparsers(dest="command", required=True)
    approve = commands.add_parser(
        "approve", help="write approval.yml and approved-body.md; only after an explicit human approval"
    )
    approve.add_argument("folder", type=Path)
    approve.add_argument("--by", required=True, help="the approving human's name")
    args = parser.parse_args(argv)
    try:
        marker = record_approval(args.folder, args.by)
    except ValueError as exc:
        print(f"approval not recorded: {exc}", file=sys.stderr)
        return 1
    print(f"recorded {marker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
