"""Deterministic formatting for the typeset phase (``typeset.py auto``).

Pure text functions, no file access. ``auto_format`` applies only the
conversions that need no judgement: runs of ``- a; b; c`` lines become pipe
tables, ``Figura: caption (path)`` lines become images and bare URLs become
autolinks. It never adds or removes a word of the body: the draft holds no
column names, so a table gets an empty header row. ``pending`` lists what is
left for the agent, and ``empty_table_headers`` backs the ``table_headers``
check that keeps a build waiting until those columns are named.
"""
from __future__ import annotations

import re

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_INDENTED_CODE_RE = re.compile(r"^(?: {4}|\t)")
_FIGURE_RE = re.compile(
    r"^Figura:\s*(?P<caption>.+?)\s*\((?P<path>[^()\s]+\.(?:png|jpe?g|pdf|svg))\)\s*$", re.IGNORECASE
)
_ROW_RE = re.compile(r"^- (?P<cells>.*;.*)$")
_URL_RE = re.compile(r"https?://[^\s<>\[\]`\"«»“”]+")
_NUMERIC_RE = re.compile(r"^[+-]?\d[\d.,]*\s*%?$")
_EMPTY_HEADER_RE = re.compile(r"^\|(\s*\|)+\s*$")
_SEPARATOR_RE = re.compile(r"^\|(\s*:?-+:?\s*\|)+\s*$")
_ASSIGNMENT_RE = re.compile(r"\S\s=\s\S")
_OPERATOR_RE = re.compile(r"[/·×^√∑|]")
_MIN_TABLE_CELLS = 3
_TRAILING_PUNCTUATION = ".,;:!?"
# Stripped from the end of a URL only when the same kind of mark opens right before it.
_WRAPPING_MARKS = "*_'‘’"


def _code_flags(lines: list[str]) -> list[bool]:
    """Per line, whether it is code: a fence line, inside a fenced block, or indented code.

    A fenced block closes only with the character that opened it, repeated at
    least as many times.
    """
    flags = []
    opened = ""
    for line in lines:
        fence = _FENCE_RE.match(line)
        if opened:
            flags.append(True)
            if fence and fence[1][0] == opened[0] and len(fence[1]) >= len(opened):
                opened = ""
        elif fence:
            opened = fence[1]
            flags.append(True)
        else:
            flags.append(bool(_INDENTED_CODE_RE.match(line)))
    return flags


def _split_cells(text: str) -> list[str]:
    """Split on the ``;`` that separate cells.

    A separator is followed by a space or ends the line, so the ``;`` of a URL
    (``a;b=1``) is not one; inside square brackets (``[@a; @b]``) or inline
    code it never is.
    """
    cells = [""]
    depth = 0
    code = False
    for position, char in enumerate(text):
        if char == "`":
            code = not code
        elif not code and char == "[":
            depth += 1
        elif not code and char == "]" and depth:
            depth -= 1
        if char == ";" and not code and not depth and text[position + 1 : position + 2] in ("", " ", "\t"):
            cells.append("")
        else:
            cells[-1] += char
    return [cell.strip() for cell in cells]


def _cells(line: str) -> list[str] | None:
    """The cells of a list line that holds a ``;``, or ``None`` for any other line.

    A line whose ``;`` separate nothing is one cell: it still belongs to the
    run it sits in, which is then not uniform.
    """
    match = _ROW_RE.match(line)
    return _split_cells(match["cells"]) if match else None


def _row_run(lines: list[str], flags: list[bool], start: int) -> list[list[str]]:
    """The cells of the consecutive ``- a; b`` lines that begin at ``start``."""
    rows = []
    for line, is_code in zip(lines[start:], flags[start:]):
        cells = None if is_code else _cells(line)
        if cells is None:
            break
        rows.append(cells)
    return rows


def _table_rows(rows: list[list[str]]) -> list[list[str]] | None:
    """The rows as a table, or ``None`` when the run is not one.

    A table is a run of two or more rows that all hold the same number of
    cells, three or more. A last cell that is empty in every row comes from a
    trailing ``;`` and is not a column.
    """
    if len(rows) < 2 or len({len(row) for row in rows}) != 1:
        return None
    if all(not row[-1] for row in rows):
        rows = [row[:-1] for row in rows]
    return rows if len(rows[0]) >= _MIN_TABLE_CELLS else None


def _link_urls(line: str) -> tuple[str, int]:
    """Wrap bare URLs as autolinks; inline code and existing links stay as they are."""
    count = 0
    parts = line.split("`")
    for index in range(0, len(parts), 2):
        segment = parts[index]

        def wrap(match: re.Match[str], segment: str = segment) -> str:
            nonlocal count
            before = segment[: match.start()]
            url = match.group(0)
            if before.endswith(("<", "](", "[")):
                return url
            tail = ""
            wrapped = before[-1:] in tuple(_WRAPPING_MARKS)
            while url and (
                url[-1] in _TRAILING_PUNCTUATION
                or (wrapped and url[-1] in _WRAPPING_MARKS)
                or (url[-1] == ")" and url.count(")") > url.count("("))
            ):
                tail = url[-1] + tail
                url = url[:-1]
            count += 1
            return f"<{url}>{tail}"

        parts[index] = _URL_RE.sub(wrap, segment)
    return "`".join(parts), count


def _table(rows: list[list[str]]) -> list[str]:
    width = len(rows[0])
    separator = "|"
    for column in range(width):
        values = [row[column] for row in rows if row[column]]
        numeric = bool(values) and all(_NUMERIC_RE.match(value) for value in values)
        separator += "---:|" if numeric else "---|"
    body = ["| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |" for row in rows]
    return ["|" + "  |" * width, separator, *body]


def auto_format(text: str) -> tuple[str, dict[str, int]]:
    """The formatted text and how many tables, figures and URLs were converted."""
    lines = text.split("\n")
    flags = _code_flags(lines)
    out: list[str] = []
    counts = {"tables": 0, "figures": 0, "urls": 0}
    index = 0
    while index < len(lines):
        line = lines[index]
        if flags[index]:
            out.append(line)
            index += 1
            continue
        rows = _row_run(lines, flags, index)
        table = _table_rows(rows)
        if table:
            if out and out[-1].strip():
                out.append("")
            for table_line in _table(table):
                linked, found = _link_urls(table_line)
                counts["urls"] += found
                out.append(linked)
            counts["tables"] += 1
            index += len(rows)
            if index < len(lines) and lines[index].strip():
                out.append("")
            continue
        if len(rows) > 1:
            # A run that is not a table stays a list as a whole: never convert only part of it.
            for row_line in lines[index : index + len(rows)]:
                linked, found = _link_urls(row_line)
                counts["urls"] += found
                out.append(linked)
            index += len(rows)
            continue
        figure = _FIGURE_RE.match(line)
        if figure:
            out.append(f"![{figure['caption']}]({figure['path']})")
            counts["figures"] += 1
        else:
            linked, found = _link_urls(line)
            counts["urls"] += found
            out.append(linked)
        index += 1
    return "\n".join(out), counts


def _unfenced(text: str) -> list[tuple[int, str]]:
    """``(line number, line)`` for every line that is not code."""
    lines = text.split("\n")
    return [
        (number, line)
        for number, (line, is_code) in enumerate(zip(lines, _code_flags(lines)), start=1)
        if not is_code
    ]


def empty_table_headers(text: str) -> list[tuple[int, int]]:
    """``(line number, column count)`` of every table whose header row is empty."""
    lines = _unfenced(text)
    found = []
    for (number, line), (_, following) in zip(lines, lines[1:]):
        if _EMPTY_HEADER_RE.match(line) and _SEPARATOR_RE.match(following):
            found.append((number, line.count("|") - 1))
    return found


def pending(text: str) -> list[str]:
    """What ``auto_format`` leaves for the agent, in line order."""
    items = [
        (number, f"table without column names: name its {columns} columns")
        for number, columns in empty_table_headers(text)
    ]
    lines = _unfenced(text)
    run: list[int] = []
    for number, line in [*lines, (0, "")]:
        cells = _cells(line)
        if cells is not None and len(cells) == 2 and (not run or number == run[-1] + 1):
            run.append(number)
            continue
        if len(run) >= 2:
            items.append((run[0], "possible two-column table: format it as a table if it is data"))
        run = [number] if cells is not None and len(cells) == 2 else []
    for number, line in lines:
        if line.startswith(("|", "#", "!", "- ")):
            continue
        prose = _URL_RE.sub("", line)
        if _ASSIGNMENT_RE.search(prose) and _OPERATOR_RE.search(prose):
            items.append((number, "possible formula: write it as math"))
    return [f"line {number}: {message}" for number, message in sorted(items)]
