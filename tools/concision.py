"""Concision checks for a draft body: word budgets and padding.

No guide asks for more text, so these checks only cap: a per-section word
budget (explicit ``max_words`` per criterion, or the criterion's weight share of
the rubric's total ``max_words``), the total budget, stock filler phrases, and
a warning for paragraphs longer than ``LONG_PARAGRAPH_WORDS``. Only prose counts: headings,
tables, code, display math, images and citation keys are excluded.
"""

from __future__ import annotations

import re
import unicodedata

from markdown_image import IMAGE_PATTERN

LONG_PARAGRAPH_WORDS = 80

# Stock padding; matched case- and accent-insensitively on whole words.
FILLER_PHRASES = (
    "cabe destacar",
    "cabe mencionar",
    "cabe senalar",
    "cabe resaltar",
    "es importante destacar",
    "es importante mencionar",
    "es importante senalar",
    "es importante resaltar",
    "es importante recalcar",
    "vale la pena mencionar",
    "vale la pena destacar",
    "en resumen",
    "en definitiva",
    "sin lugar a dudas",
    "juega un papel fundamental",
    "juega un papel crucial",
    "juega un rol fundamental",
    "hoy en dia",
    "en la actualidad",
    "a lo largo de este informe",
    "it is important to note",
    "it is worth noting",
    "plays a crucial role",
    "in today's world",
)

_WORD = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*", re.UNICODE)
_CITATION = re.compile(r"\[@[^\]]*\]")
_INLINE_MATH = re.compile(r"(?<!\\)\$[^$\n]+?(?<!\\)\$")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
# Plain-text draft table: a "Tabla N. caption" line whose data lines follow as list items.
_TABLE_CAPTION = re.compile(r"^\s*(?:Tabla|Table)\s+\d+\s*[.:]", re.IGNORECASE)


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold()) if not unicodedata.combining(c))


def _closes_fence(line: str, fence: str) -> bool:
    marker = _FENCE.match(line)
    return bool(marker) and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence)


def _block_end(lines: list[str], start: int) -> int | None:
    """Index of the line closing the code fence or display math opened at
    ``start``, or None when it never closes (the block is then prose, so a
    stray opener can never hide the rest of the body from the checks)."""
    opener = lines[start]
    marker = _FENCE.match(opener)
    for index in range(start + 1, len(lines)):
        if marker and _closes_fence(lines[index], marker.group(1)):
            return index
        if not marker and "$$" in lines[index]:
            return index
    return None


def _prose_blocks(body: str) -> list[str]:
    """Paragraphs and single list items of prose, in order."""
    blocks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            blocks.append(" ".join(current))
            current.clear()

    lines = body.splitlines()
    index = 0
    in_table = False
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        index += 1
        if _TABLE_CAPTION.match(line):
            flush()
            in_table = True
            continue
        if in_table:
            if not stripped or _LIST_ITEM.match(line):
                continue
            in_table = False
        if stripped.startswith("$$") and stripped.count("$$") >= 2:
            # One-line display math: only the text after the closing $$ is prose.
            line = stripped = stripped.split("$$", 2)[2].strip()
        elif _FENCE.match(line) or stripped.startswith("$$"):
            end = _block_end(lines, index - 1)
            if end is not None:
                flush()
                index = end + 1
                continue
        if not stripped or _HEADING.match(line) or stripped.startswith("|") or stripped.startswith("<!--"):
            flush()
            continue
        if _LIST_ITEM.match(line):
            flush()
            current.append(_LIST_ITEM.sub("", line, count=1))
            continue
        current.append(stripped)
    flush()
    return blocks


def _count(text: str) -> int:
    return len(_WORD.findall(_INLINE_MATH.sub(" ", IMAGE_PATTERN.sub(" ", _CITATION.sub(" ", text)))))


def prose_words(body: str) -> int:
    return sum(_count(block) for block in _prose_blocks(body))


def section_text(body: str, title: str) -> str | None:
    """The section named ``title`` with its subsections, or None when absent."""
    lines = body.splitlines()
    start = level = None
    fence: str | None = None
    for index, line in enumerate(lines):
        marker = _FENCE.match(line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence:
            continue
        match = _HEADING.match(line)
        if not match:
            continue
        depth = len(match.group(1))
        if start is not None and depth <= level:
            return "\n".join(lines[start:index])
        if start is None and _fold(match.group(2).strip()) == _fold(title.strip()):
            start, level = index + 1, depth
    return "\n".join(lines[start:]) if start is not None else None


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def section_budgets(criteria: list[dict], total: int | None) -> dict[str, int]:
    """Word budget per mapped section.

    A criterion's budget is its explicit ``max_words``; otherwise, when the
    rubric sets a total and every criterion has a weight, its weight share of
    the total. Criteria mapped to the same section add up.
    """
    weights = [c.get("weight") for c in criteria]
    shareable = _positive_int(total) and bool(criteria) and all(
        isinstance(w, (int, float)) and not isinstance(w, bool) and w > 0 for w in weights
    )
    weight_sum = sum(weights) if shareable else 0
    budgets: dict[str, int] = {}
    for criterion in criteria:
        section = criterion.get("section")
        if not isinstance(section, str):
            continue
        explicit = criterion.get("max_words")
        if _positive_int(explicit):
            budget = explicit
        elif shareable:
            budget = round(total * criterion["weight"] / weight_sum)
        else:
            continue
        budgets[section] = budgets.get(section, 0) + budget
    return budgets


def budget_problems(body: str, criteria: list[dict], total: int | None) -> list[str]:
    problems = []
    for section, budget in section_budgets(criteria, total).items():
        text = section_text(body, section)
        if text is None:
            continue
        count = prose_words(text)
        if count > budget:
            problems.append(f"section '{section}' has {count} prose words ({count} > {budget})")
    if _positive_int(total):
        count = prose_words(body)
        if count > total:
            problems.append(f"total prose words {count} > {total}")
    return problems


def filler_problems(body: str) -> list[str]:
    found = []
    for block in _prose_blocks(body):
        folded = _fold(block)
        for phrase in FILLER_PHRASES:
            if re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", folded):
                found.append(f"'{phrase}' in: {block[:60]}")
    return found


def long_paragraph_problems(body: str, limit: int = LONG_PARAGRAPH_WORDS) -> list[str]:
    problems = []
    for block in _prose_blocks(body):
        count = _count(block)
        if count > limit:
            problems.append(f"{count} words (> {limit}): {block[:60]}")
    return problems


def concision_results(body: str, criteria: list[dict], total: int | None) -> list[dict]:
    """Blocking budget and filler checks plus an advisory paragraph-length warning."""
    entries = (
        ("word_budget", budget_problems(body, criteria, total), "within the word budget (or none set)"),
        ("filler_phrases", filler_problems(body), "no stock filler phrases"),
    )
    results = [{"check": name, "ok": not problems, "detail": "; ".join(problems) or ok} for name, problems, ok in entries]
    long = long_paragraph_problems(body)
    results.append({"check": "long_paragraphs", "ok": True,
                    "detail": "warning: review readability; " + "; ".join(long) if long
                    else f"no paragraph over {LONG_PARAGRAPH_WORDS} words"})
    return results
