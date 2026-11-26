"""Deterministic formatting for the typeset phase (``typeset.py auto``).

Pure text functions, no file access. ``auto_format`` applies only the
conversions that need no judgement: runs of ``- a; b; c`` lines become pipe
tables, ``Figura: caption (path)`` lines become images and bare URLs become
autolinks. It never adds or removes a word of the body. A table takes its
column names from the parentheses that close the caption line before it
(``Tabla N. Caption (col a; col b; col c).``, or comma-separated
``(col a, col b, col c)`` when the list holds no ``;``) when they name as many columns
as the rows hold: the names move to the header row, the caption keeps
``Tabla N. Caption.`` and a ``<!-- table-style: tabla-N purpose=reference -->``
directive follows it. Otherwise the table gets an empty header row. A
``Figura:`` line with a sentence after its path becomes the image and that
sentence as its own paragraph.

Technical tokens (``TECHNICAL_TOKENS``: file names, MAC and IP addresses,
prefixes, interface names, binary and hex values, the ``CLI_COMMANDS``) are
wrapped in inline code in prose, list items and table cells; headings,
captions, image lines, URLs, links, citations, math (inline and display) and
existing code stay as they are. In each ``#``/``##`` section, in prose and list
items only and never as a bold-only line, a term is bolded once: terms listed in
report.yml ``key_terms`` at their first use, then the term that opens a
definition paragraph or list item (``El MAC flooding es un ...``).
Both passes are idempotent: formatting an already formatted text changes
nothing.

``pending`` lists what is left for the agent; ``empty_table_headers``,
``table_cell_problems`` and ``figure_leftovers`` back the ``table_headers``,
``table_cells`` and ``figure_leftovers`` checks of ``typeset.py check``.
"""
from __future__ import annotations

import re

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_INDENTED_CODE_RE = re.compile(r"^(?: {4}|\t)")
_FIGURE_RE = re.compile(
    r"^Figura:\s*(?P<caption>.+?)\s*\((?P<path>[^()\s]+\.(?:png|jpe?g|pdf|svg))\)(?:\s+(?P<rest>\S.*?))?\s*$",
    re.IGNORECASE,
)
_CAPTION_RE = re.compile(r"^(?P<head>Tabla (?P<number>\d+)\.\s.*?)\s*\((?P<columns>[^()]*[;,][^()]*)\)\.?\s*$")
_DIRECTIVE_RE = re.compile(r"^<!--\s*table-style:.*-->\s*$")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^()\s]+\)")
_FIGURA_TEXT_RE = re.compile(r"\bFigura:")
_FIGURE_PATH_RE = re.compile(r"\((?:[^()\s]*/)?figures/[^()\s]*\)|\([^()\s]+/[^()\s]+\.(?:png|jpe?g|pdf|svg)\)", re.IGNORECASE)
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

# Commands set in monospace when they appear in prose (skill-visual-organization
# S9). Edit this list to add commands; matching ignores case and spacing, and an
# address or interface right after the command joins the same code span.
CLI_COMMANDS = (
    "show mac address-table dynamic",
    "show mac address-table",
    "clear mac address-table dynamic",
    "mac address-table static",
    "show ip interface brief",
    "show ipv6 interface brief",
    "show running-config",
    "ipconfig /all",
    "ipconfig",
    "ip -6 addr show",
    "ip addr show",
    "arp -a",
    "ping",
    "tracert",
    "traceroute",
)
_HEX = "[0-9A-Fa-f]"
_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
_IPV4 = rf"{_OCTET}(?:\.{_OCTET}){{3}}(?:/(?:3[0-2]|[12]?\d))?"
_GROUP = rf"{_HEX}{{1,4}}"
_IPV6 = (
    rf"(?:(?:{_GROUP}:){{7}}{_GROUP}|(?:{_GROUP}(?::{_GROUP}){{0,6}})?::(?:{_GROUP}(?::{_GROUP}){{0,6}})?)"
    r"(?:/(?:12[0-8]|1[01]\d|[1-9]?\d))?"
)
# Part of an IPv6 address or a hex placeholder for one (ff02::1:ffXX:XXXX, the
# EUI-64 filler ff:fe, an interface ID 1ee3:56db:e4ad:3dab). A hex letter or an
# X must appear, so times (10:30, 12:30:45) and ratios (3:1) never match, and a
# lone pair needs two-character groups on both sides (ff:fe, not a:b).
_PGROUP = "[0-9A-Fa-fXx]{1,4}"
_IPV6_PARTIAL = (
    r"(?=[0-9A-Fa-fXx:]*[A-Fa-fXx])"
    rf"(?:{_PGROUP}(?::{_PGROUP}){{2,}}"
    r"|[0-9A-Fa-fXx]{2,4}:[0-9A-Fa-fXx]{2,4}"
    rf"|(?:{_PGROUP}(?::{_PGROUP})*)?::{_PGROUP}(?::{_PGROUP})*)"
)
_MAC = rf"{_HEX}{{2}}(?P<sep>[:-]){_HEX}{{2}}(?:(?P=sep){_HEX}{{2}}){{4}}"
_CISCO_MAC = rf"{_HEX}{{4}}\.{_HEX}{{4}}\.{_HEX}{{4}}"
_INTERFACE = (
    r"(?i:FastEthernet|GigabitEthernet|TenGigabitEthernet|Ethernet|Serial|Fa|Gi|Te|Se|Eth|Et)"
    r"\d+(?:/\d+){1,2}(?:\.\d+)?"
)
_COMMAND = "(?i:" + "|".join(
    r"\s+".join(re.escape(word) for word in command.split())
    for command in sorted(CLI_COMMANDS, key=len, reverse=True)
) + ")"
# (kind, pattern) in priority order; each pattern carries its own boundaries.
# A sentence-final '.' after a token is punctuation, not part of it.
# File names: a name (optionally with a relative path) ending in one of these extensions.
FILE_EXTENSIONS = (
    "pkt", "pka", "pcap", "pcapng", "png", "jpg", "jpeg", "svg", "pdf", "txt", "log", "md", "yml", "yaml",
    "json", "csv", "xml", "html", "cfg", "conf", "ini", "py", "sh", "tex", "bib", "docx", "xlsx", "pptx", "zip",
)
_FILE = (
    r"(?:[\w-]+/)*[\w-]+(?:\.[\w-]+)*\.(?i:"
    + "|".join(sorted(FILE_EXTENSIONS, key=len, reverse=True))
    + ")"
)
TECHNICAL_TOKENS: tuple[tuple[str, str], ...] = (
    ("file", rf"(?<![\w./\\-]){_FILE}(?![\w/-]|\.\w)"),
    (
        "command",
        rf"(?<![\w-]){_COMMAND}(?:\s+(?:{_IPV4}|{_IPV6.replace('(?P<sep>', '(?:')}|{_CISCO_MAC}|{_INTERFACE}))?"
        r"(?![\w-])",
    ),
    ("mac", rf"(?<![\w:./-]){_MAC}(?![\w:/-])"),
    ("mac", rf"(?<![\w./]){_CISCO_MAC}(?![\w/]|\.\w)"),
    ("ipv6", rf"(?<![\w:./]){_IPV6}(?![\w:/]|\.\w)"),
    ("ipv4", rf"(?<![\w.:/]){_IPV4}(?![\w/]|\.\w)"),
    ("ipv6", rf"(?<![\w:./]){_IPV6_PARTIAL}(?![\w:/]|\.\w)"),
    ("interface", rf"(?<![\w/]){_INTERFACE}(?![\w/]|\.\w)"),
    ("binary", r"(?<![\w./])[01]{8}(?:\.[01]{8}){0,3}(?![\w/]|\.\w)"),
    ("hex", r"(?<![\w./])0x[0-9A-Fa-f]+(?![\w/]|\.\w)"),
)
TECHNICAL_TOKEN_KINDS = tuple(dict.fromkeys(kind for kind, _ in TECHNICAL_TOKENS))
TECHNICAL_TOKEN_HELP = (
    "technical tokens set in inline code: mac (38:a7:46:39:d2:7b, 38-A7-..., 0001.6453.DBC1), "
    "ipv4 (192.168.10.1, 192.168.10.0/24, each end of a range), ipv6 (2001:db8::1, fe80::/10, ::1, parts and placeholders such as "
    "ff02::1:ffXX:XXXX, ff:fe, 1ee3:56db:e4ad:3dab), "
    "interface (Fa0/24, FastEthernet0/1, Gi0/1), binary (00111000, dotted octets), hex (0x0800), "
    "command (" + ", ".join(CLI_COMMANDS) + "), file (APE2-F2-mac-ip.pkt, configs/sw1.txt; extensions: "
    + ", ".join(FILE_EXTENSIONS) + ")"
)
_TOKEN_RE = re.compile("|".join(f"(?P<t{index}>{pattern})" for index, (_, pattern) in enumerate(TECHNICAL_TOKENS)))
_TOKEN_KIND = {f"t{index}": kind for index, (kind, _) in enumerate(TECHNICAL_TOKENS)}
# Spans no token or key term is looked for in. Bold spans are protected only
# for the key-term pass.
_PROTECTED = (
    r"`[^`]*`|<!--.*?-->|<[A-Za-z][A-Za-z0-9+.-]*:[^>\s]*>|!?\[[^\]]*\]\([^)\s]*\)|\[-?@[^\]]*\]"
    r"|\$[^$\n]+\$|" + _URL_RE.pattern
    # A '(figures/x.png)' leftover stays as it is for the figure_leftovers check.
    + r"|(?i:\((?:[^()\s]*/)?figures/[^()\s]*\)|\([^()\s]+/[^()\s]+\.(?:png|jpe?g|pdf|svg)\))"
)
_PROTECTED_RE = re.compile(_PROTECTED)
_PROTECTED_BOLD_RE = re.compile(r"\*\*[^*\n]+\*\*|" + _PROTECTED)
# Lines that are not prose: headings, captions, images and HTML.
_NOT_PROSE_RE = re.compile(r"^\s{0,3}#{1,6}(?:\s|$)|^\s*(?:Tabla\s+\d+\.|Table\s+\d+\.|Figura\b|Figure\b)|^\s*!\[|^\s*<")
_SECTION_RE = re.compile(r"^\s{0,3}#{1,2}(?:\s|$)")
_BOLD_ONLY_RE = re.compile(r"^\*\*[^*]+\*\*[.:;,!?]?$")
_BOLD_SPAN_RE = re.compile(r"\*\*[^*\n]+\*\*")
# Display math blocks: '$$' or '\[' opens, '$$' or '\]' closes.
_MATH_OPEN_RE = re.compile(r"^\s*(?:\$\$|\\\[)\s*$")
_MATH_CLOSE_RE = re.compile(r"^\s*(?:\$\$|\\\])\s*$")
# A definition: a paragraph or list item that opens with a term of one to four
# words, optionally followed by '(ACR)' or ', o <alias>,', and 'es un/una' or
# 'son unos/unas' (or 'is a/an'). Only the term is bolded.
_DEFINITION_RE = re.compile(
    r"^(?P<lead>\s*(?:[-*+]\s+|\d+[.)]\s+)?(?:(?:El|La|Los|Las|Un|Una|The|An?)\s+)?)"
    r"(?P<term>[^\W\d_][\w-]*(?:\s+[\w-]+){0,3}?)"
    r"(?=(?:\s+\([^()\n]{1,40}\))?(?:,\s+o\s+[^,\n]{1,60},)?\s+(?:es\s+(?:un|una)|son\s+(?:unos|unas)|is\s+an?)\s)",
    re.IGNORECASE,
)
# First words that open a sentence about something other than a defined term.
_NOT_A_TERM = frozenset(
    "esto eso aquello este esta ese esa ello lo no se ya también tambien aquí aqui ahora hoy cada todo "
    "primero segundo tercero cuarto quinto último ultimo resultado objetivo problema ejemplo caso motivo "
    "idea punto paso cual que it this that there here result first second example".split()
)


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


def _caption_columns(out: list[str], width: int) -> tuple[int, str, str, list[str]] | None:
    """The caption line before a table whose parentheses name its ``width`` columns.

    Returns its index in ``out``, the caption without the parentheses, the
    table number and the column names; ``None`` when there is no such caption
    or it names another number of columns. Blank lines and a table-style
    directive may sit between the caption and the rows.
    """
    index = len(out) - 1
    while index >= 0 and (not out[index].strip() or _DIRECTIVE_RE.match(out[index].strip())):
        index -= 1
    match = _CAPTION_RE.match(out[index]) if index >= 0 else None
    if not match:
        return None
    columns = _caption_names(match["columns"])
    if len(columns) != width or not all(columns):
        return None
    return index, match["head"].rstrip(".") + ".", match["number"], columns


def _caption_names(columns: str) -> list[str]:
    """The column names in caption parentheses: ``;``-separated, else ``,``-separated."""
    names = _split_cells(columns)
    if len(names) > 1:
        return names
    return [name.strip() for name in columns.split(",")]


def _directed(out: list[str], start: int) -> bool:
    return any(_DIRECTIVE_RE.match(line.strip()) for line in out[start:])


def _table(rows: list[list[str]], header: list[str] | None = None) -> list[str]:
    width = len(rows[0])
    separator = "|"
    for column in range(width):
        values = [row[column] for row in rows if row[column]]
        numeric = bool(values) and all(_NUMERIC_RE.match(value) for value in values)
        separator += "---:|" if numeric else "---|"
    body = ["| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |" for row in rows]
    if header is None:
        return ["|" + "  |" * width, separator, *body]
    names = [name[:1].upper() + name[1:] for name in header]
    return ["| " + " | ".join(name.replace("|", "\\|") for name in names) + " |", separator, *body]


def _spans(line: str, pattern: re.Pattern[str]) -> list[tuple[int, int]]:
    return [match.span() for match in pattern.finditer(line)]


def _inside(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(start < span_end and end > span_start for span_start, span_end in spans)


def wrap_technical_tokens(line: str) -> tuple[str, dict[str, int]]:
    """``line`` with every technical token outside protected spans in inline code, and the count per kind."""
    counts = dict.fromkeys(TECHNICAL_TOKEN_KINDS, 0)
    protected = _spans(line, _PROTECTED_RE)
    pieces = []
    position = 0
    for match in _TOKEN_RE.finditer(line):
        start, end = match.span()
        token = match.group(0)
        if (
            _inside(protected, start, end)
            or token == "::"
            or line[start - 1 : start] == "`"
            or line[end : end + 1] == "`"
        ):
            continue
        pieces += [line[position:start], f"`{token}`"]
        position = end
        counts[_TOKEN_KIND[match.lastgroup]] += 1
    pieces.append(line[position:])
    return "".join(pieces), counts


def _term_re(term: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + r"\s+".join(re.escape(word) for word in term.split()) + r"(?!\w)", re.IGNORECASE)


def _bold_term(line: str, pattern: re.Pattern[str]) -> str | None:
    """``line`` with the first usable occurrence of the term in bold, or ``None``."""
    protected = _spans(line, _PROTECTED_BOLD_RE)
    for match in pattern.finditer(line):
        if _inside(protected, *match.span()):
            continue
        bolded = f"{line[: match.start()]}**{match.group(0)}**{line[match.end():]}"
        if _BOLD_ONLY_RE.match(bolded.strip()):
            return None
        return bolded
    return None


def _typeset_spans(lines: list[str], key_terms: tuple[str, ...], counts: dict[str, int]) -> list[str]:
    """Technical tokens in inline code everywhere in prose, key terms in bold once per section."""
    flags = _code_flags(lines)
    math = _math_flags(lines)
    prose = [
        not is_code and not in_math and not _NOT_PROSE_RE.match(line)
        for line, is_code, in_math in zip(lines, flags, math)
    ]
    out = []
    for line, is_prose in zip(lines, prose):
        if is_prose:
            line, found = wrap_technical_tokens(line)
            for kind, number in found.items():
                counts[f"code_{kind}"] += number
                counts["code"] += number
        out.append(line)
    terms = [(term, _term_re(term)) for term in sorted(key_terms, key=len, reverse=True)]
    starts = [index for index, line in enumerate(out) if not flags[index] and _SECTION_RE.match(line)]
    for start, end in zip([0, *starts], [*starts, len(out)]):
        eligible = [index for index in range(start, end) if prose[index] and not out[index].lstrip().startswith("|")]
        bolded_terms = {_normal(span[2:-2]) for index in eligible for span in _BOLD_SPAN_RE.findall(out[index])}
        for term, pattern in terms:
            if any(pattern.fullmatch(bolded) for bolded in bolded_terms):
                continue
            for index in eligible:
                bolded = _bold_term(out[index], pattern)
                if bolded is not None:
                    out[index] = bolded
                    bolded_terms.add(_normal(term))
                    counts["bold"] += 1
                    break
        for index in eligible:
            if index > 0 and prose[index - 1] and out[index - 1].strip() and not _LIST_ITEM_RE.match(out[index]):
                continue  # not the opening line of a paragraph or list item
            match = _DEFINITION_RE.match(out[index])
            if not match or match.group("term").split()[0].lower() in _NOT_A_TERM:
                continue
            term = match.group("term")
            if _normal(term) in bolded_terms:
                continue
            out[index] = f"{out[index][: match.start('term')]}**{term}**{out[index][match.end('term'):]}"
            bolded_terms.add(_normal(term))
            counts["bold"] += 1
    return out


_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def _normal(term: str) -> str:
    return " ".join(term.split()).casefold()


def _math_flags(lines: list[str]) -> list[bool]:
    """Per line, whether it belongs to a display math block (its delimiters included)."""
    flags = []
    inside = False
    for line in lines:
        if inside:
            flags.append(True)
            inside = not _MATH_CLOSE_RE.match(line)
        else:
            inside = bool(_MATH_OPEN_RE.match(line))
            flags.append(inside)
    return flags


def auto_format(text: str, key_terms: tuple[str, ...] | list[str] = ()) -> tuple[str, dict[str, int]]:
    """The formatted text and how many tables, figures, URLs, code tokens and bold terms were converted.

    ``counts["code"]`` is the total of the ``code_<kind>`` counts, one per
    ``TECHNICAL_TOKEN_KINDS`` entry.
    """
    lines = text.split("\n")
    flags = _code_flags(lines)
    out: list[str] = []
    counts = {"tables": 0, "figures": 0, "urls": 0, "code": 0, "bold": 0}
    counts.update({f"code_{kind}": 0 for kind in TECHNICAL_TOKEN_KINDS})
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
            caption = _caption_columns(out, len(table[0]))
            header = None
            if caption:
                position, text, number, header = caption
                out[position] = text
                if not _directed(out, position + 1):
                    out[position + 1 : position + 1] = ["", f"<!-- table-style: tabla-{number} purpose=reference -->"]
            if out and out[-1].strip():
                out.append("")
            for table_line in _table(table, header):
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
            if out and out[-1].strip():
                out.append("")
            out.append(f"![{figure['caption']}]({figure['path']})")
            counts["figures"] += 1
            # Its own paragraph: a line right after the image would make it inline text.
            following = [figure["rest"]] if figure["rest"] else []
            if following or (index + 1 < len(lines) and lines[index + 1].strip()):
                out.append("")
            if following:
                # The merged sentence is formatted as the next line.
                lines[index + 1 : index + 1] = following
                flags[index + 1 : index + 1] = [False]

        else:
            linked, found = _link_urls(line)
            counts["urls"] += found
            out.append(linked)
        index += 1
    return "\n".join(_typeset_spans(out, tuple(key_terms), counts)), counts


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


def _split_row(line: str) -> list[str]:
    """The cells of a pipe-table row, split as the LaTeX build splits them (``\\|`` is a literal pipe)."""
    stripped = re.sub(r"(?<!\\)\|$", "", line.strip()).lstrip("|")
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", stripped)]


def _pipe_tables(text: str) -> list[tuple[int, list[str], list[tuple[int, list[str]]]]]:
    """``(header line number, header cells, [(line number, cells)])`` of every pipe table outside code."""
    lines = text.split("\n")
    flags = _code_flags(lines)
    tables = []
    index = 0
    while index + 1 < len(lines):
        line = lines[index]
        if flags[index] or "|" not in line or flags[index + 1] or not _SEPARATOR_RE.match(lines[index + 1].strip()):
            index += 1
            continue
        rows = []
        row = index + 2
        while row < len(lines) and not flags[row] and lines[row].strip() and "|" in lines[row]:
            rows.append((row + 1, _split_row(lines[row])))
            row += 1
        tables.append((index + 1, _split_row(line), rows))
        index = row
    return tables


def table_cell_problems(text: str) -> list[str]:
    """Empty header cells of a named header, empty body cells, ragged rows and rows split into extra cells.

    A header row that is empty as a whole is the ``table_headers`` check, not
    this one.
    """
    problems = []
    for number, header, rows in _pipe_tables(text):
        width = len(header)
        if any(header):
            problems += [
                f"line {number}: empty header cell in column {column}"
                for column, cell in enumerate(header, start=1)
                if not cell
            ]
        for row_number, cells in rows:
            if len(cells) > width:
                problems.append(
                    f"line {row_number}: {len(cells)} cells, the header has {width} (a stray ';' or '|' split a cell?)"
                )
            elif len(cells) < width:
                problems.append(f"line {row_number}: {len(cells)} cells, the header has {width} (ragged row)")
            else:
                problems += [
                    f"line {row_number}: empty cell in column {column} (write — if nothing applies)"
                    for column, cell in enumerate(cells, start=1)
                    if not cell
                ]
    return problems


def figure_leftovers(text: str) -> list[str]:
    """Literal ``Figura:`` text and figure paths in parentheses left outside an image."""
    problems = []
    for number, line in _unfenced(text):
        prose = "`".join(part for position, part in enumerate(line.split("`")) if position % 2 == 0)
        prose = _IMAGE_RE.sub("", prose)
        if _FIGURA_TEXT_RE.search(prose):
            problems.append(f"line {number}: literal 'Figura:' text: write it as ![caption](path) on its own line")
        problems += [
            f"line {number}: figure path '{match.group(0)}' outside an image"
            for match in _FIGURE_PATH_RE.finditer(prose)
            if "://" not in match.group(0)
        ]
    return problems


def _caption_before(lines: list[str], number: int) -> re.Match[str] | None:
    """The ``Tabla N. Caption (a; b)`` match of the caption line before line ``number`` (1-based)."""
    index = number - 2
    while index >= 0 and (not lines[index].strip() or _DIRECTIVE_RE.match(lines[index].strip())):
        index -= 1
    return _CAPTION_RE.match(lines[index]) if index >= 0 else None


def _row_cells(cells: list[str]) -> int:
    """How many cells a ``- a; b`` row holds, a trailing ``;`` aside."""
    return len(cells) - 1 if len(cells) > 1 and not cells[-1] else len(cells)


def pending(text: str) -> list[str]:
    """What ``auto_format`` leaves for the agent, in line order."""
    all_lines = text.split("\n")
    items = []
    for number, columns in empty_table_headers(text):
        message = f"table without column names: name its {columns} columns"
        caption = _caption_before(all_lines, number)
        named = len(_caption_names(caption["columns"])) if caption else columns
        if named != columns:
            message += f" (the caption names {named}: fix the caption or the rows)"
        items.append((number, message))
    lines = _unfenced(text)
    run: list[tuple[int, int]] = []
    for number, line in [*lines, (0, "")]:
        cells = _cells(line)
        if cells is not None and (not run or number == run[-1][0] + 1):
            run.append((number, _row_cells(cells)))
            continue
        counts = sorted({count for _, count in run})
        if len(run) >= 2 and len(counts) > 1 and counts[0] >= 2 and counts[-1] >= _MIN_TABLE_CELLS:
            listed = ", ".join(str(count) for count in counts)
            items.append((run[0][0], f"list rows with {listed} cells: a stray ';' keeps it from becoming a table"))
        run = [(number, _row_cells(cells))] if cells is not None else []
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
