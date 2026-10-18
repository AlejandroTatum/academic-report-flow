#!/usr/bin/env python3
"""The final human review marker contract.

A final review is a file on disk, not a session variable: ``final-review.yml``
binds a human OK to the exact bytes of the final PDF through ``pdf_sha256``.
Two consumers share this predicate with different presentation: the delivery
gate in ``publish_validated_pdf`` maps it onto a user-facing abort message, and
``deliver_report`` names the missing evidence before delegating to that
publisher. Keeping the predicate here -- and the presentation at each boundary
-- is what stops the deliver entrypoint and the irreversible publisher from
disagreeing about whether the human saw the PDF that is about to ship.

A bounded edit made after the review keeps it: ``record_final_review`` writes
``reviewed-body.md`` (the ``body.md`` bytes the human reviewed) next to the
marker and binds them through ``body_sha256``. When the PDF was rebuilt, the
review is ``carried`` -- still valid -- only if ``validation.yml`` passes for the
CURRENT PDF (and declared bibliography), the snapshot hashes to ``body_sha256``,
and the diff from the snapshot to the current ``body.md`` is bounded (see
``bounded_edit``). Anything else is ``stale``, as before.

``final_review_state`` is pure and read-only: it never writes, never
creates a directory, and never raises for a bad marker (``record_final_review``
is the only writer, reached through the explicit-review CLI): an unreadable or
invalid marker is ``malformed`` data the caller can report, never a crash and
never something this module "repairs". Reviewed bytes that disappeared -- a
missing or rebuilt PDF -- are ``stale``: the human must review the current PDF
again, exactly as with approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from approval_marker import sha256_file, utc_now, write_files_atomically
from bounded_edit import bounded
from report_config import read_yaml

MARKER_NAME = "final-review.yml"
SNAPSHOT_NAME = "reviewed-body.md"
BODY_NAME = "body.md"
VALIDATION_NAME = "validation.yml"
MARKER_SCHEMA = "academic.doc-final-review/v1"
REQUIRED_KEYS = ("pdf_sha256", "reviewed_at", "reviewed_by")


@dataclass(frozen=True)
class FinalReviewState:
    """The final review marker as derived from disk.

    ``state`` is exactly one of ``current|carried|absent|stale|malformed``;
    ``reason`` is the bounded token ``"" | final_review_marker_absent |
    final_review_marker_stale | final_review_marker_malformed``; ``detail`` is a
    short ASCII description naming the offending file or key (for ``carried``,
    the size of the bounded edit). ``ok`` is the one question every gate asks:
    ``current`` and ``carried`` both mean the review holds.
    """

    state: str
    reason: str
    detail: str

    @property
    def ok(self) -> bool:
        return self.state in ("current", "carried")


def _malformed(detail: str) -> FinalReviewState:
    return FinalReviewState(
        state="malformed", reason="final_review_marker_malformed", detail=detail
    )


def _is_missing_or_blank(value: object) -> bool:
    """A required key must be present and carry visible text."""
    return value is None or not str(value).strip()


def _validation_passes(folder: Path, pdf_hash: str, bibliography: Path | None) -> bool:
    """True when ``validation.yml`` passes for exactly the current PDF (and bibliography)."""
    receipt = folder / VALIDATION_NAME
    try:
        data = read_yaml(receipt)
        if not isinstance(data, dict):
            return False
        if str(data.get("artifact_sha256") or "").strip().lower() != pdf_hash:
            return False
        if str(data.get("result") or "").strip().lower() != "pass":
            return False
        if bibliography is not None:
            recorded = str(data.get("bibliography_sha256") or "").strip().lower()
            return recorded == sha256_file(bibliography)
    except Exception:
        return False
    return True


def _carried(
    folder: Path, marker: dict, pdf_hash: str, bibliography: Path | None
) -> FinalReviewState | None:
    """``carried`` when a rebuilt, validated PDF follows a bounded edit of the reviewed body.

    The snapshot is trusted only when its bytes hash to the marker's
    ``body_sha256``; a marker without that key (a hand-written one) never carries.
    """
    recorded = str(marker.get("body_sha256") or "").strip().lower()
    if not recorded:
        return None
    snapshot = folder / SNAPSHOT_NAME
    try:
        if not snapshot.is_file() or sha256_file(snapshot) != recorded:
            return None
        old = snapshot.read_text(encoding="utf-8")
        new = (folder / BODY_NAME).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not _validation_passes(folder, pdf_hash, bibliography):
        return None
    is_bounded, words = bounded(old, new)
    if not is_bounded:
        return None
    return FinalReviewState(
        state="carried", reason="", detail=f"bounded edit since final review ({words} words)"
    )


def final_review_state(
    report_dir: Path, pdf_path: Path, *, bibliography: Path | None = None
) -> FinalReviewState:
    """Derive the final review state of ``pdf_path`` without touching disk.

    When ``bibliography`` is given (the report declared its `.bib` a final
    deliverable), the marker must also bind those exact bytes through
    ``bibliography_sha256``: a pdf-only marker is ``malformed`` and a marker
    bound to other bibliography bytes is ``stale``. Without the argument the
    predicate is exactly the PDF-only contract it always was.
    """
    folder = Path(report_dir)
    pdf = Path(pdf_path)
    marker_path = folder / MARKER_NAME

    if not marker_path.is_file():
        return FinalReviewState(
            state="absent",
            reason="final_review_marker_absent",
            detail=f"{MARKER_NAME} missing",
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

    if bibliography is not None:
        if _is_missing_or_blank(data.get("bibliography_sha256")):
            return _malformed(f"{MARKER_NAME} missing or blank bibliography_sha256")
        if not bibliography.is_file():
            return FinalReviewState(
                state="stale",
                reason="final_review_marker_stale",
                detail=f"{MARKER_NAME} bibliography_sha256 does not match {bibliography.name}",
            )
        try:
            bib_hash = sha256_file(bibliography)
        except OSError:
            return FinalReviewState(
                state="stale",
                reason="final_review_marker_stale",
                detail=f"{MARKER_NAME} bibliography_sha256 does not match {bibliography.name}",
            )
        if str(data["bibliography_sha256"]).strip().lower() != bib_hash:
            return FinalReviewState(
                state="stale",
                reason="final_review_marker_stale",
                detail=f"{MARKER_NAME} bibliography_sha256 does not match {bibliography.name}",
            )

    if not pdf.is_file():
        return FinalReviewState(
            state="stale",
            reason="final_review_marker_stale",
            detail=f"final PDF {pdf.name} missing",
        )

    try:
        pdf_hash = sha256_file(pdf)
    except OSError:
        return FinalReviewState(
            state="stale",
            reason="final_review_marker_stale",
            detail=f"final PDF {pdf.name} unreadable",
        )

    if str(data["pdf_sha256"]).strip().lower() != pdf_hash:
        carried = _carried(folder, data, pdf_hash, bibliography)
        if carried is not None:
            return carried
        return FinalReviewState(
            state="stale",
            reason="final_review_marker_stale",
            detail=f"{MARKER_NAME} pdf_sha256 does not match {pdf.name}",
        )

    return FinalReviewState(state="current", reason="", detail="")


def record_final_review(
    work_folder: Path, reviewed_by: str, pdf_path: Path, *, bibliography: Path | None = None
) -> Path:
    """Write ``final-review.yml`` and ``reviewed-body.md`` for the PDF being reviewed.

    Call it only for an explicit human OK of those exact bytes. Raises
    ``ValueError`` (writing nothing) for a blank name, a missing PDF, a missing
    ``body.md`` or a declared bibliography that is not a file.
    """
    folder = Path(work_folder)
    pdf = Path(pdf_path)
    name = (reviewed_by or "").strip()
    if not name:
        raise ValueError("reviewed_by must name the reviewing human")
    if not pdf.is_file():
        raise ValueError(f"final PDF {pdf} missing")
    body_path = folder / BODY_NAME
    if not body_path.is_file():
        raise ValueError(f"{BODY_NAME} missing in {folder}")
    if bibliography is not None and not Path(bibliography).is_file():
        raise ValueError(f"declared bibliography {bibliography} missing")
    body = body_path.read_bytes()
    lines = [
        f"schema: {MARKER_SCHEMA}",
        f"pdf_sha256: {sha256_file(pdf)}",
    ]
    if bibliography is not None:
        lines.append(f"bibliography_sha256: {sha256_file(Path(bibliography))}")
    lines += [
        f"body_sha256: {hashlib.sha256(body).hexdigest()}",
        f"reviewed_at: {utc_now()}",
        f"reviewed_by: {json.dumps(name, ensure_ascii=False)}",
    ]
    write_files_atomically(
        [
            (folder / SNAPSHOT_NAME, body),
            (folder / MARKER_NAME, ("\n".join(lines) + "\n").encode("utf-8")),
        ]
    )
    return folder / MARKER_NAME


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record the human final review of the final PDF.")
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser(
        "record", help="write final-review.yml and reviewed-body.md; only after an explicit human OK"
    )
    record.add_argument("folder", type=Path)
    record.add_argument("--by", required=True, help="the reviewing human's name")
    args = parser.parse_args(argv)
    try:
        from report_config import load_report_config

        config = load_report_config(args.folder)
        marker = record_final_review(
            args.folder, args.by, config.pdf_path, bibliography=config.delivery_bibliography()
        )
    except (ValueError, KeyError, OSError) as exc:
        print(f"final review not recorded: {exc}", file=sys.stderr)
        return 1
    print(f"recorded {marker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
