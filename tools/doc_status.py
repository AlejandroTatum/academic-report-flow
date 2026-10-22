#!/usr/bin/env python3
"""Derive the academic-report-flow phases from on-disk artifacts (read-only).

Slice 2c-i of the status layer: the phase vocabulary, the two value dataclasses,
the eleven per-phase derivations, and the ``derive``/``main`` composition on top
of them. Each ``_phase_*`` function answers for exactly one phase and returns a raw
``done|pending|blocked`` token; ``derive`` runs them in order, wraps an unexpected
exception as ``blocked``, locks every phase after the first incomplete one to
``pending``, and projects the route (``current``/``next``/``gate``). ``render_human``
and ``render_machine`` project that value: the portable human block and the
``academic.doc-status/v1`` markdown shape. ``main`` renders both on every invocation.

Approval delegates to ``approval_marker.approval_state`` -- the same predicate
``publish_validated_pdf`` enforces -- so routing and the irreversible publisher
cannot disagree about which marker is current. The plan, verify and review
phases delegate to ``rubric_plan.rubric_state``, ``content_check.content_check_state``
and ``final_review_marker.final_review_state`` for the same reason.

The module is pure and read-only. ``_phase_intake`` builds ``ReportConfig``
directly instead of calling ``load_report_config``, which raises ``SystemExit``
on an unknown route -- a status tool reports what it finds, it never exits.
"""
from __future__ import annotations

import json
import os
import shlex
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import content_check
import final_review_marker
import rubric_plan
import typeset
from guide_facts import load_guide_facts
from course_profile import COURSE_LAYOUT, PRACTICE_FORMATS, course_repo
from approval_marker import approval_state, bound_file_names, draft_is_fresh, render_settings_unchanged, sha256_file
from publish_pdf import PublicationError, matching_delivered_version, scan_delivery_versions
from report_config import (
    ROOT,
    DEFAULT_STUDENT,
    ReportConfig,
    is_placeholder_value,
    read_yaml,
    versioned_pdf_pattern,
)
from evidence_contract import evidence_gate_engaged, load_evidence_package, validate_evidence_package
from source_count import MIN_ACADEMIC_SOURCES, effective_min_sources, source_gate
from structure_contract import structure_confirmation_state, structure_gate_engaged

# new-report-flow T5: the content-first route. The preview phase is gone (the
# draft is the only thing the user reviews); plan, verify, format and review
# sit between the phases that existed before.
PHASES = (
    "intake",
    "research",
    "plan",
    "draft",
    # verify-concise-drafts T8: verify runs before approval, so one approval
    # packet carries the preview, the requirement matrix and the missing items.
    "verify",
    "approval",
    "format",
    # issue #96: the approved body.md is plain text; it is formatted in
    # body.typeset.md before the final build.
    "typeset",
    "generate",
    "validate",
    "review",
    "deliver",
)
DONE, CURRENT, PENDING, BLOCKED = "done", "current", "pending", "blocked"
STATE_TOKENS = (DONE, CURRENT, PENDING, BLOCKED)
SCHEMA_NAME = "academic.doc-status"
SCHEMA_VERSION = 1

# One action sentence per phase: the closing ``**Next**`` line for the routed token,
# and the front-loaded gate's consequence for the phase that still waits. Every
# sentence names the absolute path it acts on -- the work folder exactly as the
# caller passed it, and for the tool phases a complete, shell-quoted command built
# from this interpreter and this code root's entrypoint -- so a fresh session can
# paste the printed command from any working directory and have it run.
_GUIDANCE = {
    "intake": "complete {report_yml}, then re-run doc_status",
    "research": (
        "write at least {min_sources} book or paper sources to {sources}, "
        "then re-run doc_status"
    ),
    "plan": "record the teacher's rubric in {rubric}, then re-run doc_status",
    "draft": "draft {body}, then re-run doc_status",
    "approval": (
        "before asking, build a preview PDF with {build_command} --no-approval-check for content "
        "review: the draft is plain text, so layout findings it prints are not fixed in {body}; "
        "formatting is applied in body.typeset.md after approval and the layout is audited after "
        "typeset and generate, in validate; the message right before "
        "the prompt lists clickable Markdown links with absolute file:// URLs to the draft PDF "
        "({pdf}) and {body}: print it with {packet_command} --open (it also opens the fresh draft PDF "
        "for the user) and paste that approval packet "
        "(links, per-criterion summary, missing items) unchanged; "
        "the preview is never the final artifact; "
        "generation runs only after you approve {body}"
    ),
    "verify": (
        "launch ONE independent verifier for {rubric} with the brief from {check_command} "
        "--verify-brief (add --verify-brief --since verification.yml when it exists, so only "
        "changed sections are re-checked), save its matrix as verification.yml; run {check_command} "
        "--verification verification.yml, then re-run doc_status"
    ),
    "format": (
        "the format answers normally arrive with the approval batch; ask only the missing "
        "fields named by doc_status, never re-ask what {report_yml} records: use ask_user_choice "
        "for APE, AA, ACD or libre, PDF or DOCX, and each remaining metadata gap with suggested "
        "options (never free text); decide group work and members here; "
        "record the answer in {report_yml}, then re-run doc_status"
    ),
    "typeset": (
        "run {typeset_bind_command} (it copies the approved {body} to {typeset_body} when missing "
        "and binds it), apply the backend formatting there and never in {body}: formulas as math, "
        "data as tables, `Figura:` lines as `![caption](path)`, bare URLs as `<url>`, the format's "
        "fixed headings; keep every word and [@key] of {body}; run {typeset_check_command} until it "
        "passes, then re-run doc_status"
    ),
    "generate": "build with {build_command}, then re-run doc_status",
    "validate": "record {validation} for the final PDF, then re-run doc_status",
    "review": (
        "ask the user to review {pdf}, then record {final_review}, "
        "then re-run doc_status"
    ),
    "deliver": "publish with {deliver_command}, then re-run doc_status",
}


@dataclass(frozen=True)
class PhaseState:
    """One phase of the route: a ``done|pending|blocked`` token plus its evidence."""

    name: str
    state: str
    detail: str = ""
    blocked_reason: str = ""


@dataclass(frozen=True)
class DocStatus:
    """The whole route derived once from disk, ready to render or serialize."""

    work_folder: Path
    phases: tuple[PhaseState, ...]
    current: str
    next_token: str
    gate: str
    blocked_reasons: tuple[str, ...]


def _read_text(path: Path) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def _phase_intake(folder: Path, config: ReportConfig, _documents_root: Path | None) -> PhaseState:
    """Intake is identity, not the whole route metadata (new-report-flow T5).

    ``report.yml`` must exist, the route must be known, a declared ``format:``
    must be one the format table recognises, and the report must be identified:
    ``title`` and ``student`` present and real (not bracket templates or X/0
    fill-in marks). Subject/teacher and the format-specific fields belong to
    the format phase. A report that engaged the structure flow still needs it
    confirmed here, exactly as before.
    """
    if not (folder / "report.yml").is_file():
        return PhaseState("intake", PENDING, "report.yml missing")
    if not config.route_is_known:
        return PhaseState("intake", BLOCKED, f"route={config.route} not recognized", "unknown_route")
    if config.format is not None and not config.format_is_known:
        return PhaseState(
            "intake", BLOCKED, f"format={config.format} not recognized", "unknown_format"
        )
    if config.format_hint is not None and not config.format_hint_is_known:
        return PhaseState("intake", BLOCKED, f"format_hint={config.format_hint} not recognized", "unknown_format_hint")
    missing = [key for key in ("title", "student") if not config.metadata.get(key)]
    if missing:
        return PhaseState("intake", PENDING, f"missing metadata: {', '.join(missing)}")
    placeholders = [
        key for key in ("title", "student") if is_placeholder_value(config.metadata.get(key))
    ]
    if placeholders:
        return PhaseState("intake", PENDING, f"placeholder metadata: {', '.join(placeholders)}")
    # #12: once a report engages the structure flow (declares `structure:`
    # at all), intake stays incomplete until that contract reports
    # confirmed. A report that never engaged the flow is untouched -- the
    # existing behaviour every report before this feature relied on.
    if structure_gate_engaged(config.raw):
        state, detail = structure_confirmation_state(config)
        if state != "confirmed":
            return PhaseState("intake", PENDING, f"structure {state}: {detail}")
    return PhaseState("intake", DONE, f"route={config.route}, title and student recorded")


def _phase_research(folder: Path, config: ReportConfig, _documents_root: Path | None) -> PhaseState:
    # new-report-flow T2: research is a hard source gate. The phase is done
    # only when the report's own BibTeX file carries at least
    # MIN_ACADEMIC_SOURCES eligible book-or-paper entries; a recorded
    # `research: skipped` in report.yml and a non-empty evidence-matrix.md no
    # longer satisfy it. #11 still applies: once research/evidence.yml
    # exists at all, it must validate structurally on top of the source
    # gate -- unsupported, conflicting, or insufficient claims (R12) block
    # this phase exactly like any other final-gate failure.
    engaged = evidence_gate_engaged(folder)
    if engaged:
        package = load_evidence_package(folder) or {}
        result = validate_evidence_package(package)
        if result.errors:
            return PhaseState(
                "research", PENDING, "evidence.yml invalid: " + "; ".join(result.errors)
            )
    sources = source_gate(folder, config)
    if not sources.ok:
        detail = sources.reason
        if str(config.raw.get("research") or "").strip().lower() == "skipped":
            detail += " (research: skipped is no longer accepted)"
        return PhaseState("research", PENDING, detail)
    if engaged:
        return PhaseState("research", DONE, "research/evidence.yml validated")
    return PhaseState("research", DONE, sources.reason)


def _phase_plan(folder: Path, _config: ReportConfig, _documents_root: Path | None) -> PhaseState:
    """Map the rubric-plan predicate onto one phase state (new-report-flow T3).

    A valid ``rubric.yml`` is the plan artifact; an absent one is ordinary
    progress and a malformed one -- unparsable or schema-invalid -- is
    ``blocked`` data the plan phase must fix. The rubric is never written or
    repaired here.
    """
    state = rubric_plan.rubric_state(folder)
    if state == "valid":
        criteria = rubric_plan.load_rubric(folder)
        count = len(criteria)
        noun = "criterion" if count == 1 else "criteria"
        checked = rubric_plan.count_checked_criteria(criteria)
        return PhaseState("plan", DONE, f"rubric.yml valid ({count} {noun}, {checked} with checks)")
    if state == "absent":
        return PhaseState("plan", PENDING, "rubric.yml missing")
    return PhaseState("plan", BLOCKED, "rubric.yml malformed", "rubric_malformed")


def _phase_draft(folder: Path, _config: ReportConfig, _documents_root: Path | None) -> PhaseState:
    body = folder / "body.md"
    if not body.is_file():
        return PhaseState("draft", PENDING, "body.md missing")
    text = _read_text(body)
    if text is None:
        return PhaseState("draft", BLOCKED, "body.md unreadable", "draft_unreadable")
    if not text.strip():
        return PhaseState("draft", PENDING, "body.md empty")
    # Tools enforce the quality rules before the human decision: while the same
    # body check `content_check.py --body-check` runs would fail, approval is
    # not offered. A current approval marker is never re-gated (the user already
    # approved those exact bytes). A carried approval is not exempt: its bytes
    # changed, and the body check still runs after every edit.
    if approval_state(folder).state != "current":
        try:
            failed = [c for c in content_check.body_check_results(folder) if not c["ok"]]
        except (OSError, ValueError, TypeError) as exc:
            return PhaseState("draft", PENDING, f"body check could not run: {exc}", "body_check_failed")
        if failed:
            return PhaseState(
                "draft",
                PENDING,
                "body check fails: " + "; ".join(f"{c['check']}: {c['detail']}" for c in failed),
                "body_check_failed",
            )
    return PhaseState("draft", DONE, "body.md present and passes the body check")


def _phase_approval(folder: Path, _config: ReportConfig, _documents_root: Path | None) -> PhaseState:
    """Map the shared approval predicate onto one phase state.

    ``current`` and ``carried`` (a bounded edit since approval) are ``done``: an
    absent marker stays ``pending`` so the route waits at approval, and a stale marker -- the body changed since approval --
    also returns to ``pending``, because editing after approval is the normal
    review loop, not a deadlock. Only a malformed marker is ``blocked``, with the
    predicate's own bounded reason. The marker is never written here.
    """
    state = approval_state(folder)
    if state.state == "current":
        bound = " and ".join(bound_file_names())
        return PhaseState("approval", DONE, f"approval.yml matches {bound}")
    if state.state == "carried":
        return PhaseState("approval", DONE, state.detail)
    if state.state == "absent":
        return PhaseState("approval", PENDING, state.detail)
    if state.state == "stale":
        return PhaseState(
            "approval",
            PENDING,
            f"{state.detail}; the body changed since approval, re-approve",
        )
    return PhaseState("approval", BLOCKED, state.detail, state.reason)


def _phase_verify(folder: Path, _config: ReportConfig, _documents_root: Path | None) -> PhaseState:
    """Map the content-check predicate onto one phase state (new-report-flow T3/T5).

    ``pass`` is ``done``; absent and stale (the draft, the rubric or the bib
    changed since the check) are ordinary progress -- the check simply reruns.
    A recorded fail is ``blocked`` with ``content_check_failed``: the findings
    must be fixed through the user's edit orders, never silently polished. A
    malformed marker is ``blocked`` too. The check is never run or repaired
    here; ``content_check_state`` already re-derives the verdict, so a forged
    pass cannot clear this phase.
    """
    state = content_check.content_check_state(folder)
    if state == "pass":
        return PhaseState("verify", DONE, "content-check.yml passes for the current draft")
    if state == "absent":
        return PhaseState("verify", PENDING, "content-check.yml missing")
    if state == "stale":
        return PhaseState(
            "verify",
            PENDING,
            "content-check.yml is stale: inputs changed or legacy marker; re-run the verifier",
            "content_check_stale",
        )
    if state == "fail":
        return PhaseState(
            "verify",
            BLOCKED,
            "content check failed: findings must be fixed through the user's edit orders",
            "content_check_failed",
        )
    return PhaseState("verify", BLOCKED, "content-check.yml malformed", "content_check_malformed")


def _has_legacy_pdf(folder: Path, config: ReportConfig, documents_root: Path | None) -> bool:
    """A report from before explicit ``output:`` answers: its PDF already exists
    and was validated or delivered, so it is treated as ``output: pdf``. A merely
    generated PDF (possibly another folder's) never waives the answer."""
    if not config.pdf_path.is_file():
        return False
    if (folder / "validation.yml").is_file():
        return True
    return _phase_deliver(folder, config, documents_root).state == DONE


def _has_final_build(folder: Path, config: ReportConfig) -> bool:
    """True when the PDF at ``pdf_path`` is a final build, not a draft preview.

    The preview (``--no-approval-check``) writes the same path and always
    predates ``approval.yml``; a final build never does. A PDF from a report
    without an approval marker (legacy) counts as built, and an equal mtime
    counts as final, as in ``_phase_generate``. Rewriting ``approval.yml`` after
    a final build turns that PDF back into a preview on purpose: generate needs
    a rebuild then anyway, and format waits for ``delivery_dir`` until it does.
    """
    pdf = config.pdf_path
    if not pdf.is_file():
        return False
    marker = folder / "approval.yml"
    return not marker.is_file() or pdf.stat().st_mtime >= marker.stat().st_mtime


# The approval batch carries the format questions only while report.yml still
# lacks them (#80): format answers are plain report.yml data, recorded as soon as
# they are given, so a request for changes reopens only the body approval.
_APPROVAL_FORMAT_BATCH = (
    "; in the same batch use ask_user_choice "
    "(suggested options, never free text) for the document format APE, AA, ACD or libre (libre also "
    "needs format_spec: options 'documento sobrio sin portada' or 'con portada'), the "
    "delivery format PDF or DOCX, and any metadata that format still needs; never infer "
    "an answer, no defaults"
)
_APPROVAL_RECORD_ANSWERS = (
    "; record each format answer in {report_yml} as soon as it is given, even when the user "
    "requests changes; only approval.yml waits for an explicit approve"
)
_APPROVAL_FORMAT_RECORDED = (
    "; the format answers are already recorded in {report_yml}: ask only whether the user "
    "approves {body}, never re-ask format, output, delivery folder or metadata"
)


def _approval_format_suffix(folder: Path, config: ReportConfig, documents_root: Path | None) -> str:
    """What the approval batch still asks about the format, from ``report.yml`` alone."""
    if config.format is None:
        return _APPROVAL_FORMAT_BATCH + _APPROVAL_RECORD_ANSWERS
    state = _phase_format(folder, config, documents_root)
    if state.state == BLOCKED:
        return _approval_only_with(state.detail)
    # The gate always precedes approval, so whatever PDF exists is a preview:
    # the folder checks run as before a build.
    gaps = _missing_format_fields(folder, config, documents_root)
    if not gaps and _course_folder_missing(config, documents_root, before_build=True):
        gaps = ["delivery folder (record metadata.unit, metadata.practice_number and metadata.topic, "
                "then run course_profile.py)"]
    if not gaps:
        problem = _delivery_folder_problem(config, documents_root, before_build=True)
        return _approval_only_with(f"delivery folder unusable: {problem}") if problem else _APPROVAL_FORMAT_RECORDED
    return (
        "; in the same batch use ask_user_choice (suggested options, never free text) only for "
        f"what {{report_yml}} still lacks, never re-asking what it records; still missing: {', '.join(gaps)}"
        + _APPROVAL_RECORD_ANSWERS
    )


def _approval_only_with(reason: str) -> str:
    """Approve now; a problem the user does not answer as a field is reported by format."""
    escaped = reason.replace("{", "{{").replace("}", "}}")
    return _APPROVAL_FORMAT_RECORDED + f"; the format phase still reports: {escaped}"


def _missing_format_fields(folder: Path, config: ReportConfig, documents_root: Path | None) -> list[str]:
    """The ``report.yml`` keys a known format still needs, in the order they are asked."""
    missing = [
        key
        for key in config.format_required_metadata
        if not config.metadata.get(key) or is_placeholder_value(config.metadata.get(key))
    ]
    if config.format == "libre" and not config.format_spec:
        missing.append("format_spec")
    output = str(config.raw.get("output") or "").strip()
    if not output and not _has_legacy_pdf(folder, config, documents_root):
        missing.append("output")
    return missing


def _phase_format(folder: Path, config: ReportConfig, documents_root: Path | None) -> PhaseState:
    """Map the chosen format and its metadata onto one phase state (T4/T5).

    The answers normally arrive with the approval batch (task 9.1), so this is a
    completeness check: an absent ``format:`` is ordinary progress (ask APE, AA, ACD
    or libre). A chosen format needs its required metadata present and
    placeholder-free, ``libre`` a ``format_spec:``, and every format an explicit
    ``output:`` (PDF or DOCX has no default, except for a legacy report whose PDF is
    already validated or delivered) -- an incomplete choice stays
    ``pending`` with only the missing keys named. An unrecognised format or ``output:``
    value is ``blocked`` and named (intake already blocks the format; this handler stays defensive).
    """
    chosen = config.format
    if chosen is None:
        return PhaseState("format", PENDING, "format not chosen: ask the user APE, AA, ACD or libre")
    if not config.format_is_known:
        return PhaseState("format", BLOCKED, f"format={chosen} not recognized", "unknown_format")
    output = str(config.raw.get("output") or "").strip()
    if output and output.lower() not in ("pdf", "docx"):
        return PhaseState(
            "format", BLOCKED, f"output={output} not recognized: use pdf or docx", "unknown_output"
        )
    missing = _missing_format_fields(folder, config, documents_root)
    legacy_pdf = not output and "output" not in missing
    if missing:
        return PhaseState("format", PENDING, f"missing format metadata: {', '.join(missing)}")
    if legacy_pdf:
        return PhaseState("format", DONE, f"format={chosen}, output pdf (legacy report), metadata complete")
    missing_folder = _course_folder_missing(config, documents_root)
    if missing_folder:
        return PhaseState("format", PENDING, missing_folder)
    problem = _delivery_folder_problem(config, documents_root)
    if problem:
        return PhaseState("format", PENDING, f"delivery folder unusable: {problem}")
    return PhaseState("format", DONE, f"format={chosen}, output and metadata complete")


def _course_folder_missing(config: ReportConfig, documents_root: Path | None, *, before_build: bool = False) -> str:
    """Why format waits for ``delivery_dir``, or ``""`` when it does not.

    A course repo fixes where the practice lands; recording it before the
    final build avoids moving (and re-approving) the PDF after review.
    Reports with a final build keep their status.
    """
    if config.format not in PRACTICE_FORMATS or "delivery_dir" in config.raw:
        return ""
    if not before_build and _has_final_build(config.folder, config):
        return ""
    repo = course_repo(config, documents_root)
    if repo is None:
        return ""
    return (
        f"delivery_dir not set: course repo {repo} uses {COURSE_LAYOUT}; record "
        "metadata.unit, metadata.practice_number and metadata.topic, then run course_profile.py, "
        "or set delivery_dir by hand"
    )


def _delivery_folder_problem(config: ReportConfig, documents_root: Path | None, *, before_build: bool = False) -> str:
    """The publisher's refusal for the delivery folder, checked before the build (#83).

    Same scan ``deliver_report.py`` runs, so a folder holding anything but
    ``<slug>-vNNN.pdf`` (and paired ``.bib``) is reported while the user can
    still choose another folder, not after the final review. A report with a
    final build is never re-gated here: deliver still refuses the folder. An
    unresolvable identity is the deliver phase's to report; an unreadable path
    (a file, no permission) is a reason, never a crash.
    """
    if not before_build and _has_final_build(config.folder, config):
        return ""
    try:
        delivery = config.delivery_folder(documents_root)
        slug = config.document_slug
    except (KeyError, ValueError):
        return ""
    try:
        scan_delivery_versions(delivery, slug)
    except PublicationError as exc:
        return str(exc)
    except OSError as exc:
        return f"{delivery} is not a readable folder ({exc.strerror or exc})"
    return ""


def _phase_typeset(folder: Path, _config: ReportConfig, _documents_root: Path | None) -> PhaseState:
    """Report whether the approved plain-text body has a current formatted copy (issue #96).

    An approval recorded before the typeset phase (no ``typeset: required``)
    renders ``body.md`` as before and is ``done``, unless a typeset body is
    bound anyway: the build renders it, so it is checked (issue #98). Otherwise ``done`` needs
    every ``typeset.check_results`` entry to pass; anything else is ordinary
    progress (``pending``) with the failing checks named. Read-only.
    """
    if not typeset.typeset_in_use(folder):
        return PhaseState("typeset", DONE, "legacy approval: body.md renders as is (no typeset required)")
    results = typeset.check_results(folder)
    failed = [item for item in results if not item["ok"]]
    if not failed:
        return PhaseState("typeset", DONE, "body.typeset.md formats the approved body.md and passes the checks")
    if len(results) == 1:
        return PhaseState("typeset", PENDING, failed[0]["detail"])
    return PhaseState(
        "typeset", PENDING, "typeset check fails: " + "; ".join(f"{i['check']}: {i['detail']}" for i in failed)
    )


def _phase_generate(folder: Path, config: ReportConfig, _documents_root: Path | None) -> PhaseState:
    """Report whether the final PDF is the one the markers authorized.

    Bounded to the mtime comparisons the design specifies (new-report-flow T5):
    the artifact is ``done`` when ``config.pdf_path`` exists and is not older
    than ``approval.yml`` AND not older than ``report.yml`` -- changing the
    format after a build requires a rebuild. The one exception is a change to
    delivery-only keys (``delivery_dir``, ``deliver_bibliography``): when the
    build's render record still matches report.yml, the PDF is unchanged and
    stays current. A missing PDF, a missing marker,
    or a PDF that predates either file is ordinary progress -- generate is
    never ``blocked``; a stale build simply has to be redone. Timestamps and
    the render record are read; nothing is written or repaired here.
    """
    pdf = config.pdf_path
    if not pdf.is_file():
        return PhaseState("generate", PENDING, "final PDF missing")
    marker = folder / "approval.yml"
    report_yml = folder / "report.yml"
    if not marker.is_file():
        return PhaseState("generate", PENDING, "approval.yml missing")
    if not report_yml.is_file():
        return PhaseState("generate", PENDING, "report.yml missing")
    if pdf.stat().st_mtime < report_yml.stat().st_mtime and not render_settings_unchanged(folder):
        return PhaseState("generate", PENDING, f"final PDF {pdf.name} older than report.yml")
    # A carried approval keeps the gate but not the build: the marker predates
    # the bounded edit, so the PDF must also postdate body.md.
    body = folder / "body.md"
    if approval_state(folder).state == "carried" and pdf.stat().st_mtime < body.stat().st_mtime:
        return PhaseState("generate", PENDING, f"final PDF {pdf.name} older than body.md")
    typeset_body = folder / "body.typeset.md"
    if typeset.typeset_in_use(folder) and typeset_body.is_file() and pdf.stat().st_mtime < typeset_body.stat().st_mtime:
        return PhaseState("generate", PENDING, f"final PDF {pdf.name} older than body.typeset.md")
    if pdf.stat().st_mtime >= marker.stat().st_mtime:
        return PhaseState("generate", DONE, f"final PDF {pdf.name} is not older than approval.yml")
    return PhaseState("generate", PENDING, f"final PDF {pdf.name} older than approval.yml")


def _phase_validate(folder: Path, config: ReportConfig, _documents_root: Path | None) -> PhaseState:
    """Map the validation receipt onto one phase state.

    ``done`` requires both halves of the design's predicate: the receipt records
    ``result: pass`` and its ``artifact_sha256`` equals the final PDF's bytes.
    Receipt identity is checked before the recorded outcome: a receipt bound to
    other bytes is stale evidence -- a stale ``result: fail`` included -- and
    returns to ``pending`` so the new build can revalidate. Only a fail bound to
    the current bytes is the ``blocked`` ``validation_failed`` outcome. The
    receipt is never written or repaired here.
    """
    receipt = folder / "validation.yml"
    if not receipt.is_file():
        return PhaseState("validate", PENDING, "validation.yml missing")
    try:
        data = read_yaml(receipt)
    except Exception:
        return PhaseState("validate", PENDING, "validation.yml unreadable")
    pdf = config.pdf_path
    if not pdf.is_file():
        return PhaseState("validate", PENDING, "final PDF missing")
    try:
        artifact_hash = sha256_file(pdf)
    except OSError:
        return PhaseState("validate", PENDING, "final PDF unreadable")
    # Identity before outcome: a receipt that does not bind to the current PDF
    # bytes describes a superseded build, so its recorded result (fail included)
    # is stale evidence and validation simply reruns against the new bytes.
    if str(data.get("artifact_sha256") or "").strip().lower() != artifact_hash:
        return PhaseState("validate", PENDING, "validation.yml artifact_sha256 does not match final PDF")
    result = str(data.get("result") or "").strip().lower()
    if result == "fail":
        return PhaseState("validate", BLOCKED, "validation.yml recorded result: fail", "validation_failed")
    if result != "pass":
        return PhaseState("validate", PENDING, "validation.yml result is not pass")
    # course-deliverables T2: when the bibliography is a declared deliverable,
    # the receipt must bind its exact bytes, exactly like the PDF hash. The
    # declared source itself is refused here as pending evidence, never invented.
    if config.deliver_bibliography:
        try:
            bib = config.delivery_bibliography()
        except ValueError as exc:
            return PhaseState("validate", PENDING, str(exc))
        recorded_bib = str(data.get("bibliography_sha256") or "").strip().lower()
        if not recorded_bib:
            return PhaseState(
                "validate", PENDING,
                "validation.yml missing bibliography_sha256 for the declared bibliography",
            )
        try:
            bib_hash = sha256_file(bib)
        except OSError:
            return PhaseState("validate", PENDING, "declared bibliography unreadable")
        if recorded_bib != bib_hash:
            return PhaseState(
                "validate", PENDING,
                f"validation.yml bibliography_sha256 does not match {bib.name}",
            )
    return PhaseState("validate", DONE, f"validation.yml passes for {pdf.name}")


def _phase_review(folder: Path, config: ReportConfig, _documents_root: Path | None) -> PhaseState:
    """Map the final-review predicate onto one phase state (new-report-flow T1/T5).

    ``current`` and ``carried`` (a bounded edit since the review, with a passing
    validation of the current PDF) are ``done``: an absent marker stays
    ``pending`` so the route waits at review, and a stale one -- the PDF changed since the human
    looked at it -- also returns to ``pending``, because reviewing the current
    build is the normal loop. Only a malformed marker is ``blocked``, with the
    predicate's own bounded reason. The marker is never written here. When the
    bibliography is a declared deliverable, the predicate binds its bytes too,
    exactly like the publisher's gate.
    """
    try:
        bibliography = config.delivery_bibliography()
    except ValueError as exc:
        return PhaseState("review", PENDING, str(exc))
    state = final_review_marker.final_review_state(folder, config.pdf_path, bibliography=bibliography)
    if state.state == "current":
        return PhaseState("review", DONE, f"final-review.yml matches {config.pdf_path.name}")
    if state.state == "carried":
        return PhaseState("review", DONE, state.detail)
    if state.state in ("absent", "stale"):
        return PhaseState("review", PENDING, state.detail)
    return PhaseState("review", BLOCKED, state.detail, state.reason)


def _phase_deliver(folder: Path, config: ReportConfig, documents_root: Path | None) -> PhaseState:
    """Report whether the final set is already delivered to Documents.

    ``done`` when the report's shared delivery folder (``config.delivery_folder``
    -- the exact folder the publisher writes, with the academic route scoped by
    the confirmed subject slug) holds a version whose complete artifact set
    matches the request through the publisher's own matcher: PDF bytes, plus
    the declared bibliography's bytes when ``deliver_bibliography`` is set, or
    the absence of a sibling ``.bib`` for a PDF-only request. ``pending``
    otherwise. Delivery is never ``blocked``: the design gives it no failure
    state, so an absent copy -- or one made from other bytes -- is ordinary
    progress, not an abort.
    """
    pdf = config.pdf_path
    if not pdf.is_file():
        return PhaseState("deliver", PENDING, "final PDF missing")
    try:
        delivery = config.delivery_folder(documents_root)
        slug = config.document_slug
        bibliography = config.delivery_bibliography()
    except (KeyError, ValueError):
        return PhaseState("deliver", PENDING, "publication identity unavailable")
    if not delivery.is_dir():
        return PhaseState("deliver", PENDING, f"no published {slug}-vNNN.pdf")
    try:
        source_hash = sha256_file(pdf)
        bib_hash = sha256_file(bibliography) if bibliography is not None else None
    except OSError:
        return PhaseState("deliver", PENDING, "final PDF or declared bibliography unreadable")
    try:
        matched = matching_delivered_version(delivery, slug, source_hash, bib_hash)
    except (PublicationError, OSError) as exc:
        return PhaseState("deliver", PENDING, f"delivery folder unusable: {exc}")
    if matched is not None:
        return PhaseState("deliver", DONE, f"{matched.name} published and hash-matched")
    return PhaseState("deliver", PENDING, f"no published {slug}-vNNN.pdf matches the final PDF")


def derive(folder: Path, *, documents_root: Path | None = None) -> DocStatus:
    """Compose every phase derivation into one route projection.

    The handlers run in ``PHASES`` order and each one is wrapped: an unexpected
    exception becomes that phase's ``blocked`` state with a ``derivation_error``
    reason, so a status call never crashes and never claims a phase ``done`` by
    accident. Once a phase is not ``done`` the route locks: every later phase is
    reported ``pending`` regardless of the artifacts on disk, because nothing
    downstream has been authorized. The first incomplete phase becomes
    ``current`` and is also the ``next`` token; an all-done route reports
    ``done``. The whole derivation is read-only. The work folder is resolved once,
    so the rendered guidance carries an absolute path even when the caller passed a
    relative one.
    """
    folder = Path(folder).resolve()
    config = ReportConfig(folder=folder, raw=read_yaml(folder / "report.yml"))
    handlers = (
        _phase_intake,
        _phase_research,
        _phase_plan,
        _phase_draft,
        _phase_verify,
        _phase_approval,
        _phase_format,
        _phase_typeset,
        _phase_generate,
        _phase_validate,
        _phase_review,
        _phase_deliver,
    )
    phases: list[PhaseState] = []
    locked = False
    for name, handler in zip(PHASES, handlers):
        try:
            phase = handler(folder, config, documents_root)
        except Exception as exc:  # one phase must never abort the whole status
            phase = PhaseState(name, BLOCKED, f"derivation error: {exc}", "derivation_error")
        if locked:
            phase = PhaseState(name, PENDING, "waiting for an earlier phase")
        elif phase.state != DONE:
            locked = True
        phases.append(phase)

    focus = next((phase for phase in phases if phase.state != DONE), None)
    if focus is None:
        current, next_token, gate = DONE, DONE, ""
    else:
        current = next_token = focus.name
        # The one authoritative gate: the actual focus phase, its pre-projection
        # token, and that phase's own readiness guidance. The human renderer and
        # the JSON payload both project this value verbatim.
        guidance = _guidance(focus.name, folder, config, focus.blocked_reason, documents_root=documents_root)
        gate = f"{focus.name} {focus.state} - {guidance}"
        if focus.state == PENDING:
            phases[PHASES.index(focus.name)] = replace(focus, state=CURRENT)
    blocked_reasons = tuple(
        phase.blocked_reason for phase in phases if phase.state == BLOCKED and phase.blocked_reason
    )
    return DocStatus(folder, tuple(phases), current, next_token, gate, blocked_reasons)


def _tool_command(script: str, work_folder: Path) -> str:
    """A complete, shell-quoted command that runs one entrypoint on ``work_folder``.

    Built with ``shlex.join`` so a work folder containing spaces (or quotes) prints
    as a command a shell parses back to exactly these arguments, and prefixed with
    ``sys.executable`` because the entrypoints are not executable files and must run
    under the interpreter that owns this repository's dependencies.
    """
    return shlex.join([sys.executable, str(ROOT / "tools" / script), str(work_folder)])


def _effective_min_sources(config: ReportConfig) -> int:
    """The source minimum the research gate applies; the default if ``min_sources:`` is invalid
    (the gate itself reports the invalid value)."""
    try:
        return effective_min_sources(config)
    except ValueError:
        return MIN_ACADEMIC_SOURCES


def _uncited_bibliography(config: ReportConfig) -> bool:
    """Whether ``uncited_bibliography:`` is on; an invalid value is the gate's to report."""
    try:
        return config.uncited_bibliography
    except ValueError:
        return False


def _guidance(
    phase_name: str,
    work_folder: Path,
    config: ReportConfig | None = None,
    blocked_reason: str = "",
    *,
    documents_root: Path | None = None,
) -> str:
    """Action sentence for ``phase_name``, bound to the real work-folder path.

    Every path is absolute and every command is complete: the work folder exactly as
    the caller passed it (``derive`` resolves it once), and for the tool phases an
    interpreter + entrypoint + folder command that runs from any working directory.
    Nothing is left to resolve against an assumed cwd. ``config`` may be passed by
    callers that already hold one (``derive``); otherwise it is rebuilt read-only,
    because the review guidance names the configured final PDF.
    """
    template = _GUIDANCE.get(phase_name)
    if template is None:
        return ""
    folder = Path(work_folder)
    if config is None:
        config = ReportConfig(folder=folder, raw=read_yaml(folder / "report.yml"))
    if phase_name == "approval" and not draft_is_fresh(config.pdf_path, folder / "body.md"):
        template = (
            "rebuild the draft PDF: {build_command} --no-approval-check (the draft PDF is missing "
            "or does not match the current {body}); do not present the approval prompt until it "
            "is rebuilt, then re-run doc_status; generation runs only after you approve {body}"
        )
    elif phase_name == "approval":
        template += _approval_format_suffix(folder, config, documents_root)
    if phase_name == "verify" and blocked_reason == "content_check_stale":
        template = ("launch ONE independent verifier for {body} with the brief from {check_command} "
                    "--verify-brief --since verification.yml, then run {check_command} "
                    "--verification verification.yml")
    if phase_name == "verify" and blocked_reason == "content_check_malformed":
        template = "launch ONE independent verifier for {body}, then run the content check: {check_command} --verification verification.yml"
    if phase_name == "verify" and blocked_reason == "content_check_failed":
        template = ("show the user the approval packet from {packet_command} --open (draft PDF, criterion summary, "
                    "missing items) and fix {body} only through the user's literal edit orders; "
                    "rebuild the preview, then re-run the verifier with {check_command} "
                    "--verify-brief --since verification.yml")
    if phase_name == "draft" and blocked_reason == "body_check_failed":
        template = "fix {body} until {check_command} --body-check passes, then re-run doc_status"
    if phase_name == "intake" and not config.metadata.get("student"):
        template += (
            "; a student name the user saved as permanent for all future sessions "
            "(saved as permanent) counts as confirmed: record it without asking; otherwise suggest "
            f"{DEFAULT_STUDENT} as the default student and confirm with the user "
            "through a single-choice prompt (do not auto-fill, never invent a name)"
        )
    if phase_name == "format":
        facts = load_guide_facts(folder, config)
        family = facts.get("family") or config.format_hint
        if family:
            template += f"; guide suggests {family} (confirm the format)"
        known = {key: facts[key] for key in ("practice_number", "practice_type", "planned_time") if key in facts}
        if known:
            template += "; guide already states " + ", ".join(f"{key}={value}" for key, value in known.items())
        if config.format == "ape" or (not config.format and family == "ape"):
            missing = [key for key in config.format_required_metadata if not config.metadata.get(key) or is_placeholder_value(config.metadata.get(key))] if config.format == "ape" else [key for key in ("cycle", "unit", "learning_outcome", "practice_number", "practice_type", "schedule", "place", "planned_time") if not config.metadata.get(key)]
            gaps = [key for key in missing if key not in known]
            if gaps:
                template += "; remaining gaps: " + ", ".join(gaps)
    if phase_name == "review":
        template += ("; open the PDF for the user (never screenshots): "
                     + _tool_command("pdf_viewer.py", config.pdf_path).replace("{", "{{").replace("}", "}}"))
    if phase_name == "research" and _uncited_bibliography(config):
        template = (
            "write at least 1 entry (any type) to {sources}, the exact list to print "
            "(uncited_bibliography: true), then re-run doc_status"
        )
    if phase_name == "research" and _effective_min_sources(config) == 0:
        template = "no sources are required (min_sources: 0); re-run doc_status"
    return template.format(
        folder=folder,
        report_yml=folder / "report.yml",
        min_sources=_effective_min_sources(config),
        sources=folder / "sources.bib",
        rubric=folder / "rubric.yml",
        body=folder / "body.md",
        validation=folder / "validation.yml",
        pdf=config.pdf_path,
        final_review=folder / "final-review.yml",
        check_command=_tool_command("content_check.py", folder),
        packet_command=_tool_command("approval_packet.py", folder),
        build_command=_tool_command("build_report_auto.py", folder),
        deliver_command=_tool_command("deliver_report.py", folder),
        typeset_bind_command=shlex.join([sys.executable, str(ROOT / "tools" / "typeset.py"), "bind", str(folder)]),
        typeset_check_command=shlex.join([sys.executable, str(ROOT / "tools" / "typeset.py"), "check", str(folder)]),
        typeset_body=folder / "body.typeset.md",
    )


def _payload(status: DocStatus) -> dict[str, object]:
    """The ``academic.doc-status/v1`` JSON projection of a derived ``DocStatus``."""
    return {
        "schemaName": SCHEMA_NAME,
        "schemaVersion": SCHEMA_VERSION,
        "workFolder": str(status.work_folder),
        "phases": [
            {"name": p.name, "state": p.state, "detail": p.detail, "blockedReason": p.blocked_reason}
            for p in status.phases
        ],
        "current": status.current,
        "next": status.next_token,
        "gate": status.gate,
        "blockedReasons": list(status.blocked_reasons),
    }


def _route(status: DocStatus) -> str:
    """The one route line, always bracketing exactly the current token."""
    names = [phase.name for phase in status.phases]
    if status.current in names:
        tokens = [f"[{name}]" if name == status.current else name for name in names]
    else:  # route complete: the bracket advances past the last phase to `done`
        tokens = [*names, f"[{status.current}]"]
    return " > ".join(tokens)


def _gate(status: DocStatus) -> str:
    """Project the authoritative gate: ``status.gate`` derived once in ``derive``.

    There is no second derivation here -- the human block renders exactly the
    value the JSON payload carries, so the two outputs cannot disagree. The gate
    names the route's actual focus phase with its own readiness guidance; there
    is no approval front-load for phases that have not reached approval.
    """
    return status.gate


def _summary_lines(status: DocStatus) -> list[str]:
    """Flat summary bullets; ``pending`` phases stay terse because they only wait."""
    return [
        f"- {phase.name}: {phase.state}"
        + (f" - {phase.detail}" if phase.state != PENDING and phase.detail else "")
        for phase in status.phases
    ]


def render_human(status: DocStatus) -> str:
    """Render the portable human block: optional gate, one bracketed route line,
    a flat ``**Summary**``, and a closing ``**Next**`` -- ASCII only, no tables."""
    lines: list[str] = []
    gate = _gate(status)
    if gate:
        lines.append(f"**Gate**: {gate}")
    lines.append(f"Route: {_route(status)}")
    lines.extend(["", "**Summary**", *_summary_lines(status), ""])
    next_line = f"**Next**: {status.next_token}"
    if status.next_token in PHASES:
        focus = next(phase for phase in status.phases if phase.name == status.next_token)
        next_line += f" - {_guidance(status.next_token, status.work_folder, blocked_reason=focus.blocked_reason)}"
    lines.append(next_line)
    return "\n".join(lines) + "\n"


def render_machine(status: DocStatus) -> str:
    """Render the ``academic.doc-status/v1`` machine block (sdd-status shape)."""
    payload = _payload(status)
    reasons = [f"- {reason}" for reason in status.blocked_reasons] or ["- none"]
    lines = [
        "## Document Workflow Status",
        "",
        f"schema: {SCHEMA_NAME}/v{SCHEMA_VERSION}",
        f"next: {status.next_token}",
        "",
        "### Summary",
        *[f"- {phase.name}: {phase.state}" for phase in status.phases],
        "",
        "### Blocked Reasons",
        *reasons,
        "",
        "### JSON",
        "```json",
        json.dumps(payload, indent=2),
        "```",
    ]
    return "\n".join(lines) + "\n"


def _is_readable_dir(folder: Path) -> bool:
    """True when ``folder`` is an existing, listable directory."""
    try:
        return folder.is_dir() and os.access(folder, os.R_OK | os.X_OK)
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python tools/doc_status.py <work-folder> [--json]``.

    Exit 2 for a missing, non-directory or unreadable folder (creating nothing); exit
    0 for any derivable folder. Both blocks render every time: human then machine on
    stdout, and under ``--json`` machine on stdout with human on stderr.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in args
    positional = [arg for arg in args if arg != "--json"]
    if len(positional) != 1:
        print("usage: doc_status.py <work-folder> [--json]", file=sys.stderr)
        return 2
    folder = Path(positional[0])
    if not _is_readable_dir(folder):
        print(f"work folder missing, not a directory, or unreadable: {folder}", file=sys.stderr)
        return 2
    status = derive(folder)
    if json_mode:
        sys.stdout.write(render_machine(status))
        sys.stderr.write(render_human(status))
    else:
        sys.stdout.write(render_human(status))
        sys.stdout.write(render_machine(status))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
