#!/usr/bin/env python3
"""The hard content check: record the verifier's matrix, derive the verdict.

verify-concise-drafts T6 replaces the two independent judges with ONE
independent read-only verifier. It scores nothing: it fills a requirement ->
evidence matrix (``verification.yml``, schema ``academic.verification/v1``):
``requirements: [{criterion, requirement, status: found|partial|missing, location,
evidence, gap}]`` plus ``unmapped_paragraphs`` (deletion candidates) and free-text
``findings``. ``found`` needs ``evidence``, an exact quote from ``body.md``;
``partial`` (covered in part) needs that quote too and ``gap``, what is still
absent; ``gap`` is written only for ``partial``, so records without it stay valid.
This tool never generates the matrix; it validates it against the plan
(``tools/rubric_plan.py``), downgrades any ``found`` requirement whose quote is
not in ``body.md`` (whitespace-normalized) to ``missing`` with a finding (same for
``partial``), derives each criterion as ``cumple`` (all its requirements found;
a ``partial`` does not count, only the grade weighs it) or ``falta``, adds the
deterministic mechanical checks over ``body.md`` and the document bib, and writes
``content-check.yml`` (schema ``academic.content-check/v1``) with the derived
``result``: ``pass`` only when every criterion is ``cumple`` AND every
mechanical check is ok, so the agent can never declare a pass by itself.

Mechanical checks reuse the repo's existing citation helpers instead of a new
regex: ``validate_ieee_refs.cited_keys``/``bib_keys`` for `[@key]` extraction
and resolution, and ``source_count.eligible_entry_keys``/``MIN_ACADEMIC_SOURCES``
for the at-least-five-eligible-sources-cited gate (T2). ``links_resolve``
(``tools/link_check.py``) opens every http(s) URL in the body: an HTTP error
fails, DNS failures and timeouts are warnings only.

The check reports findings and never rewrites the draft: its only write is
``content-check.yml``. ``body.md`` bytes flow into ``body_sha256`` exactly as
``approval.yml`` binds them, ``rubric.yml`` and the document bib into
``rubric_sha256``/``bib_sha256`` (new-report-flow T5), so
``content_check_state`` can detect any input edited after the check and route
the phase back to ``stale``. When the report declares a guide input, the check
binds it too (``guide_sha256``, report-flow-hardening T11); markers written
before a guide existed carry no key and stay valid. A missing or unreadable
file is data, never a crash: ``content_check_state`` never raises. The marker
is written atomically (temp file + ``os.replace``), so a crash can never leave
a half-written verdict.

``content_check_state`` also never trusts the recorded ``result`` blindly: it
re-derives the verdict from the recorded criteria (every status ``cumple``),
the recorded requirements (all ``found``, every criterion covered), the recorded
mechanical checks (every ``ok``), and the recorded criterion ids (equal to the
current rubric ids) -- a forged ``result: pass`` fails. A ``partial`` requirement
passes only when a human accepted it in ``accepted-gaps.yml`` (``accepted_gaps.py``):
the write path and ``content_check_state`` share one predicate, and the waiver is
re-read and re-validated against the body, rubric, bib and recorded requirements
each time, never copied into the marker, so the recorded statuses stay
``partial``/``falta`` and ``missing`` never passes. Markers written by the
old two-judge flow (``judges``/``disagreements``) stay readable and valid.

CLI: ``python tools/content_check.py <report-folder> --verification <file>``
exits 0 on pass, 1 on fail, 2 on usage/input error; ``--verify-brief`` prints the
verifier's assignment. Length is the body check's (``word_budget``: prose words,
tables excluded): the brief tells the verifier not to count words or report
length, and the ``--verification`` output prints the same ``word_budget`` line
the body check prints, outside the marker and the verdict (faster-verify-loop S3).
The plan's ``needs_person`` items (S5) are listed in the brief, and a ``partial``
whose gap is one of their reasons is printed as ``waiting for a person``; it
stays ``partial`` and the verdict stays ``fail`` until a person accepts it.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import concision
import link_check
import rubric_plan
import rubric_checks
import timings
import yaml
import accepted_gaps
from approval_marker import BODY_NAME, sha256_file
from bounded_edit import LIMIT, bounded, heading_outline
from report_config import ReportConfig, read_yaml
from validate_report import SECTION_SPECS, bold_pseudo_heading_lines, section_structure_validation
from source_count import MIN_ACADEMIC_SOURCES, all_entry_keys, effective_min_sources, eligible_entry_keys
from validate_ieee_refs import bib_keys, cited_keys

CONTENT_CHECK_NAME = "content-check.yml"
# The body bytes the check ran on; a bounded edit against them keeps the marker.
CHECKED_SNAPSHOT_NAME = "checked-body.md"
CONTENT_CHECK_SCHEMA = "academic.content-check/v1"
VERIFICATION_SCHEMA = "academic.verification/v1"
REQUIREMENT_STATUSES = ("found", "partial", "missing")
JUDGMENT_STATUSES = ("cumple", "flojo", "falta")  # legacy two-judge markers
RESULT_VALUES = ("pass", "fail")
LEGACY_MECHANICAL_NAMES = {"citations_resolve", "eligible_sources_cited", "judgments_match_rubric", "rubric_checks"}
MECHANICAL_NAMES = {
    "citations_resolve", "eligible_sources_cited", "verification_matches_rubric", "rubric_checks", "links_resolve",
}

# Keys content-check.yml must carry for content_check_state to trust it; the
# per-check ``mechanical`` entries and ``criteria`` records are validated by
# presence here and by their producers below. Legacy two-judge markers carry
# ``judges``/``disagreements`` instead of the verifier keys.
_COMMON_MARKER_KEYS = (
    "schema",
    "body_sha256",
    "rubric_sha256",
    "bib_sha256",
    "checked_at",
    "criteria",
    "findings",
    "mechanical",
    "result",
)
REQUIRED_MARKER_KEYS = _COMMON_MARKER_KEYS + ("judges", "disagreements")
REQUIRED_VERIFIER_KEYS = _COMMON_MARKER_KEYS + ("verifier", "requirements", "unmapped_paragraphs")


@dataclass(frozen=True)
class CheckOutcome:
    """The result of one content-check run.

    ``errors`` non-empty means a usage/input error: nothing was written and
    ``result``/``marker`` carry no verdict. Otherwise ``marker`` is the exact
    mapping written to ``content-check.yml``.
    """

    result: str
    marker: dict
    errors: tuple[str, ...]


def _guide_input(folder: Path, config: ReportConfig) -> str | None:
    """Resolve the optional guide once, rejecting paths outside this report."""
    raw = config.raw.get("guide")
    if not raw:
        return None
    relative = Path(str(raw))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("guide must be relative to the report folder")
    root = folder.resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("guide must remain inside the report folder")
    if not resolved.is_file():
        return None
    return str(resolved.relative_to(root))


def verifier_inputs(folder: Path, config: ReportConfig) -> list[str]:
    """Exact report-relative names available to the independent verifier."""
    inputs = [rubric_plan.RUBRIC_NAME, BODY_NAME,
              Path(str(config.raw.get("bibliography") or config.raw.get("bib") or "sources.bib")).name]
    guide = _guide_input(folder, config)
    if guide:
        inputs.append(guide)
    return inputs


def _already_run_checks_section(folder: Path, criteria: list[dict], body_text: str) -> str:
    """The deterministic rubric checks already run, with their tolerance rules.

    report-flow-hardening T10: a reviewer once marked a criterion down over a
    sentence-initial capital that ``verbatim_from_guide`` had already accepted,
    re-checking a property the deterministic checks own. The brief therefore
    lists every check's PASS/FAIL outcome over the exact body.md being verified
    and states the tolerances plainly, so a PASS settles that property and the
    verifier spends its read-only pass on what the checks do not cover.
    """
    results = rubric_checks.run_checks(folder, criteria, body_text)
    lines = ["Deterministic rubric checks already run on this exact body.md (tool-run, read-only):"]
    if results:
        lines.extend(
            f"- {result.criterion_id} check {result.check_index} ({result.type}): "
            f"{'PASS' if result.ok else 'FAIL'} - {result.detail}"
            for result in results
        )
    else:
        lines.append("- None: this rubric defines no deterministic checks.")
    lines.append("Tolerance rules these checks apply: " + rubric_checks.TOLERANCE_RULES)
    lines.append(
        "Do not mark a requirement missing for a property a PASSING check above already "
        "verifies (including differences covered by the tolerance rules); verify only what the "
        "checks do not cover. A FAILING check may be cited as evidence."
    )
    return "\n".join(lines) + "\n"


_QUOTE_STYLES = str.maketrans({"“": '"', "”": '"', "«": '"', "»": '"'})


def normalize_body_text(text: str) -> str:
    """The body's words with Markdown markup and quote style stripped.

    Heading markers, list markers, block quotes, emphasis, code ticks, table
    pipes/separator rows, curly versus straight quotes and whitespace do not
    count; any other character does.
    """
    lines = []
    for line in text.translate(_QUOTE_STYLES).splitlines():
        if re.fullmatch(r"\s*\|?(?:\s*:?-{3,}:?\s*\|?)+\s*", line):
            continue
        line = re.sub(r"^\s*(?:#{1,6}\s+|>+\s*|[-*+]\s+|\d+[.)]\s+)", "", line)
        # Math spans are content: their operators never count as markup.
        parts = re.split(r"(\$[^$]*\$)", line)
        for i in range(0, len(parts), 2):
            text_part = parts[i].replace("|", " ").replace("*", "").replace("`", "")
            parts[i] = re.sub(r"(?<!\w)_+|_+(?!\w)", "", text_part)
        lines.append("".join(parts))
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def body_text_sha256(text: str) -> str:
    return hashlib.sha256(normalize_body_text(text).encode("utf-8")).hexdigest()


def section_hashes(body_text: str, criteria: list[dict]) -> dict[str, str]:
    """Markup-normalized hash of each criterion's mapped section; absent sections are omitted."""
    hashes: dict[str, str] = {}
    for criterion in criteria:
        section = criterion.get("section")
        text = concision.section_text(body_text, section) if isinstance(section, str) else None
        if text is not None:
            hashes[str(criterion.get("id"))] = body_text_sha256(text)
    return hashes


def _same_matrix(folder: Path, previous_rubric: object, rubric_hash: str) -> bool:
    """The rubric is unchanged, or changed only in ``max_words`` (faster-verify-loop S4).

    A ceilings-only change is recognized only through the ``rubric_matrix_sha256``
    the previous ``content-check.yml`` recorded for that same ``rubric_sha256``;
    a marker without it (written before this field) behaves as before.
    """
    if previous_rubric == rubric_hash:
        return True
    try:
        marker = yaml.safe_load((folder / CONTENT_CHECK_NAME).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return False
    if not isinstance(marker, dict) or marker.get("rubric_sha256") != previous_rubric:
        return False
    recorded = marker.get("rubric_matrix_sha256")
    return isinstance(recorded, str) and bool(recorded) and recorded == rubric_plan.rubric_matrix_sha256(folder)


def _incremental_section(folder: Path, since: Path, criteria: list[dict], hashes: dict[str, str],
                         rubric_hash: str) -> str:
    """Brief block for a re-verify after an edit (verify-concise-drafts T7, S2).

    A criterion whose mapped section hashes the same as in the previous
    verification is carried over verbatim; the verifier re-checks only the
    rest. Carried quotes are still checked against body.md by run_check. A
    rubric change forces a full verify, except one that only touches
    ``max_words`` (``_same_matrix``).
    """
    previous, errors = parse_verification(since)
    if errors:
        raise ValueError(errors[0])
    name = Path(since).name
    if not _same_matrix(folder, previous["rubric_sha256"], rubric_hash):
        return f"Previous verification {name}: full verify: the rubric changed since it was written.\n"
    old = previous["section_sha256"]
    carried = [str(c.get("id")) for c in criteria
               if str(c.get("id")) in hashes and old.get(str(c.get("id"))) == hashes[str(c.get("id"))]]
    recheck = [str(c.get("id")) for c in criteria if str(c.get("id")) not in carried]
    text = (f"Incremental re-verify against {name}: only the sections of the re-checked criteria changed.\n"
            f"Re-check only these criteria: {', '.join(recheck) or '(none)'}\n"
            f"Carried over unchanged (the tool merges them from the previous check; do not list them): "
            f"{', '.join(carried) or '(none)'}\n")
    return text + ("Return requirements only for the re-checked criteria (an empty list when there are none) and "
                   "list unmapped paragraphs only for their sections; the tool still checks every carried "
                   "evidence quote against body.md.\n")


# faster-verify-loop S3: the body check owns length, so the verifier never counts words.
WORD_BUDGET_NOTE = (
    "Length is checked mechanically: the tool's word_budget check counts prose words, tables "
    "excluded, against the rubric's max_words. Do not count words and do not report length in "
    "requirements, findings or prose_findings.\n"
)


VERIFY_EXAMPLE_NOTE = (
    "\nDouble-quote every string value (every requirement, location, evidence and finding): an "
    "unquoted ': ' inside a value breaks the YAML.\nExample of valid requirements, unmapped "
    "paragraphs and findings:\n"
    "```yaml\n"
    f'schema: "{VERIFICATION_SCHEMA}"\n'
    "requirements:\n"
    '  - criterion: "objetivo"\n'
    '    requirement: "The guide asks for a measurable goal."\n'
    '    status: "found"\n'
    '    location: "## Objetivos, first paragraph"\n'
    '    evidence: "Medir la deriva con error menor al 2 %"\n'
    '  - criterion: "objetivo"\n'
    '    requirement: "The guide asks for one Wokwi link per part."\n'
    '    status: "missing"\n'
    '    location: ""\n'
    '    evidence: ""\n'
    "unmapped_paragraphs:\n"
    '  - "Como es sabido, la simulacion"\n'
    "findings:\n"
    '  - "WARNING: the conclusion repeats the introduction."\n'
    "```\n"
)

def _parse_prose_findings(name: str, raw: object) -> tuple[list[dict], list[str]]:
    """The verifier's optional ``prose_findings``: mappings with location, kind, quote and fix.

    Absent or empty is legal (every verification written before this key exists).
    A malformed entry is a usage error; entries beyond the cap are ignored.
    """
    if raw in (None, []):
        return [], []
    if not isinstance(raw, list):
        return [], [f"{name} prose_findings must be a list of mappings"]
    items: list[dict] = []
    for index, record in enumerate(raw[: concision.MAX_PROSE_FINDINGS], start=1):
        if not isinstance(record, dict):
            return [], [f"{name} prose_findings entry {index} must be a mapping"]
        kind, quote = record.get("kind"), record.get("quote")
        if kind not in concision.PROSE_KINDS:
            return [], [f"{name} prose_findings entry {index} kind must be one of: {', '.join(concision.PROSE_KINDS)}"]
        if not isinstance(quote, str) or not quote.strip():
            return [], [f"{name} prose_findings entry {index} needs a quote from body.md"]
        items.append({"location": _text_or_none(record.get("location")) or "", "kind": kind,
                      "quote": " ".join(quote.split()), "fix": _text_or_none(record.get("fix")) or ""})
    return items, []


def merge_prose_findings(body_text: str, lint: list[dict], verifier: list[dict]) -> tuple[list[dict], list[str]]:
    """Lint findings plus the verifier's whose quote really is in body.md (others become findings)."""
    normalized_body = " ".join(body_text.split())
    merged = [{**item, "source": "lint"} for item in lint]
    dropped: list[str] = []
    for item in verifier:
        if item["quote"] in normalized_body:
            merged.append({**{k: item[k] for k in ("location", "kind", "quote", "fix")}, "source": "verifier"})
        else:
            dropped.append(f"prose finding dropped, quote not in body.md: '{item['quote']}'")
    return merged[: concision.MAX_PROSE_FINDINGS * 2], dropped


_FINDING_SEVERITY_KEYS = ("severity", "level")
_FINDING_TEXT_KEYS = ("text", "message", "detail")


def _flatten_finding(item: object) -> str | None:
    """A finding as a string; a mapping is flattened deterministically, other types are None."""
    if isinstance(item, str):
        return item
    if not isinstance(item, dict) or not item:
        return None
    severity = next((item[k] for k in _FINDING_SEVERITY_KEYS if isinstance(item.get(k), str)), None)
    text = next((item[k] for k in _FINDING_TEXT_KEYS if isinstance(item.get(k), str)), None)
    if severity is not None and text is not None:
        return f"{severity}: {text}"
    return "; ".join(f"{k}: {item[k]}" for k in sorted(item, key=str))


WAITING_FOR_PERSON = "waiting for a person"


def _needs_person_section(entries: list[dict]) -> str:
    """Brief block naming the plan's ``needs_person`` items (faster-verify-loop S5); empty without any."""
    if not entries:
        return ""
    return ("Items only a person can close (rubric needs_person): when body.md only states the plan for one "
            "of them, report its requirement as partial with the recorded reason, verbatim, as gap; do not "
            "spend a finding or a prose_findings entry on it.\n"
            + "".join(f"- {entry['item']}: {entry['reason']}\n" for entry in entries))


def waiting_for_person(requirements: list, entries: list[dict]) -> list[dict]:
    """The ``partial`` requirements whose gap is a ``needs_person`` reason (whitespace-normalized).

    A label only: the requirement stays ``partial``, the criterion ``falta`` and the
    verdict ``fail`` until a person accepts the gap with ``accepted_gaps.py``.
    """
    reasons = {" ".join(str(entry["reason"]).split()) for entry in entries}
    return [r for r in requirements if isinstance(r, dict) and r.get("status") == "partial"
            and " ".join(str(r.get("gap") or "").split()) in reasons]


def waiting_label(record: dict) -> str:
    return f"{WAITING_FOR_PERSON}: {record.get('requirement')} (gap: {record.get('gap')})"


def _criteria_section(criteria: list[dict]) -> str:
    lines = ["Rubric criteria (every one needs at least one requirement):"]
    for criterion in criteria:
        line = f"- {criterion.get('id')}: {criterion.get('title', '')} (section: {criterion.get('section', '')})"
        deliverables = criterion.get("deliverables")
        if isinstance(deliverables, list) and deliverables:
            line += "; deliverables: " + "; ".join(str(d) for d in deliverables)
        lines.append(line)
    return "\n".join(lines) + "\n"


def _carried_requirements(folder: Path, criteria: list[dict], rubric_hash: str, body_text: str,
                          answered: set[str]) -> list[dict]:
    """Requirements the previous content-check.yml settled and the verifier skipped.

    A criterion is carried only when the verifier gave it no requirement, the
    rubric is unchanged (or changed only in ``max_words``, recognized through the
    marker's ``rubric_matrix_sha256``) and its mapped section hashes the same as
    when the previous marker verified it, so an incremental answer lists only what
    changed. Legacy markers without ``section_sha256`` carry nothing.
    """
    try:
        previous = yaml.safe_load((folder / CONTENT_CHECK_NAME).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return []
    if (not isinstance(previous, dict) or previous.get("schema") != CONTENT_CHECK_SCHEMA
            or not _same_matrix(folder, previous.get("rubric_sha256"), rubric_hash)
            or not isinstance(previous.get("section_sha256"), dict)
            or not isinstance(previous.get("requirements"), list)):
        return []
    current = section_hashes(body_text, criteria)
    old = previous["section_sha256"]
    keep = {cid for cid, digest in current.items() if cid not in answered and old.get(cid) == digest}
    records = [record for record in previous["requirements"] if _carryable(record, keep)]
    return [{key: str(record.get(key) or "")
             for key in ("criterion", "requirement", "status", "location", "evidence",
                         *(("gap",) if record.get("status") == "partial" else ()))}
            for record in records]


def _carryable(record: object, keep: set[str]) -> bool:
    """The marker is now an input, so a carried record meets parse_verification's
    rules: a kept criterion, a non-blank demand, a valid status and, when found or
    partial, a non-blank quote (an empty quote would pass the in-body check) and,
    when partial, a non-blank gap."""
    if not isinstance(record, dict):
        return False
    criterion, demand, evidence = record.get("criterion"), record.get("requirement"), record.get("evidence")
    if not isinstance(criterion, str) or criterion not in keep:
        return False
    if not isinstance(demand, str) or not demand.strip() or record.get("status") not in REQUIREMENT_STATUSES:
        return False
    if record["status"] == "missing":
        return True
    gap = record.get("gap")
    return (isinstance(evidence, str) and bool(evidence.strip())
            and (record["status"] == "found" or (isinstance(gap, str) and bool(gap.strip()))))


def verify_brief(folder: Path, since: Path | None = None) -> str:
    """A self-contained, read-only assignment with hashes for the current draft.

    Carries the rubric criteria and deliverables, the already-run deterministic
    rubric checks and their tolerance rules (report-flow-hardening T10), so the
    verifier never re-verifies a property a PASSing check has settled. body.md is
    read exactly once (T11): the recorded ``body_sha256`` and the rubric checks
    verify the same bytes. ``since`` is the previous verification: criteria
    whose sections did not change are carried over instead of re-verified.
    """
    folder = folder.resolve()
    if rubric_plan.rubric_state(folder) != "valid":
        raise ValueError("rubric.yml missing or malformed")
    for name in (BODY_NAME, rubric_plan.RUBRIC_NAME):
        if not (folder / name).is_file():
            raise ValueError(f"{name} missing or unreadable")
    config = ReportConfig(folder=folder, raw=read_yaml(folder / "report.yml"))
    inputs = verifier_inputs(folder, config)
    criteria = rubric_plan.load_rubric(folder)
    try:
        body_bytes = (folder / BODY_NAME).read_bytes()
        body_text = body_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{BODY_NAME} missing or unreadable") from exc
    except OSError as exc:
        raise ValueError(f"{BODY_NAME} missing or unreadable") from exc
    schema = {
        "schema": VERIFICATION_SCHEMA,
        "verifier": {"role": "independent", "inputs": inputs},
        "body_sha256": hashlib.sha256(body_bytes).hexdigest(),
        "rubric_sha256": sha256_file(folder / rubric_plan.RUBRIC_NAME),
        "body_text_sha256": body_text_sha256(body_text),
        "section_sha256": section_hashes(body_text, criteria),
        "requirements": [{"criterion": "<rubric criterion id>", "requirement": "<the guide/rubric demand, quoted>",
                          "status": "found|partial|missing", "location": "<where in body.md>",
                          "evidence": "<exact quote from body.md; required when found or partial>",
                          "gap": "<what is still absent; required when partial, omit otherwise>"}],
        "unmapped_paragraphs": ["<first words of a paragraph that answers no requirement>"],
        "findings": [],
        "prose_findings": [],
    }
    incremental = (_incremental_section(folder, since, criteria, schema["section_sha256"], schema["rubric_sha256"])
                   if since is not None else "")
    return ("You are an independent read-only verifier. Verify only from these inputs; "
            "do not use the drafting conversation or any other files. Do not edit any file.\n"
            "Never score or grade. For each rubric criterion list the requirements the guide and rubric "
            "demand and mark each found, partial or missing (partial: covered in part; quote what is there and "
            "write the gap, what is still absent). Split a plural demand into one requirement per item "
            "(one per part, link, table or question: \"Wokwi links\" for parts A-E is five requirements). "
            "Quote evidence exactly: it must be a verbatim "
            "substring of body.md. When you cannot quote it, mark the requirement missing; never write "
            "that something seems to comply. Check data (numbers, names, links per part) against the guide. "
            "Links are fetched by the tool. List paragraphs that answer no requirement under "
            "unmapped_paragraphs (deletion candidates). Independently review the whole draft for "
            "semantic repetition, circular explanations, ambiguity and missing necessary context; "
            "report specific locations and suggested corrections in findings, without rewriting. "
            "Length and filler checks cannot establish semantic concision. Repeat this whole-draft "
            "review even during incremental verification; findings are advisory, not a score. Also list each "
            "text-quality problem you find as a prose_findings entry (location, kind "
            "repeticion|circular|ambiguo|relleno|registro, an exact quote from body.md, fix); at most "
            f"{concision.MAX_PROSE_FINDINGS}, none when the prose is clean.\n"
            + WORD_BUDGET_NOTE
            + f"Citations [@key] in body.md render in {config.citation_style.upper()} format at build time from sources.bib; citation keys are expected, not a formatting defect. Check that cited keys exist in sources.bib instead.\n"
            + _criteria_section(criteria)
            + _needs_person_section(rubric_plan.load_needs_person(folder))
            + incremental
            + _already_run_checks_section(folder, criteria, body_text)
            + "Allowed input paths (absolute):\n"
            + "\n".join(str(folder / name) for name in inputs)
            + "\nReturn only verification YAML using this schema; allowed statuses: found|partial|missing.\n"
            + yaml.safe_dump(schema, sort_keys=False)
            + VERIFY_EXAMPLE_NOTE)


def _text_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def parse_verification(path: Path) -> tuple[dict, list[str]]:
    """Parse the verifier's file into ``(verification, errors)``.

    The file is the verifier's *input* contract, so a structural violation (bad
    YAML, non-mapping, wrong schema, malformed requirement, ``found`` without an
    evidence quote) is a usage error the caller reports with exit code 2 --
    unlike an unknown criterion id, which is well-formed input that simply fails
    the mechanical check. ``location`` is optional and recorded as a string.
    """
    name = Path(path).name
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {}, [f"{name} is not valid UTF-8; save it as UTF-8"]
    except OSError:
        return {}, [f"{name} unreadable"]
    try:
        data = yaml.safe_load(text)
    except Exception:
        return {}, [f"{name} is not valid YAML"]
    if not isinstance(data, dict):
        return {}, [f"{name} must be a YAML mapping"]
    if data.get("schema") != VERIFICATION_SCHEMA:
        return {}, [f"{name} schema must be {VERIFICATION_SCHEMA}"]

    records = data.get("requirements")
    # An empty list is legal on an incremental re-verify where every criterion
    # is carried over; run_check rejects it when nothing fills it.
    if not isinstance(records, list):
        return {}, [f"{name} requirements must be a non-empty list"]

    errors: list[str] = []
    requirements: list[dict] = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            errors.append(f"{name} requirement {index} must be a mapping")
            continue
        criterion = record.get("criterion")
        demand = record.get("requirement")
        status = record.get("status")
        evidence = record.get("evidence")
        if not isinstance(criterion, str) or not criterion.strip():
            errors.append(f"{name} requirement {index} missing or blank criterion")
            continue
        if not isinstance(demand, str) or not demand.strip():
            errors.append(f"{name} requirement {index} (criterion '{criterion}') missing or blank requirement")
            continue
        if status not in REQUIREMENT_STATUSES:
            allowed = ", ".join(REQUIREMENT_STATUSES)
            errors.append(f"{name} requirement {index} (criterion '{criterion}') status must be one of: {allowed}")
            continue
        if status in ("found", "partial") and (not isinstance(evidence, str) or not evidence.strip()):
            errors.append(f"{name} requirement {index} (criterion '{criterion}') is {status} but has no evidence quote")
            continue
        gap = record.get("gap")
        if status == "partial" and (not isinstance(gap, str) or not gap.strip()):
            errors.append(f"{name} requirement {index} (criterion '{criterion}') is partial but has no gap")
            continue
        requirements.append(
            {
                "criterion": criterion,
                "requirement": demand,
                "status": status,
                "location": _text_or_none(record.get("location")) or "",
                "evidence": _text_or_none(evidence) or "",
                **({"gap": gap.strip()} if status == "partial" else {}),
            }
        )

    unmapped = data.get("unmapped_paragraphs") or []
    if not isinstance(unmapped, list) or not all(isinstance(item, str) for item in unmapped):
        errors.append(f"{name} unmapped_paragraphs must be a list of strings")
        unmapped = []

    findings = data.get("findings") or []
    flattened = [_flatten_finding(f) for f in findings] if isinstance(findings, list) else [None]
    if any(f is None for f in flattened):
        errors.append(f"{name} findings must be a list of strings")
        flattened = []
    prose, prose_errors = _parse_prose_findings(name, data.get("prose_findings"))
    errors.extend(prose_errors)
    return (
        {
            "verifier": data.get("verifier"),
            "body_sha256": data.get("body_sha256"),
            "rubric_sha256": data.get("rubric_sha256"),
            "body_text_sha256": _text_or_none(data.get("body_text_sha256")) or "",
            "section_sha256": {str(k): v for k, v in (data.get("section_sha256") or {}).items()
                               if isinstance(v, str)} if isinstance(data.get("section_sha256"), dict) else {},
            "requirements": requirements,
            "unmapped_paragraphs": list(unmapped),
            "findings": flattened,
            "prose_findings": prose,
        },
        errors,
    )


def downgrade_unquoted_evidence(requirements: list[dict], body_text: str) -> tuple[list[dict], list[str]]:
    """The anti-hallucination rule: ``found`` and ``partial`` need a quote that body.md really holds.

    A ``found`` or ``partial`` requirement whose evidence is absent from body.md
    (whitespace-normalized, case-sensitive) becomes ``missing`` and yields a
    finding naming its criterion and the quote; nothing else changes.
    """
    normalized_body = " ".join(body_text.split())
    result: list[dict] = []
    findings: list[str] = []
    for record in requirements:
        if record["status"] in ("found", "partial") and " ".join(record["evidence"].split()) not in normalized_body:
            findings.append(
                f"evidence not found in body.md: criterion '{record['criterion']}': requirement "
                f"'{record['requirement']}' downgraded to missing; quote: '{record['evidence']}'"
            )
            record = {key: value for key, value in record.items() if key != "gap"} | {"status": "missing"}
        result.append(record)
    return result, findings


def requirements_accepted(requirements: list, waived: frozenset[tuple[str, str]]) -> bool:
    """Every requirement is ``found`` or a ``partial`` a human accepted (``accepted_gaps.py``).

    One predicate for the write path and ``content_check_state``: ``missing``
    never passes, and a ``partial`` passes only when ``waived`` names its
    ``(criterion, requirement)``.
    """
    return all(
        isinstance(r, dict) and (
            r.get("status") == "found"
            or (r.get("status") == "partial" and (str(r.get("criterion")), str(r.get("requirement"))) in waived)
        )
        for r in requirements
    )


def criteria_closed(criteria: list, requirements: list, waived: frozenset[tuple[str, str]]) -> bool:
    """Every criterion is ``cumple``, or ``falta`` only because of ``partial`` requirements all accepted.

    The recorded status stays ``falta``; this is the verdict's reading of it.
    """
    for record in criteria:
        if not isinstance(record, dict):
            return False
        if record.get("status") == "cumple":
            continue
        own = [r for r in requirements if isinstance(r, dict) and str(r.get("criterion")) == str(record.get("id"))]
        if (record.get("status") != "falta" or not any(r.get("status") == "partial" for r in own)
                or not requirements_accepted(own, waived)):
            return False
    return True


def derive_criteria(criteria: list[dict], requirements: list[dict]) -> list[dict]:
    """Per-criterion ``cumple`` (every requirement found) or ``falta``; never ``flojo``.

    A ``partial`` requirement is not found: it keeps the criterion ``falta`` and
    shows in the note; the 0.5 weight is the grade's, not the verdict's."""
    derived = []
    for criterion in criteria:
        cid = str(criterion.get("id"))
        own = [r for r in requirements if r["criterion"] == cid]
        found = sum(1 for r in own if r["status"] == "found")
        partial = sum(1 for r in own if r["status"] == "partial")
        derived.append(
            {
                "id": cid,
                "status": "cumple" if own and found == len(own) else "falta",
                "where": "; ".join(dict.fromkeys(r["location"] for r in own if r["location"])),
                "note": f"{found}/{len(own)} requirements found" + (f", {partial} partial" if partial else ""),
            }
        )
    return derived


_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_SCRIPT_CHARS_RE = re.compile("[\u2070-\u209f\u00b9\u00b2\u00b3]")
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def body_format_problems(body_text: str) -> list[str]:
    """Deterministic body.md format defects that only show up in the rendered PDF.

    Fenced code blocks and inline code are skipped. The PDF template numbers
    sections from level-1 headings (a ``##``-only body numbers them 0.1.) and
    its font lacks Unicode sub/superscripts (they render blank), so a body
    without a ``# `` heading, or carrying such characters, fails before approval.
    """
    has_h1 = False
    bad_lines: list[int] = []
    in_fence = False
    for number, line in enumerate(body_text.splitlines(), start=1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if re.match(r"# \S", line):
            has_h1 = True
        if _SCRIPT_CHARS_RE.search(_INLINE_CODE_RE.sub("", line)):
            bad_lines.append(number)
    problems = []
    if not has_h1:
        problems.append("no level-1 heading: sections must start at `# ` (not `##`)")
    if bad_lines:
        problems.append(
            "Unicode superscript/subscript characters at "
            + ", ".join(f"line {n}" for n in bad_lines)
            + ": the PDF font renders them blank; write math instead, e.g. "
            "`$c_1$`, `$10^{-5}$`, `m/s$^2$`"
        )
    # The validator's own rule, applied to the whole body exactly as it will be
    # at validation time, so a defect is caught before approval, not after.
    bold = bold_pseudo_heading_lines(body_text)
    if bold:
        problems.append(
            "bold-only line(s) used as headings at "
            + ", ".join(f"line {n}" for n, _ in bold)
            + ": use a `##`/`###` heading instead of manual bold"
        )
    return problems


# Backend formatting a plain-text draft must not carry (issue #96). Code spans
# and fenced blocks are content and are skipped. Order is the report order.
# Inline math follows Pandoc's rule, so currency such as "$5 y $10" is text: the
# opening ``$`` is followed by a non-space, the closing one follows a non-space
# and is not followed by a digit (issue #98).
_PLAIN_TEXT_MARKUP: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("math", re.compile(r"\$\$|\$(?=\S)[^$\n]*(?<=\S)\$(?!\d)|\\\(|\\\[")),
    ("LaTeX command", re.compile(r"\\[A-Za-z]+")),
    ("table", re.compile(r"^\s*\|.*\|\s*$")),
    ("image", re.compile(r"!\[[^\]\n]*\]\(")),
    ("bold", re.compile(r"\*\*[^*\n]+\*\*")),
    ("HTML comment", re.compile(r"<!--")),
)


# A Windows path is text, not LaTeX (issue #98): a drive (``C:\dir``), ``.\`` or
# UNC (``\\server``) prefix, two or more segments, or a file extension. A lone
# ``2\times3`` or ``x\cdot`` has none of these and stays a command.
_WINDOWS_PATH_RE = re.compile(
    r"(?<!\S)(?:"
    r"(?:[A-Za-z]:|\.{1,2}|\\)\\\S*"
    r"|[\w.-]+\\[\w.-]+\\\S*"
    r"|[\w.-]+\\[\w-]+\.[A-Za-z0-9]{1,5}\b"
    r")"
)


def plain_text_problems(body_text: str) -> list[str]:
    """Backend formatting in a plain-text draft, one entry per offending line.

    The draft keeps only ``#`` headings and ``[@key]`` citations as markers;
    math, LaTeX commands, pipe tables, images, bold and HTML comments belong
    to ``body.typeset.md`` after approval, so a formatting fix never touches
    the approved text.
    """
    hits: list[str] = []
    in_fence = False
    for number, line in enumerate(body_text.splitlines(), start=1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        text = _WINDOWS_PATH_RE.sub("", _INLINE_CODE_RE.sub("", line))
        hits.extend(f"line {number} ({label})" for label, pattern in _PLAIN_TEXT_MARKUP if pattern.search(text))
    if not hits:
        return []
    return [
        "backend formatting in the plain-text draft at "
        + ", ".join(hits)
        + ": write plain text (formulas in readable notation, figures as `Figura: caption (path)`); "
        "formatting is applied in body.typeset.md after approval (typeset)"
    ]


def draft_format_problems(body_text: str) -> list[str]:
    """Format defects of a plain-text draft: the level-1 heading rule only.

    Unicode sub/superscripts are plain text here; ``body_format_problems``
    applies the rendering rules to ``body.typeset.md``.
    """
    return [p for p in body_format_problems(body_text) if p.startswith("no level-1 heading")]


def mechanical_checks(
    body_text: str,
    bib_text: str,
    criteria: list[dict],
    requirements: list[dict],
    min_sources: int = MIN_ACADEMIC_SOURCES,
    uncited_bibliography: bool = False,
) -> list[dict]:
    """Derive the deterministic per-check entries (``check``/``ok``/``detail``).

    (a) every ``[@key]`` citation in body.md resolves to a bib entry;
    (b) at least ``min_sources`` (the report's effective minimum) distinct eligible book/paper entries
        are actually cited in body.md (not merely present in the bib);
        (``uncited_bibliography`` replaces this with "the bib lists at least one entry");
    (c) every rubric criterion id has at least one requirement and no requirement names an unknown id.
    """
    cited = cited_keys(body_text)
    known_bib = bib_keys(bib_text)
    eligible = set(eligible_entry_keys(bib_text))
    unresolved = sorted(cited - known_bib)
    eligible_cited = sorted(cited & eligible)

    checks: list[dict] = []

    if cited:
        detail = f"{len(cited) - len(unresolved)}/{len(cited)} cited keys resolve to bib entries"
        if unresolved:
            detail += f"; unresolved: {', '.join(unresolved)}"
    else:
        detail = "no [@key] citations in body.md"
    checks.append({"check": "citations_resolve", "ok": not unresolved, "detail": detail})

    if uncited_bibliography:
        listed = len(all_entry_keys(bib_text))
        noun = "entry" if listed == 1 else "entries"
        checks.append(
            {
                "check": "eligible_sources_cited",
                "ok": listed >= 1,
                "detail": f"uncited bibliography: {listed} {noun} listed, no citations required",
            }
        )
    else:
        checks.append(
            {
                "check": "eligible_sources_cited",
                "ok": len(eligible_cited) >= min_sources,
                "detail": (
                    f"{len(eligible_cited)}/{min_sources} eligible book or paper "
                    f"sources cited in body.md"
                    + (f": {', '.join(eligible_cited)}" if eligible_cited else "")
                ),
            }
        )

    known_ids = [str(criterion.get("id")) for criterion in criteria]
    counts = Counter(str(record["criterion"]) for record in requirements)
    problems: list[str] = []
    missing = [cid for cid in known_ids if counts.get(cid, 0) == 0]
    if missing:
        problems.append(f"no requirement for: {', '.join(missing)}")
    unknown = sorted(set(counts) - set(known_ids))
    if unknown:
        problems.append(f"unknown ids: {', '.join(unknown)}")
    detail = "; ".join(problems) or (
        f"every criterion has at least one requirement ({len(known_ids)} criteria, {len(requirements)} requirements)"
    )
    checks.append({"check": "verification_matches_rubric", "ok": not problems, "detail": detail})

    return checks


def _read_bib(config: ReportConfig) -> str:
    """Read the document bib through ReportConfig.bib_path, tolerating bad files.

    A missing, unreadable or non-UTF-8 bib becomes empty text, so the mechanical
    checks fail closed (unresolved citations, zero eligible sources) instead of
    crashing -- the same tolerance source_count.source_gate applies.
    """
    bib = config.bib_path
    if bib is None:
        return ""
    try:
        return bib.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def _sha256_or_empty(path: Path | None) -> str:
    """The hex digest of ``path``, or ``""`` when it is absent/unreadable.

    The empty string is the recorded identity of 'this input did not exist when
    the check ran', so a file that appears (or disappears) afterwards changes
    the binding and the state goes stale.
    """
    if path is None:
        return ""
    try:
        return sha256_file(path)
    except OSError:
        return ""


def _write_marker_atomically(path: Path, text: str | bytes) -> None:
    """Write ``text`` to ``path`` so readers never see a half-written marker.

    The temp file sits beside the target (same filesystem, so ``os.replace`` is
    atomic) and is removed even when the replace fails, so a crashed check
    never leaves a ``content-check.yml.tmp`` behind for the next run to trip on.
    """
    tmp = path.with_name(path.name + ".tmp")
    try:
        if isinstance(text, bytes):
            tmp.write_bytes(text)
        else:
            tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def links_resolve_check(body_text: str, fetcher: link_check.Fetcher | None) -> tuple[dict, list[str]]:
    """The ``links_resolve`` entry plus its warning findings (unreachable hosts never fail)."""
    urls = link_check.extract_urls(body_text)
    if not urls:
        return {"check": "links_resolve", "ok": True, "detail": "no http(s) URLs in body.md"}, []
    results = link_check.check_links(urls, fetcher)
    broken = [r for r in results if r.status == "broken"]
    unreachable = [r for r in results if r.status == "unreachable"]
    detail = f"{len(results)} links checked"
    if broken:
        detail += "; broken: " + ", ".join(f"{r.url} ({r.detail})" for r in broken)
    elif not unreachable:
        detail += ", all resolve"
    if unreachable:
        detail += f"; {len(unreachable)} unreachable (warning only)"
    warnings = [f"link warning: {r.url} unreachable ({r.detail}); not verified" for r in unreachable]
    return {"check": "links_resolve", "ok": not broken, "detail": detail}, warnings


def run_check(
    folder: Path,
    verification_path: Path,
    config: ReportConfig | None = None,
    fetcher: link_check.Fetcher | None = None,
) -> CheckOutcome:
    """Run the content check for a report folder and write content-check.yml.

    The only file this function writes is ``content-check.yml``; ``body.md`` is
    read for hashing, citation and quote matching and never modified. On a usage
    or input error (missing folder/rubric/body, malformed verification) nothing
    is written and ``errors`` names the offending file. ``fetcher`` replaces the
    production HTTP fetcher (tests never reach the network).
    """
    folder = Path(folder)
    if not folder.is_dir():
        return CheckOutcome("", {}, (f"report folder not found: {folder}",))

    if rubric_plan.rubric_state(folder) != "valid":
        return CheckOutcome(
            "", {}, (f"{rubric_plan.RUBRIC_NAME} missing or malformed; run the plan phase first",)
        )

    body_path = folder / BODY_NAME
    try:
        body_text = body_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return CheckOutcome("", {}, (f"{BODY_NAME} is not valid UTF-8",))
    except OSError:
        return CheckOutcome("", {}, (f"{BODY_NAME} missing or unreadable",))

    if isinstance(verification_path, (list, tuple)):
        if len(verification_path) != 1:
            return CheckOutcome("", {}, ("exactly one verification file required: pass one --verification",))
        verification_path = verification_path[0]
    verification, errors = parse_verification(verification_path)
    if errors:
        return CheckOutcome("", {}, tuple(errors))
    if config is None:
        # Build directly (doc_status's production rule): a missing report.yml is
        # an empty mapping, so the bib default (sources.bib) still applies.
        config = ReportConfig(folder=folder, raw=read_yaml(folder / "report.yml"))

    try:
        min_sources = effective_min_sources(config)
        uncited = config.uncited_bibliography
    except ValueError as exc:
        return CheckOutcome("", {}, (str(exc),))

    try:
        expected_inputs = verifier_inputs(folder, config)
        criteria = rubric_plan.load_rubric(folder)
        rubric_hash = sha256_file(folder / rubric_plan.RUBRIC_NAME)
    except (OSError, ValueError, TypeError) as exc:
        return CheckOutcome("", {}, (f"rubric or guide missing, malformed or unreadable: {exc}",))
    if not criteria:
        return CheckOutcome("", {}, ("rubric.yml missing or malformed",))
    name = Path(verification_path).name
    verifier = verification["verifier"]
    reused = False
    if not isinstance(verifier, dict) or verifier.get("role") != "independent":
        errors.append(f"{name}: verifier.role must be independent")
    elif verifier.get("inputs") != expected_inputs:
        errors.append(f"{name}: verifier.inputs must list exactly: {', '.join(expected_inputs)}")
    verified_body, verified_rubric = verification["body_sha256"], verification["rubric_sha256"]
    if not isinstance(verified_body, str) or not isinstance(verified_rubric, str):
        errors.append(f"{name}: body_sha256 and rubric_sha256 are required")
    elif verified_rubric != rubric_hash:
        errors.append(f"{name}: verification is for a different draft; re-run the verifier")
    elif verified_body != sha256_file(body_path):
        # Stale body hash: still valid when only markup changed (same words).
        if verification["body_text_sha256"].strip().lower() == body_text_sha256(body_text):
            reused = True
        else:
            errors.append(f"{name}: verification is for a different draft; re-run the verifier")
    if errors:
        return CheckOutcome("", {}, tuple(errors))

    answered = {item["criterion"] for item in verification["requirements"]}
    carried = _carried_requirements(folder, criteria, rubric_hash, body_text, answered)
    if not verification["requirements"] and not carried:
        return CheckOutcome("", {}, (f"{name} requirements must be a non-empty list",))
    requirements, downgrade_findings = downgrade_unquoted_evidence(
        [*verification["requirements"], *carried], body_text)
    derived = derive_criteria(criteria, requirements)
    link_entry, link_warnings = links_resolve_check(body_text, fetcher)
    prose, prose_dropped = merge_prose_findings(
        body_text, concision.prose_findings(body_text), verification["prose_findings"])
    findings = list(dict.fromkeys([*verification["findings"], *downgrade_findings, *link_warnings, *prose_dropped]))
    checks = mechanical_checks(body_text, _read_bib(config), criteria, requirements, min_sources, uncited)
    if reused and checks[-1]["ok"]:
        checks[-1]["detail"] += "; verification reused: markup-only change"
    rubric_results = [vars(item) for item in rubric_checks.run_checks(folder, criteria, body_text)]
    failed = [item for item in rubric_results if not item["ok"]]
    format_problems = draft_format_problems(body_text) + plain_text_problems(body_text)
    statuses = {item["id"]: item["status"] for item in derived}
    detail = "; ".join(
        f"{item['criterion_id']} check {item['check_index']} ({item['type']}): {item['detail']}"
        + (" (verified cumple despite failing check)" if statuses.get(item["criterion_id"]) == "cumple" else "")
        for item in failed
    ) or f"all {len(rubric_results)} rubric checks pass"
    # The format defects ride on the deterministic body check so the marker
    # keeps its fixed set of mechanical entries.
    if format_problems:
        detail = "; ".join([*([detail] if failed else []), *(f"body_format: {p}" for p in format_problems)])
    checks.append({"check": "rubric_checks", "ok": not failed and not format_problems, "detail": detail})
    checks.append(link_entry)
    mechanical_ok = all(check["ok"] for check in checks)
    waived = accepted_gaps.waived_requirements(folder, requirements)
    criteria_ok = criteria_closed(derived, requirements, waived) and requirements_accepted(requirements, waived)
    guide = _guide_input(folder, config)
    guide_binding = {"guide_sha256": _sha256_or_empty(folder / guide)} if guide else {}
    marker = {
        "schema": CONTENT_CHECK_SCHEMA,
        "body_sha256": sha256_file(body_path),
        "rubric_sha256": _sha256_or_empty(folder / rubric_plan.RUBRIC_NAME),
        # The plan without its max_words ceilings (faster-verify-loop S4): lets the
        # next --since carry sections across a ceilings-only change. Not a binding.
        "rubric_matrix_sha256": rubric_plan.rubric_matrix_sha256(folder),
        "bib_sha256": _sha256_or_empty(config.bib_path),
        # Optional binding (report-flow-hardening T11): recorded only when the
        # report declares a guide, so pre-guide markers keep their old shape.
        **guide_binding,
        "verifier": verifier,
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "criteria": derived,
        "requirements": requirements,
        # What the next incremental re-verify compares against (S3): the
        # sections these requirements were verified on, and which were carried.
        "section_sha256": section_hashes(body_text, criteria),
        "carried_criteria": sorted({item["criterion"] for item in carried}),
        # Deletion candidates: reported, never blocking.
        "unmapped_paragraphs": verification["unmapped_paragraphs"],
        # The verifier's free-text findings verbatim, plus every mechanical
        # failure so the human reads one artifact, not two.
        "findings": findings
        + [f"{check['check']}: {check['detail']}" for check in checks if not check["ok"]],
        "mechanical": checks,
        # Advisory (never a verdict input): deterministic lint plus the verifier's own, quote-checked.
        "prose_findings": prose,
        "rubric_check_results": rubric_results,
        "result": "pass" if mechanical_ok and criteria_ok else "fail",
    }
    # Raw bytes, so the snapshot hashes to body_sha256 even with CRLF line ends.
    _write_marker_atomically(folder / CHECKED_SNAPSHOT_NAME, body_path.read_bytes())
    _write_marker_atomically(
        folder / CONTENT_CHECK_NAME,
        yaml.safe_dump(marker, sort_keys=False, allow_unicode=False),
    )
    return CheckOutcome(str(marker["result"]), marker, ())


def rubric_changed_since_check(report_dir: Path) -> bool:
    """True when ``content-check.yml`` records a ``rubric_sha256`` other than the current rubric's.

    Lets ``doc_status`` name the rubric as the stale input. Never raises, never writes.
    """
    folder = Path(report_dir)
    try:
        data = read_yaml(folder / CONTENT_CHECK_NAME)
    except Exception:
        return False
    if not isinstance(data, dict) or not isinstance(data.get("rubric_sha256"), str):
        return False
    rubric_path = folder / rubric_plan.RUBRIC_NAME
    current = _sha256_or_empty(rubric_path if rubric_path.is_file() else None)
    return data["rubric_sha256"].strip().lower() != current


def content_check_state(report_dir: Path) -> str:
    """Derive the verify-phase state of a report folder without touching it.

    Exactly one of ``absent|malformed|stale|fail|pass``. A marker that cannot
    be read or is missing required keys is ``malformed``; a marker whose
    ``body_sha256``, ``rubric_sha256`` or ``bib_sha256`` no longer matches the
    folder is ``stale`` (the draft, the rubric or the bib changed since the
    check; a bounded draft edit, or a bounded heading rename, keeps the marker, see
    ``_bounded_since_check``), as is a recorded ``guide_sha256`` that no longer matches the
    guide the report declares (or the guide is gone). A marker without
    ``guide_sha256`` predates guide binding and stays valid. A marker with a
    ``verifier`` is a single-verify marker; one without is the legacy two-judge
    shape, still honored when well formed. A non-list ``judges`` field never
    crashes: under the current schema it is the old, incomplete shape
    (``stale``), under any other schema it is ``malformed``. The recorded
    ``result`` is never trusted blindly: the verdict is re-derived from the
    recorded criteria (every status ``cumple``), the recorded requirements (all
    ``found``, every criterion covered, for verifier markers), the recorded
    mechanical checks (every ``ok``) and the recorded criterion ids (equal to
    the current rubric ids), so a forged ``result: pass`` fails.
    Never raises, never writes.
    """
    folder = Path(report_dir)
    path = folder / CONTENT_CHECK_NAME
    if not path.is_file():
        return "absent"

    try:
        data = read_yaml(path)
    except Exception:
        return "malformed"
    if not isinstance(data, dict):
        return "malformed"
    verified = "verifier" in data
    if not verified and data.get("schema") == CONTENT_CHECK_SCHEMA and ("rubric_sha256" not in data or "judges" not in data or not isinstance(data.get("judges"), list) or len(data["judges"]) < 2):
        return "stale"
    for key in REQUIRED_VERIFIER_KEYS if verified else REQUIRED_MARKER_KEYS:
        if data.get(key) is None:
            return "malformed"
    if verified:
        if not isinstance(data["verifier"], dict) or data["verifier"].get("role") != "independent":
            return "malformed"
        if not isinstance(data["requirements"], list) or not data["requirements"] or not isinstance(data["unmapped_paragraphs"], list):
            return "malformed"
    else:
        if not isinstance(data["judges"], list) or len(data["judges"]) != 2 or any(not isinstance(judge, dict) or judge.get("role") != "independent" for judge in data["judges"]):
            return "malformed"
        if not isinstance(data["disagreements"], list):
            return "malformed"
    if data["schema"] != CONTENT_CHECK_SCHEMA:
        return "malformed"
    if data["result"] not in RESULT_VALUES:
        return "malformed"
    if not isinstance(data["criteria"], list) or not data["criteria"]:
        return "malformed"
    mechanical = data["mechanical"]
    expected_names = MECHANICAL_NAMES if verified else LEGACY_MECHANICAL_NAMES
    if (not isinstance(mechanical, list)
            or len(mechanical) != len(expected_names)
            or any(not isinstance(entry, dict) or type(entry.get("ok")) is not bool
                   for entry in mechanical)
            or {entry["check"] for entry in mechanical if isinstance(entry.get("check"), str)} != expected_names):
        return "malformed"

    body_path = folder / BODY_NAME
    if not body_path.is_file():
        return "malformed"
    try:
        body_hash = sha256_file(body_path)
    except OSError:
        return "malformed"
    recorded_body = str(data["body_sha256"]).strip().lower()
    if recorded_body != body_hash and not _bounded_since_check(folder, recorded_body, data):
        return "stale"

    rubric_path = folder / rubric_plan.RUBRIC_NAME
    rubric_hash = _sha256_or_empty(rubric_path if rubric_path.is_file() else None)
    if str(data["rubric_sha256"]).strip().lower() != rubric_hash:
        return "stale"

    try:
        config = ReportConfig(folder=folder, raw=read_yaml(folder / "report.yml"))
        bib_path = config.bib_path
    except Exception:
        bib_path = None
    if str(data["bib_sha256"]).strip().lower() != _sha256_or_empty(bib_path):
        return "stale"

    if data.get("guide_sha256") is not None:
        try:
            config = ReportConfig(folder=folder, raw=read_yaml(folder / "report.yml"))
            guide = _guide_input(folder, config)
        except Exception:
            guide = None
        guide_hash = _sha256_or_empty(folder / guide) if guide else ""
        if str(data["guide_sha256"]).strip().lower() != guide_hash:
            return "stale"

    criteria = data["criteria"]
    mechanical_ok = all(
        isinstance(entry, dict) and entry.get("ok") is True for entry in data["mechanical"]
    )
    try:
        planned = rubric_plan.load_rubric(folder)
        if not planned or rubric_plan.rubric_state(folder) != "valid":
            return "malformed"
    except Exception:
        return "malformed"
    if rubric_plan.count_checked_criteria(planned):
        recorded = data.get("rubric_check_results")
        expected = [(c["id"], index, check["type"])
                    for c in planned for index, check in enumerate(c.get("checks", []), start=1)]
        if not isinstance(recorded, list) or [
            (item.get("criterion_id"), item.get("check_index"), item.get("type"))
            for item in recorded if isinstance(item, dict)
        ] != expected or len(recorded) != len(expected) or any(
            not isinstance(item, dict) or item.get("ok") is not True for item in recorded
        ) or not any(
            isinstance(entry, dict) and entry.get("check") == "rubric_checks" and entry.get("ok") is True
            for entry in data["mechanical"]
        ):
            mechanical_ok = False
    recorded_ids = [str(record.get("id")) for record in criteria if isinstance(record, dict)]
    current_ids = [str(criterion.get("id")) for criterion in planned]
    ids_match = len(recorded_ids) == len(current_ids) and set(recorded_ids) == set(current_ids)
    # The waiver is read and re-validated here, never copied into the marker.
    recorded_requirements = data["requirements"] if verified else []
    waived = accepted_gaps.waived_requirements(folder, recorded_requirements) if verified else frozenset()
    criteria_ok = criteria_closed(criteria, recorded_requirements, waived)
    requirements_ok = True
    if verified:
        covered = {str(r.get("criterion")) for r in recorded_requirements if isinstance(r, dict)}
        requirements_ok = requirements_accepted(recorded_requirements, waived) and set(current_ids) <= covered
    return "pass" if criteria_ok and mechanical_ok and ids_match and requirements_ok else "fail"


def _bounded_since_check(folder: Path, recorded: str, data: dict) -> bool:
    """True when ``body.md`` differs from the checked bytes only by a bounded edit.

    The snapshot is trusted only when it hashes to the recorded ``body_sha256``.
    The edit must be bounded (``bounded_edit``: at most 40 words, no heading),
    every recorded ``found`` quote must still be in the body and the draft's
    mechanical checks must still pass on the new bytes; otherwise the verifier
    reruns as before. Accepted gaps bind the exact body, so with
    ``accepted-gaps.yml`` present any edit stales the marker. Never raises.

    Heading renames (faster-verify-loop S2, this marker only): an edit that
    renames headings is still bounded when the outline keeps its count, order
    and levels (``_headings_only_renamed``), the changed words, heading words
    included, stay within the limit, every criterion's ``section`` still
    resolves (same ``section_sha256`` keys) to the heading at the same
    position of the outline (``_section_positions``) and the rubric checks
    also pass on the new bytes.
    """
    snapshot = folder / CHECKED_SNAPSHOT_NAME
    try:
        if (folder / accepted_gaps.ACCEPTED_GAPS_NAME).exists():
            return False
        if not snapshot.is_file():
            return False
        snapshot_bytes = snapshot.read_bytes()
        if hashlib.sha256(snapshot_bytes).hexdigest() != recorded:
            return False
        old = snapshot_bytes.decode("utf-8")
        new = (folder / BODY_NAME).read_text(encoding="utf-8")
        is_bounded, words = bounded(old, new)
        renamed = False
        if not is_bounded:
            if words > LIMIT or not _headings_only_renamed(old, new):
                return False
            criteria = rubric_plan.load_rubric(folder)
            if section_hashes(old, criteria).keys() != section_hashes(new, criteria).keys():
                return False
            if _section_positions(old, criteria) != _section_positions(new, criteria):
                return False
            renamed = True
        requirements = data.get("requirements")
        if isinstance(requirements, list) and downgrade_unquoted_evidence(requirements, new)[1]:
            return False
        required = _BODY_CHECK_MECHANICAL + (("rubric_checks",) if renamed else ())
        return all(check["ok"] for check in body_check_results(folder) if check["check"] in required)
    except Exception:
        return False


def _section_positions(body_text: str, criteria: list[dict]) -> list[int | None]:
    """The heading each criterion's ``section`` resolves to, by position in the outline.

    Title matching alone cannot tell whether a rename moved a criterion onto
    other text (closing ATX hashes, a title that appears twice), so the
    resolved position is compared instead.
    """
    return [
        concision.section_position(body_text, c["section"]) if isinstance(c.get("section"), str) else None
        for c in criteria
    ]


def _headings_only_renamed(old: str, new: str) -> bool:
    """True when the headings keep their count, order and levels and only titles change.

    A position whose new title is another heading's old title is a move, not a
    rename, so swapping two headings fails. Titles are compared the way a
    criterion's ``section`` is looked up (case and accents folded), so a swap
    that also changes case or accents is still a move.
    """
    before, after = heading_outline(old), heading_outline(new)
    if [level for level, _ in before] != [level for level, _ in after]:
        return False
    was_titles = [concision._fold(title) for _, title in before]
    now_titles = [concision._fold(title) for _, title in after]
    known = set(was_titles)
    return all(was == now or now not in known for was, now in zip(was_titles, now_titles))


_BODY_CHECK_MECHANICAL = ("citations_resolve", "eligible_sources_cited")


def body_check_results(folder: Path) -> list[dict]:
    """The verification-free draft checks as ``check``/``ok``/``detail`` entries.

    One source of truth for ``--body-check`` and for ``doc_status``'s approval
    gate. Raises ``OSError``/``ValueError``/``TypeError`` when an input
    (body, rubric, report.yml, bib) is unreadable or invalid.
    """
    folder = Path(folder)
    body_text = (folder / BODY_NAME).read_text(encoding="utf-8")
    criteria = rubric_plan.load_rubric(folder)
    config = ReportConfig(folder=folder, raw=read_yaml(folder / "report.yml"))
    min_sources = effective_min_sources(config)
    mechanical = mechanical_checks(
        body_text, _read_bib(config), criteria, [], min_sources, config.uncited_bibliography
    )
    results = [check for check in mechanical if check["check"] in _BODY_CHECK_MECHANICAL]
    format_problems = draft_format_problems(body_text)
    results.append(
        {
            "check": "body_format",
            "ok": not format_problems,
            "detail": "; ".join(format_problems) or "level-1 headings present",
        }
    )
    markup = plain_text_problems(body_text)
    results.append(
        {
            "check": "plain_text",
            "ok": not markup,
            "detail": "; ".join(markup) or "plain text: only # headings and [@key] citations",
        }
    )
    failed_rubric = [item for item in rubric_checks.run_checks(folder, criteria, body_text) if not item.ok]
    results.append(
        {
            "check": "rubric_checks",
            "ok": not failed_rubric,
            "detail": "; ".join(f"{i.criterion_id} ({i.type}): {i.detail}" for i in failed_rubric)
            or "all rubric checks pass",
        }
    )
    results.extend(concision.concision_results(body_text, criteria, rubric_plan.load_max_words(folder)))
    scope_warnings = rubric_checks.section_scope_warnings(criteria, body_text)
    if scope_warnings:
        results.append({"check": "rubric_scope", "ok": True, "detail": "warning: " + "; ".join(scope_warnings)})
    return results


def _word_budget_result(folder: Path) -> dict | None:
    """The body check's ``word_budget`` entry for the current draft, or None when an input is unreadable."""
    try:
        folder = Path(folder)
        return concision.word_budget_result((folder / BODY_NAME).read_text(encoding="utf-8"),
                                            rubric_plan.load_rubric(folder), rubric_plan.load_max_words(folder))
    except (OSError, ValueError, TypeError):
        return None


def run_body_check(folder: Path) -> int:
    """Run the verification-free mechanical checks on a draft; print, never write."""
    try:
        results = body_check_results(folder)
    except (OSError, ValueError, TypeError) as exc:
        print(f"content check input error: {exc}", file=sys.stderr)
        return 2
    for check in results:
        print(f"  [{'ok' if check['ok'] else 'FAIL'}] {check['check']}: {check['detail']}")
    return 0 if all(check["ok"] for check in results) else 1


def main(argv: list[str] | None = None, fetcher: link_check.Fetcher | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the hard content check for a report folder (never edits body.md)."
    )
    parser.add_argument("folder", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--verification",
        type=Path,
        action="append",
        help=("the independent verifier's verification.yml (requirement -> evidence matrix); exactly one file; "
              "the output also prints the body check's word_budget line"),
    )
    mode.add_argument(
        "--verify-brief",
        action="store_true",
        help="print the read-only assignment for the independent verifier",
    )
    mode.add_argument(
        "--body-check",
        action="store_true",
        help="draft-time mechanical checks (format, citations, rubric checks); no verification, writes nothing",
    )
    parser.add_argument(
        "--since",
        type=Path,
        help="with --verify-brief: the previous verification.yml; re-verify only criteria whose sections changed",
    )
    args = parser.parse_args(argv)
    if args.since is not None and not args.verify_brief:
        print("content check input error: --since only applies to --verify-brief", file=sys.stderr)
        return 2
    if args.verify_brief:
        try:
            print(verify_brief(args.folder, since=args.since))
        except (ValueError, OSError) as exc:
            print(f"content check input error: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.body_check:
        return run_body_check(args.folder)  # read-only by contract: never writes timings.yml

    if len(args.verification) != 1:
        print("content check input error: exactly one verification file required: pass one --verification",
              file=sys.stderr)
        return 2
    with timings.timed(args.folder, "verify", "content_check.py"):
        outcome = run_check(args.folder, args.verification[0], fetcher=fetcher)
    if outcome.errors:
        for error in outcome.errors:
            print(f"content check input error: {error}", file=sys.stderr)
        return 2

    print(f"content check: {outcome.result}")
    for check in outcome.marker["mechanical"]:
        mark = "ok" if check["ok"] else "FAIL"
        print(f"  [{mark}] {check['check']}: {check['detail']}")
    # faster-verify-loop S3: the body check's length line, so length is never the verifier's call.
    # Printed only: the marker keeps its fixed mechanical entries and the verdict is unchanged.
    budget = _word_budget_result(args.folder)
    if budget is not None:
        print(f"  [{'ok' if budget['ok'] else 'FAIL'}] {budget['check']}: {budget['detail']}")
    for finding in outcome.marker["findings"]:
        print(f"  finding: {finding}")
    # faster-verify-loop S5: a needs_person partial is labelled apart from the fixable findings.
    for record in waiting_for_person(outcome.marker["requirements"], rubric_plan.load_needs_person(args.folder)):
        print(f"  {waiting_label(record)}")
    for paragraph in outcome.marker["unmapped_paragraphs"]:
        print(f"  unmapped paragraph (deletion candidate): {paragraph}")
    return 0 if outcome.result == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
