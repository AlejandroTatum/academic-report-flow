"""Read-only deterministic assertions over a planned rubric and draft."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from validate_ieee_refs import cited_keys

# The tolerances the deterministic checks apply, stated once so the judge brief
# (content_check.judge_brief) quotes this constant instead of its own copy: a
# PASS above settles exactly these properties and nothing more.
TOLERANCE_RULES = (
    "verbatim_from_guide normalizes whitespace and allows only the first letter to differ in case "
    "(sentence-initial capitalization is allowed); contains is case-insensitive; section headings "
    "match case- and accent-insensitively."
)


@dataclass(frozen=True)
class CheckResult:
    criterion_id: str
    check_index: int
    type: str
    ok: bool
    detail: str


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold()) if not unicodedata.combining(c))


def _section(body: str, title: str) -> str | None:
    lines = body.splitlines()
    start = None
    level = 0
    fence = None
    for index, line in enumerate(lines):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence:
            continue
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        setext = re.match(r"^\s*(?:={3,}|-{3,})\s*$", line)
        heading = match.group(1).strip().rstrip("# ").strip() if match else lines[index - 1].strip() if setext and index and lines[index - 1].strip() else None
        if heading:
            boundary = index - 1 if setext else index
            depth = len(line) - len(line.lstrip("#")) if match else (1 if line.strip()[0] == "=" else 2)
            # A section keeps its subsections; it ends at a same or higher level heading.
            if start is not None and depth <= level:
                return "\n".join(lines[start:boundary])
            if start is None and _fold(heading.strip()) == _fold(title.strip()):
                start, level = index + 1, depth
    return "\n".join(lines[start:]) if start is not None else None


def _words(text: str) -> set[str]:
    stop = {"sobre", "entre", "desde", "hasta", "these", "those", "their", "there", "which", "where", "para", "como", "todos", "todas", "through"}
    return {word for word in re.findall(r"[^\W\d_]+", _fold(text)) if len(word) >= 5 and word not in stop}


def _evaluate(folder: Path, check: dict, body: str) -> tuple[bool, str]:
    kind = check["type"]
    known = {"heading_present", "contains", "matches", "verbatim_from_guide", "ordered_list", "min_citations", "figure_referenced", "link_present", "keywords_from_section"}
    if kind not in known:
        return False, f"unknown check type '{kind}'"
    if kind == "heading_present":
        ok = _section(body, check["section"]) is not None
        return ok, f"heading '{check['section']}' {'present' if ok else 'missing'}"
    scope = body if "section" not in check else _section(body, check["section"])
    note = ""
    if scope is None and kind in ("contains", "matches"):
        # A renamed heading must not fail a text check: widen to the whole draft.
        scope, note = body, f" (section '{check['section']}' missing, checked document-wide)"
    if scope is None:
        return False, f"section '{check['section']}' missing"
    if kind == "contains":
        ok = check["text"].casefold() in scope.casefold()
        return ok, f"text '{check['text']}' {'found' if ok else 'missing'}{note}"
    if kind == "matches":
        ok = re.search(check["pattern"], scope) is not None
        return ok, f"pattern '{check['pattern']}' {'matched' if ok else 'missing'}{note}"
    if kind == "verbatim_from_guide":
        source = Path(check["source"])
        if source.is_absolute() or ".." in source.parts:
            return False, "source must be relative to report folder"
        try:
            guide = (folder / source).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return False, f"guide '{source}' missing or unreadable"
        needle = " ".join(check["text"].split())
        # Only the first character may differ in case; interior spelling and
        # capitalization remain verbatim after whitespace normalization.
        def matches_first_letter(text: str) -> bool:
            normalized = " ".join(text.split())
            return needle in normalized or (bool(needle) and any(
                normalized[index + 1:index + len(needle)] == needle[1:]
                and normalized[index].casefold() == needle[0].casefold()
                and (index == 0 or not normalized[index - 1].isalnum())
                for index in range(len(normalized) - len(needle) + 1)
            ))

        in_guide = matches_first_letter(guide)
        in_body = matches_first_letter(scope)
        return in_guide and in_body, f"verbatim text in guide={in_guide}, section={in_body}"
    if kind == "ordered_list":
        items = re.findall(r"^\s*\d+[.)]\s+\S", scope, re.MULTILINE)
        return len(items) >= check.get("min_items", 1), f"{len(items)}/{check.get('min_items', 1)} ordered items"
    if kind == "min_citations":
        count = len(cited_keys(scope))
        return count >= check["count"], f"{count}/{check['count']} distinct citations"
    if kind == "figure_referenced":
        # A plain-text draft names a figure as `Figura: caption (path)` (issue #96).
        count = len(re.findall(r"!\[[^]]*\]\([^)]+\)", scope)) + len(
            re.findall(r"(?im)^\s*(?:figura|figure)\b[^\n]*\([^)\s]+\.[A-Za-z0-9]+\)\s*$", scope)
        )
        return count >= check.get("count", 1), f"{count}/{check.get('count', 1)} figures"
    if kind == "link_present":
        # A plain-text draft writes bare URLs (issue #96).
        links = re.findall(r"<https?://[^>]+>|(?<!!)\[[^]]+\]\(https?://[^)]+\)|(?<![<(])https?://[^\s<>)\]]+", scope)
        matched = [link for link in links if "pattern" not in check or re.search(check["pattern"], link)]
        return bool(matched), f"{len(matched)} matching links"
    if kind == "keywords_from_section":
        origin = _section(body, check["from_section"])
        if origin is None:
            return False, f"source section '{check['from_section']}' missing"
        common = _words(origin) & _words(scope)
        return len(common) >= check.get("min", 2), f"{len(common)}/{check.get('min', 2)} shared keywords: {', '.join(sorted(common))}"
    return False, f"unknown check type '{kind}'"


def section_scope_warnings(criteria: list[dict], body_text: str) -> list[str]:
    """Warn about ``contains`` checks scoped to a heading the draft does not have.

    Checks are document-wide unless the property must live in one section; a
    scope that breaks when the headings are restructured only costs a round.
    """
    return [
        f"{criterion['id']} contains check {index} is scoped to section '{check['section']}', "
        "which is not in body.md; drop `section:` (document-wide) unless the property must live there"
        for criterion in criteria
        for index, check in enumerate(criterion.get("checks", []), start=1)
        if check.get("type") == "contains" and isinstance(check.get("section"), str)
        and _section(body_text, check["section"]) is None
    ]


def run_checks(report_dir: Path, criteria: list[dict], body_text: str) -> list[CheckResult]:
    """Evaluate checks in rubric order without writing or changing the draft."""
    results = []
    for criterion in criteria:
        for index, check in enumerate(criterion.get("checks", []), start=1):
            try:
                ok, detail = _evaluate(Path(report_dir), check, body_text)
            except (re.error, KeyError, TypeError, ValueError) as exc:
                ok, detail = False, f"invalid check: {exc}"
            results.append(CheckResult(criterion["id"], index, check["type"], ok, detail))
    return results
