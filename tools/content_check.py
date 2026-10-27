#!/usr/bin/env python3
"""The hard content check: record the verifier's matrix, derive the verdict.

verify-concise-drafts T6 replaces the two independent judges with ONE
independent read-only verifier. It scores nothing: it fills a requirement ->
evidence matrix (``verification.yml``, schema ``academic.verification/v1``):
``requirements: [{criterion, requirement, status: found|missing, location,
evidence}]`` plus ``unmapped_paragraphs`` (deletion candidates) and free-text
``findings``. ``found`` needs ``evidence``, an exact quote from ``body.md``.
This tool never generates the matrix; it validates it against the plan
(``tools/rubric_plan.py``), downgrades any ``found`` requirement whose quote is
not in ``body.md`` (whitespace-normalized) to ``missing`` with a finding, derives
each criterion as ``cumple`` (all its requirements found) or ``falta``, adds the
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
current rubric ids) -- a forged ``result: pass`` fails. Markers written by the
old two-judge flow (``judges``/``disagreements``) stay readable and valid.

CLI: ``python tools/content_check.py <report-folder> --verification <file>``
exits 0 on pass, 1 on fail, 2 on usage/input error; ``--verify-brief`` prints the
verifier's assignment.
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
import yaml
from approval_marker import BODY_NAME, sha256_file
from report_config import ReportConfig, read_yaml
from validate_report import SECTION_SPECS, bold_pseudo_heading_lines, section_structure_validation
from source_count import MIN_ACADEMIC_SOURCES, all_entry_keys, effective_min_sources, eligible_entry_keys
from validate_ieee_refs import bib_keys, cited_keys

CONTENT_CHECK_NAME = "content-check.yml"
CONTENT_CHECK_SCHEMA = "academic.content-check/v1"
VERIFICATION_SCHEMA = "academic.verification/v1"
REQUIREMENT_STATUSES = ("found", "missing")
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


def _incremental_section(since: Path, criteria: list[dict], hashes: dict[str, str], rubric_hash: str) -> str:
    """Brief block for a re-verify after an edit (verify-concise-drafts T7, S2).

    A criterion whose mapped section hashes the same as in the previous
    verification is carried over verbatim; the verifier re-checks only the
    rest. Carried quotes are still checked against body.md by run_check.
    """
    previous, errors = parse_verification(since)
    if errors:
        raise ValueError(errors[0])
    name = Path(since).name
    if previous["rubric_sha256"] != rubric_hash:
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
    rubric is unchanged and its mapped section hashes the same as when the
    previous marker verified it, so an incremental answer lists only what
    changed. Legacy markers without ``section_sha256`` carry nothing.
    """
    try:
        previous = yaml.safe_load((folder / CONTENT_CHECK_NAME).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return []
    if (not isinstance(previous, dict) or previous.get("schema") != CONTENT_CHECK_SCHEMA
            or previous.get("rubric_sha256") != rubric_hash
            or not isinstance(previous.get("section_sha256"), dict)
            or not isinstance(previous.get("requirements"), list)):
        return []
    current = section_hashes(body_text, criteria)
    old = previous["section_sha256"]
    keep = {cid for cid, digest in current.items() if cid not in answered and old.get(cid) == digest}
    records = [record for record in previous["requirements"] if _carryable(record, keep)]
    return [{key: str(record.get(key) or "") for key in ("criterion", "requirement", "status", "location", "evidence")}
            for record in records]


def _carryable(record: object, keep: set[str]) -> bool:
    """The marker is now an input, so a carried record meets parse_verification's
    rules: a kept criterion, a non-blank demand, a valid status and, when found,
    a non-blank quote (an empty quote would pass the in-body check)."""
    if not isinstance(record, dict):
        return False
    criterion, demand, evidence = record.get("criterion"), record.get("requirement"), record.get("evidence")
    if not isinstance(criterion, str) or criterion not in keep:
        return False
    if not isinstance(demand, str) or not demand.strip() or record.get("status") not in REQUIREMENT_STATUSES:
        return False
    return record["status"] != "found" or (isinstance(evidence, str) and bool(evidence.strip()))


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
                          "status": "found|missing", "location": "<where in body.md>",
                          "evidence": "<exact quote from body.md; required when found>"}],
        "unmapped_paragraphs": ["<first words of a paragraph that answers no requirement>"],
        "findings": [],
    }
    incremental = (_incremental_section(since, criteria, schema["section_sha256"], schema["rubric_sha256"])
                   if since is not None else "")
    return ("You are an independent read-only verifier. Verify only from these inputs; "
            "do not use the drafting conversation or any other files. Do not edit any file.\n"
            "Never score or grade. For each rubric criterion list the requirements the guide and rubric "
            "demand and mark each found or missing. Split a plural demand into one requirement per item "
            "(one per part, link, table or question: \"Wokwi links\" for parts A-E is five requirements). "
            "Quote evidence exactly: it must be a verbatim "
            "substring of body.md. When you cannot quote it, mark the requirement missing; never write "
            "that something seems to comply. Check data (numbers, names, links per part) against the guide. "
            "Links are fetched by the tool. List paragraphs that answer no requirement under "
            "unmapped_paragraphs (deletion candidates). Independently review the whole draft for "
            "semantic repetition, circular explanations, ambiguity and missing necessary context; "
            "report specific locations and suggested corrections in findings, without rewriting. "
            "Length and filler checks cannot establish semantic concision. Repeat this whole-draft "
            "review even during incremental verification; findings are advisory, not a score.\n"
            f"Citations [@key] in body.md render in {config.citation_style.upper()} format at build time from sources.bib; citation keys are expected, not a formatting defect. Check that cited keys exist in sources.bib instead.\n"
            + _criteria_section(criteria)
            + incremental
            + _already_run_checks_section(folder, criteria, body_text)
            + "Allowed input paths (absolute):\n"
            + "\n".join(str(folder / name) for name in inputs)
            + "\nReturn only verification YAML using this schema; allowed statuses: found|missing.\n"
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
        if status == "found" and (not isinstance(evidence, str) or not evidence.strip()):
            errors.append(f"{name} requirement {index} (criterion '{criterion}') is found but has no evidence quote")
            continue
        requirements.append(
            {
                "criterion": criterion,
                "requirement": demand,
                "status": status,
                "location": _text_or_none(record.get("location")) or "",
                "evidence": _text_or_none(evidence) or "",
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
        },
        errors,
    )


def downgrade_unquoted_evidence(requirements: list[dict], body_text: str) -> tuple[list[dict], list[str]]:
    """The anti-hallucination rule: ``found`` needs a quote that body.md really holds.

    A ``found`` requirement whose evidence is absent from body.md
    (whitespace-normalized, case-sensitive) becomes ``missing`` and yields a
    finding naming its criterion and the quote; nothing else changes.
    """
    normalized_body = " ".join(body_text.split())
    result: list[dict] = []
    findings: list[str] = []
    for record in requirements:
        if record["status"] == "found" and " ".join(record["evidence"].split()) not in normalized_body:
            findings.append(
                f"evidence not found in body.md: criterion '{record['criterion']}': requirement "
                f"'{record['requirement']}' downgraded to missing; quote: '{record['evidence']}'"
            )
            record = {**record, "status": "missing"}
        result.append(record)
    return result, findings


def derive_criteria(criteria: list[dict], requirements: list[dict]) -> list[dict]:
    """Per-criterion ``cumple`` (every requirement found) or ``falta``; never ``flojo``."""
    derived = []
    for criterion in criteria:
        cid = str(criterion.get("id"))
        own = [r for r in requirements if r["criterion"] == cid]
        found = sum(1 for r in own if r["status"] == "found")
        derived.append(
            {
                "id": cid,
                "status": "cumple" if own and found == len(own) else "falta",
                "where": "; ".join(dict.fromkeys(r["location"] for r in own if r["location"])),
                "note": f"{found}/{len(own)} requirements found",
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


def _write_marker_atomically(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` so readers never see a half-written marker.

    The temp file sits beside the target (same filesystem, so ``os.replace`` is
    atomic) and is removed even when the replace fails, so a crashed check
    never leaves a ``content-check.yml.tmp`` behind for the next run to trip on.
    """
    tmp = path.with_name(path.name + ".tmp")
    try:
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
    findings = list(dict.fromkeys([*verification["findings"], *downgrade_findings, *link_warnings]))
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
    criteria_ok = all(item["status"] == "cumple" for item in derived)
    guide = _guide_input(folder, config)
    guide_binding = {"guide_sha256": _sha256_or_empty(folder / guide)} if guide else {}
    marker = {
        "schema": CONTENT_CHECK_SCHEMA,
        "body_sha256": sha256_file(body_path),
        "rubric_sha256": _sha256_or_empty(folder / rubric_plan.RUBRIC_NAME),
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
        "rubric_check_results": rubric_results,
        "result": "pass" if mechanical_ok and criteria_ok else "fail",
    }
    _write_marker_atomically(
        folder / CONTENT_CHECK_NAME,
        yaml.safe_dump(marker, sort_keys=False, allow_unicode=False),
    )
    return CheckOutcome(str(marker["result"]), marker, ())


def content_check_state(report_dir: Path) -> str:
    """Derive the verify-phase state of a report folder without touching it.

    Exactly one of ``absent|malformed|stale|fail|pass``. A marker that cannot
    be read or is missing required keys is ``malformed``; a marker whose
    ``body_sha256``, ``rubric_sha256`` or ``bib_sha256`` no longer matches the
    folder is ``stale`` (the draft, the rubric or the bib changed since the
    check), as is a recorded ``guide_sha256`` that no longer matches the
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
    if str(data["body_sha256"]).strip().lower() != body_hash:
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
    criteria_ok = all(
        isinstance(record, dict) and record.get("status") == "cumple" for record in criteria
    )
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
    requirements_ok = True
    if verified:
        covered = {str(r.get("criterion")) for r in data["requirements"] if isinstance(r, dict)}
        requirements_ok = all(
            isinstance(r, dict) and r.get("status") == "found" for r in data["requirements"]
        ) and set(current_ids) <= covered
    return "pass" if criteria_ok and mechanical_ok and ids_match and requirements_ok else "fail"


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
        help="the independent verifier's verification.yml (requirement -> evidence matrix); exactly one file",
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
        return run_body_check(args.folder)

    if len(args.verification) != 1:
        print("content check input error: exactly one verification file required: pass one --verification",
              file=sys.stderr)
        return 2
    outcome = run_check(args.folder, args.verification[0], fetcher=fetcher)
    if outcome.errors:
        for error in outcome.errors:
            print(f"content check input error: {error}", file=sys.stderr)
        return 2

    print(f"content check: {outcome.result}")
    for check in outcome.marker["mechanical"]:
        mark = "ok" if check["ok"] else "FAIL"
        print(f"  [{mark}] {check['check']}: {check['detail']}")
    for finding in outcome.marker["findings"]:
        print(f"  finding: {finding}")
    for paragraph in outcome.marker["unmapped_paragraphs"]:
        print(f"  unmapped paragraph (deletion candidate): {paragraph}")
    return 0 if outcome.result == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
