"""Concision checks for a draft body: word budgets and padding.

No guide asks for more text, so these checks only cap: a per-section word
budget (explicit ``max_words`` per criterion, or the criterion's weight share of
the rubric's total ``max_words``), the total budget, stock filler phrases, and
a warning for paragraphs longer than ``LONG_PARAGRAPH_WORDS``. Only prose counts: headings,
tables, code, display math, images and citation keys are excluded.

``prose_findings`` adds advisory text-quality lint (empty openers, wordy phrases,
stacked connectors, repeated sentence/paragraph starts, repeated word runs across
paragraphs, overlong sentences). Only a formulaic opener in the conclusions section
blocks; every other finding warns, because repeated technical terms are legitimate.
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

MAX_PROSE_FINDINGS = 20
LONG_SENTENCE_WORDS = 35
REPEATED_RUN_WORDS = 7
REPEATED_START_RUN = 3
PROSE_KINDS = ("repeticion", "circular", "ambiguo", "relleno", "registro")

# Sentence openers that say nothing; matched at the start of a sentence only.
EMPTY_OPENERS = (
    "como es sabido",
    "es bien sabido",
    "es de todos conocido",
    "como todos sabemos",
    "como se sabe",
    "desde tiempos inmemoriales",
    "desde el inicio de los tiempos",
    "en el mundo actual",
    "en el mundo de hoy",
    "en la sociedad actual",
)

# Wordy or redundant wording, matched anywhere on whole words, with the fix to suggest.
WORDY_PHRASES = {
    "en base a": "use 'con base en' or 'segun'",
    "debido al hecho de que": "use 'porque'",
    "subir arriba": "'subir' already implies up",
    "bajar abajo": "'bajar' already implies down",
    "entrar adentro": "'entrar' already implies in",
    "salir afuera": "'salir' already implies out",
    "volver a repetir": "use 'repetir'",
    "lapso de tiempo": "use 'lapso' or 'intervalo'",
}

CONNECTORS = (
    "por lo tanto", "por tanto", "por consiguiente", "en consecuencia", "por ende", "sin embargo",
    "no obstante", "ademas", "asimismo", "igualmente", "de igual manera", "de igual forma",
    "por otro lado", "por otra parte", "en cambio", "ahora bien", "en ese sentido",
)

# Openers a conclusions section must not start a sentence with.
FORMULAIC_CONCLUSIONS = (
    "se concluye", "se puede concluir", "podemos concluir", "en conclusion", "a modo de conclusion",
    "para concluir", "como conclusion",
)

_CONNECTOR = "|".join(sorted(map(re.escape, CONNECTORS), key=len, reverse=True))
_STACKED = re.compile(rf"(?<!\w)(?:{_CONNECTOR})\s*,?\s*(?:{_CONNECTOR})(?!\w)")
_SENTENCE_END = re.compile(r"(?<=[.!?…])[\"»”)]*\s+(?=[¿¡\"«“(\[]*[A-ZÁÉÍÓÚÑÜ])")
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
    return [block for _heading, _number, block in _located_blocks(body)]


def _located_blocks(body: str) -> list[tuple[str, int, str]]:
    """Prose blocks as ``(heading, number within that heading, text)``."""
    blocks: list[tuple[str, int, str]] = []
    current: list[str] = []
    heading = ""
    counts: dict[str, int] = {}

    def flush() -> None:
        if current:
            counts[heading] = counts.get(heading, 0) + 1
            blocks.append((heading, counts[heading], " ".join(current)))
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
            title = _HEADING.match(line)
            if title:
                heading = title.group(2).strip()
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


def heading_lines(body: str) -> dict[int, tuple[int, str]]:
    """The heading lines ``section_text`` sees: line index -> ``(level, folded title)``.

    Fenced blocks are skipped and titles are folded exactly as the section
    lookup does, so these are the only lines a criterion's ``section`` can
    resolve to.
    """
    found: dict[int, tuple[int, str]] = {}
    fence: str | None = None
    for index, line in enumerate(body.splitlines()):
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
        if match:
            found[index] = (len(match.group(1)), _fold(match.group(2).strip()))
    return found


def section_headings(body: str) -> list[tuple[int, str]]:
    """The headings ``section_text`` sees, in order, as ``(level, folded title)``."""
    return list(heading_lines(body).values())


def section_position(body: str, title: str) -> int | None:
    """Ordinal of the heading ``section_text`` resolves ``title`` to, or None when absent.

    Two bodies whose ``section_headings`` have the same levels resolve a title
    to the same section exactly when the positions are equal.
    """
    wanted = _fold(title.strip())
    for position, (_, folded) in enumerate(section_headings(body)):
        if folded == wanted:
            return position
    return None


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


def _mask(text: str) -> str:
    """``text`` with citations, images and inline math blanked, offsets unchanged."""
    for pattern in (_CITATION, IMAGE_PATTERN, _INLINE_MATH):
        text = pattern.sub(lambda m: " " * len(m.group()), text)
    return text


def _sentences(block: str) -> list[tuple[int, int]]:
    """Character spans of the sentences of ``block``."""
    spans, start = [], 0
    for match in _SENTENCE_END.finditer(block):
        spans.append((start, match.start()))
        start = match.end()
    spans.append((start, len(block)))
    return [(a, b) for a, b in spans if block[a:b].strip()]


def _slice(block: str, folded: str, start: int, end: int) -> str:
    """The original text for a span found in the folded text (same offsets when lengths agree)."""
    return block[start:end] if len(folded) == len(block) else folded[start:end]


def _words_of(text: str, spans: tuple[int, int] | None = None) -> list[re.Match]:
    start, end = spans or (0, len(text))
    return list(_WORD.finditer(text, start, end))


def _finding(heading: str, number: int, kind: str, pattern: str, quote: str, fix: str) -> dict:
    where = f"{heading}, paragraph {number}" if heading else f"document start, paragraph {number}"
    return {"location": where, "kind": kind, "quote": " ".join(quote.split()), "fix": fix, "pattern": pattern}


def _is_conclusion(heading: str) -> bool:
    return _fold(heading).startswith("conclusi")


def _sentence_findings(heading: str, number: int, block: str) -> list[dict]:
    found = []
    masked = _mask(block)
    folded = _fold(masked)
    sentences = _sentences(masked)
    for start, end in sentences:
        head = folded[start:end]
        words = _words_of(masked, (start, end))
        for phrase in EMPTY_OPENERS:
            if head.startswith(phrase):
                found.append(_finding(heading, number, "relleno", "empty_opener",
                                      _slice(block, folded, start, start + len(phrase)),
                                      "delete the opener and start with the content"))
        if _is_conclusion(heading):
            for phrase in FORMULAIC_CONCLUSIONS:
                if head.startswith(phrase):
                    found.append(_finding(heading, number, "registro", "formulaic_conclusion",
                                          _slice(block, folded, start, start + len(phrase)),
                                          "state the finding directly instead of announcing a conclusion"))
        if len(words) > LONG_SENTENCE_WORDS:
            found.append(_finding(heading, number, "ambiguo", "long_sentence",
                                  " ".join(block[w.start():w.end()] for w in words[:8]),
                                  f"{len(words)} words (> {LONG_SENTENCE_WORDS}): split into shorter sentences"))
    for match in _STACKED.finditer(folded):
        found.append(_finding(heading, number, "relleno", "stacked_connector",
                              _slice(block, folded, match.start(), match.end()), "keep a single connector"))
    for phrase, fix in WORDY_PHRASES.items():
        for match in re.finditer(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", folded):
            found.append(_finding(heading, number, "relleno", "wordy_phrase",
                                  _slice(block, folded, match.start(), match.end()), fix))
    starts = [tuple(_fold(w.group()) for w in _words_of(masked, span)[:2]) for span in sentences]
    found.extend(_repeated_starts(heading, number, starts, [block[a:b] for a, b in sentences], "sentence"))
    return found


def _repeated_starts(heading: str, number: int, keys: list[tuple], texts: list[str], unit: str) -> list[dict]:
    found, index = [], 0
    while index < len(keys):
        run = index
        while run + 1 < len(keys) and keys[run + 1] == keys[index] and len(keys[index]) == 2:
            run += 1
        if run - index + 1 >= REPEATED_START_RUN:
            quote = " ".join(texts[index].split()[:2])
            found.append(_finding(heading, number, "repeticion", "repeated_start", quote,
                                  f"{run - index + 1} consecutive {unit}s start the same way: vary or merge them"))
        index = run + 1
    return found


def _repeated_runs(blocks: list[tuple[str, int, str]]) -> list[dict]:
    """Word runs of at least ``REPEATED_RUN_WORDS`` that recur in a later paragraph."""
    seen: set[tuple[str, ...]] = set()
    found = []
    for heading, number, block in blocks:
        masked = _mask(block)
        words = _words_of(masked)
        keys = [_fold(w.group()) for w in words]
        grams = [tuple(keys[i:i + REPEATED_RUN_WORDS]) for i in range(len(keys) - REPEATED_RUN_WORDS + 1)]
        index = 0
        while index < len(grams):
            if grams[index] not in seen:
                index += 1
                continue
            end = index
            while end + 1 < len(grams) and grams[end + 1] in seen:
                end += 1
            last = min(end + REPEATED_RUN_WORDS - 1, index + 11)
            found.append(_finding(heading, number, "repeticion", "repeated_ngram",
                                  block[words[index].start():words[last].end()],
                                  "this wording already appeared earlier: cut it or say something new"))
            index = end + 1
        seen.update(grams)
    return found


def prose_findings(body: str, limit: int = MAX_PROSE_FINDINGS) -> list[dict]:
    """Advisory text-quality findings: ``location``, ``kind``, ``quote``, ``fix`` and ``pattern``.

    ``quote`` is text of the draft. Blocking openers in the conclusions section
    come first so the cap never hides them.
    """
    blocks = _located_blocks(body)
    found: list[dict] = []
    for heading, number, block in blocks:
        found.extend(_sentence_findings(heading, number, block))
    keys = [tuple(_fold(w.group()) for w in _words_of(_mask(block))[:2]) for _h, _n, block in blocks]
    for item in _repeated_starts("", 0, keys, [block for _h, _n, block in blocks], "paragraph"):
        heading, number, _block = next(b for b in blocks if " ".join(b[2].split()).startswith(item["quote"]))
        found.append({**item, "location": f"{heading}, paragraph {number}" if heading else item["location"]})
    found.extend(_repeated_runs(blocks))
    found.sort(key=lambda item: item["pattern"] != "formulaic_conclusion")
    return found[:limit]


def formulaic_conclusion_problems(findings: list[dict]) -> list[str]:
    return [f"'{item['quote']}' opens a sentence in {item['location']}"
            for item in findings if item["pattern"] == "formulaic_conclusion"]


def _prose_findings_detail(findings: list[dict]) -> str:
    if not findings:
        return "no prose findings"
    shown = "; ".join(f"{item['pattern']} '{item['quote'][:40]}'" for item in findings[:5])
    more = f"; +{len(findings) - 5} more" if len(findings) > 5 else ""
    return f"warning: review wording ({len(findings)} finding(s)); {shown}{more}"


def word_budget_result(body: str, criteria: list[dict], total: int | None) -> dict:
    """The ``word_budget`` entry: prose words (tables excluded) against the rubric's ``max_words``."""
    problems = budget_problems(body, criteria, total)
    return {"check": "word_budget", "ok": not problems,
            "detail": "; ".join(problems) or "within the word budget (or none set)"}


def concision_results(body: str, criteria: list[dict], total: int | None) -> list[dict]:
    """Blocking budget, filler and formulaic-conclusion checks plus advisory warnings."""
    findings = prose_findings(body)
    filler = filler_problems(body)
    results = [word_budget_result(body, criteria, total),
               {"check": "filler_phrases", "ok": not filler, "detail": "; ".join(filler) or "no stock filler phrases"}]
    long = long_paragraph_problems(body)
    results.append({"check": "long_paragraphs", "ok": True,
                    "detail": "warning: review readability; " + "; ".join(long) if long
                    else f"no paragraph over {LONG_PARAGRAPH_WORDS} words"})
    # Appended after the original three so consumers reading them by position keep working.
    formulaic = formulaic_conclusion_problems(findings)
    results.append({"check": "formulaic_conclusion", "ok": not formulaic,
                    "detail": "; ".join(formulaic) or "no formulaic conclusion openers"})
    results.append({"check": "prose_findings", "ok": True, "detail": _prose_findings_detail(findings)})
    return results
