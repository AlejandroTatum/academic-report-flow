"""Map contextual table style tokens to HTML/inline CSS (issue #13, spec R9).

``render_styled_table_html`` is the HTML preview backend's half of
"coherent cross-backend rendering": mirrors ``table_latex_tokens.py`` and
``table_docx_tokens.py`` token for token. Emits ONE self-contained
``<table data-table-style="ID">...</table>`` with inline styles rather than
a shared CSS class, so a styled table never depends on (or collides with)
``templates/ensayo_unl.css``'s single generic ``table``/``th``/``td`` rule
that undirected tables still use unchanged.

Kept free of any import from ``tools/build_report.py`` (that module has no
``ReportConfig`` at all -- it renders one bare Markdown file -- so the
per-table override machinery ``table_model.py`` provides does not apply
here; only automatic contextual selection does). ``escape_inline`` is
injected, matching ``convert_inline``/``fill_cell`` in the other two
backends.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from table_styles import StatusIndicator, StyleDefinition

from table_directives import strip_status_markers
from table_styles import COLUMN_EMPHASIS_FILL_HEX, HEADER_FILL_HEX, ROW_ALTERNATING_FILL_HEX

_ALIGN_CSS = {"centered": "center", "left": "left", "numeric_right": "right"}
_PADDING_PX = {"generous": "10px 12px", "standard": "6px 8px", "compact": "4px 6px", "minimal": "2px 4px"}
_FONT_SIZE_PT = {"low": "11pt", "medium": "9.5pt", "high": "8pt"}
# Derived from table_styles.HEADER_FILL_HEX (shared with table_docx_tokens)
# so "gray_shaded"/"dark_shaded" paint the identical color in both backends
# -- previously hand-copied here as a slightly different literal (#ededed
# vs DOCX's #EAEAEA), a coherence drift `test_issue_13_backend_style_coherence`
# is meant to catch.
_HEADER_STYLE = {
    "gray_shaded": f"background:#{HEADER_FILL_HEX['gray_shaded'].lower()};",
    "dark_shaded": f"background:#{HEADER_FILL_HEX['dark_shaded'].lower()};color:#ffffff;",
    "institutional_shaded": f"background:#{HEADER_FILL_HEX['institutional_shaded'].lower()};color:#ffffff;",
    "plain": "",
}
_ROW_ALTERNATING_CSS = f"#{ROW_ALTERNATING_FILL_HEX.lower()}"
_COLUMN_EMPHASIS_CSS = f"#{COLUMN_EMPHASIS_FILL_HEX.lower()}"


def _cell_border(borders_token: str) -> str:
    if borders_token == "full_grid":
        return "border:0.75pt solid #000;"
    if borders_token == "horizontal_only":
        return "border:none;border-top:0.75pt solid #000;border-bottom:0.75pt solid #000;"
    return "border:none;"  # minimal -- header underline added separately


def _indicator_html(value: str, status_indicators: "dict[str, StatusIndicator]") -> str:
    if value not in status_indicators:
        raise ValueError(
            f"unknown status marker [[status:{value}]] -- approved values are "
            f"{sorted(status_indicators)}"
        )
    indicator = status_indicators[value]
    # Symbol AND label both accompany the color -- never color alone.
    return f' <span style="color:{indicator.color};">{indicator.symbol}</span> {indicator.label}'


def render_styled_table_html(
    header: list[str],
    rows: list[list[str]],
    style: "StyleDefinition",
    status_indicators: "dict[str, StatusIndicator]",
    escape_inline: Callable[[str], str],
    emphasis_column: int | None = None,
    caption: str | None = None,
    notes: str | None = None,
) -> str:
    """Render one table as a self-contained, inline-styled HTML fragment.

    Raises ``ValueError`` for the same cases the other two backends do: a
    ``column_emphasis`` style with no (or an out-of-range)
    ``emphasis_column``, or an unapproved ``[[status:<value>]]`` marker.
    """
    tokens = style.tokens
    columns = len(header)

    if tokens["row_rhythm"] == "column_emphasis" and emphasis_column is None:
        raise ValueError(f"{style.id}: column_emphasis row rhythm requires an emphasis_column index")
    if emphasis_column is not None and not (0 <= emphasis_column < columns):
        raise ValueError(f"{style.id}: emphasis_column {emphasis_column} is out of range for {columns} columns")

    border_css = _cell_border(tokens["borders"])
    padding_css = f"padding:{_PADDING_PX[tokens['padding']]};"
    font_css = f"font-size:{_FONT_SIZE_PT[tokens['density']]};"
    align_css = f"text-align:{_ALIGN_CSS[tokens['alignment']]};"
    is_emphasis_style = tokens["row_rhythm"] == "column_emphasis"

    table_style = "width:100%;border-collapse:collapse;margin:8px 0 12px;"
    if tokens["borders"] == "minimal":
        table_style += "border-bottom:none;"

    lines = [f'<table data-table-style="{style.id}" style="{table_style}">']
    if caption:
        caption_side = "bottom" if tokens["caption"] == "below" else "top"
        lines.append(
            f'  <caption style="caption-side:{caption_side};text-align:center;'
            f'font-style:italic;font-size:10pt;">{escape_inline(caption)}</caption>'
        )

    legend_values: set[str] = set()

    def _cell(text: str, *, is_header: bool, column_index: int) -> str:
        clean, markers = strip_status_markers(text)
        content = escape_inline(clean)
        for value in markers:
            content += _indicator_html(value, status_indicators)
            legend_values.add(value)
        cell_style = f"{border_css}{padding_css}{font_css}{align_css}vertical-align:top;"
        is_emphasis_cell = is_emphasis_style and column_index == emphasis_column
        if is_emphasis_cell:
            cell_style += f"background:{_COLUMN_EMPHASIS_CSS};font-weight:700;"
            content = f"<strong>{content}</strong>" if not is_header else content
        if is_header:
            cell_style += "font-weight:700;text-align:center;" + _HEADER_STYLE[tokens["header"]]
            if tokens["borders"] == "minimal":
                cell_style += "border-bottom:0.75pt solid #000;"
            tag = "th"
        else:
            tag = "td"
        return f'    <{tag} style="{cell_style}">{content}</{tag}>'

    lines.append("  <thead>")
    lines.append("    <tr>")
    lines.extend(_cell(cell, is_header=True, column_index=idx) for idx, cell in enumerate(header))
    lines.append("    </tr>")
    lines.append("  </thead>")

    lines.append("  <tbody>")
    for row_index, row in enumerate(rows):
        padded = row + [""] * (columns - len(row))
        row_style = ""
        if tokens["row_rhythm"] == "alternating" and row_index % 2 == 1:
            row_style = f' style="background:{_ROW_ALTERNATING_CSS};"'
        lines.append(f"    <tr{row_style}>")
        lines.extend(_cell(cell, is_header=False, column_index=idx) for idx, cell in enumerate(padded))
        lines.append("    </tr>")

    if notes and tokens["notes"] == "inline":
        lines.append("    <tr>")
        lines.append(
            f'      <td colspan="{columns}" style="{border_css}{padding_css}font-style:italic;">'
            f"{escape_inline(notes)}</td>"
        )
        lines.append("    </tr>")
    lines.append("  </tbody>")
    lines.append("</table>")

    if notes and tokens["notes"] == "below":
        lines.append(f'<p style="font-style:italic;font-size:9pt;">{escape_inline(notes)}</p>')
    if legend_values:
        legend_text = "  ".join(
            f'<span style="color:{status_indicators[value].color};">{status_indicators[value].symbol}</span> '
            f"{status_indicators[value].label}"
            for value in sorted(legend_values)
        )
        lines.append(f'<p style="font-size:9pt;">{legend_text}</p>')

    return "\n".join(lines)
