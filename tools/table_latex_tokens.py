"""Map contextual table style tokens to LaTeX (issue #13, spec scenario R9).

``render_styled_table_latex`` is the LaTeX backend's half of "coherent
cross-backend rendering": given one resolved ``StyleDefinition`` (from
``tools/table_styles.py``), it emits ONE coherent construct for the whole
table -- never a mix of fragments from different styles. It has no
knowledge of overrides, receipts, or Markdown parsing; those belong to
``tools/table_model.py`` and ``tools/table_directives.py``.

Kept free of any import from ``tools/build_latex_report.py`` to avoid a
circular import (that module will call this one): cell-escaping is
injected as ``convert_inline`` rather than imported.

Page-breakable environment choice mirrors the existing generic renderer
(#26): ``longtable`` for two columns or fewer, ``xltabular`` otherwise, so
every style keeps the wrapping/pagination behavior the rest of the
document relies on.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from table_styles import StatusIndicator, StyleDefinition

from table_directives import strip_status_markers
from table_styles import HEADER_FILL_HEX

_ALIGN_COMMAND = {
    "centered": r"\centering\arraybackslash",
    "left": r"\raggedright\arraybackslash",
    "numeric_right": r"\raggedleft\arraybackslash",
}
# Header fills that carry white text; both backends of the same hex agree via
# table_styles.HEADER_FILL_HEX (dark_shaded keeps its legacy gray-model spelling).
_WHITE_TEXT_ROWCOLOR = {
    "dark_shaded": r"\rowcolor[gray]{0.25}",
    "institutional_shaded": rf"\rowcolor[HTML]{{{HEADER_FILL_HEX['institutional_shaded']}}}",
}
_PADDING_PT = {"generous": "6pt", "standard": "3pt", "compact": "2pt", "minimal": "1pt"}
_ARRAYSTRETCH = {"generous": "1.4", "standard": "1.2", "compact": "1.05", "minimal": "1.0"}
_FONT_SIZE = {"low": r"\small", "medium": r"\footnotesize", "high": r"\scriptsize"}


def _emphasize(text: str, *, is_emphasis_column: bool, bold: bool = False) -> str:
    prefix = r"\cellcolor[gray]{0.85}" if is_emphasis_column else ""
    if bold and not is_emphasis_column:
        return r"\textbf{" + text + "}"
    if is_emphasis_column:
        return prefix + r"\textbf{" + text + "}"
    return text


def _indicator_suffix(value: str, status_indicators: "dict[str, StatusIndicator]") -> str:
    if value not in status_indicators:
        raise ValueError(
            f"unknown status marker [[status:{value}]] -- approved values are "
            f"{sorted(status_indicators)}"
        )
    indicator = status_indicators[value]
    hex_color = indicator.color.lstrip("#")
    # Symbol AND label always accompany the color -- never color alone.
    return rf" \textcolor[HTML]{{{hex_color}}}{{{indicator.symbol}}} {indicator.label}"


def render_styled_table_latex(
    header: list[str],
    rows: list[list[str]],
    style: "StyleDefinition",
    status_indicators: "dict[str, StatusIndicator]",
    convert_inline: Callable[[str], str],
    emphasis_column: int | None = None,
    caption: str | None = None,
    notes: str | None = None,
) -> list[str]:
    """Render one table under one coherent resolved style.

    Raises ``ValueError`` for a ``column_emphasis`` style with no
    ``emphasis_column``, an out-of-range one, or an unapproved
    ``[[status:<value>]]`` marker -- blocking, never guessing.
    """
    tokens = style.tokens
    columns = len(header)

    if tokens["row_rhythm"] == "column_emphasis" and emphasis_column is None:
        raise ValueError(f"{style.id}: column_emphasis row rhythm requires an emphasis_column index")
    if emphasis_column is not None and not (0 <= emphasis_column < columns):
        raise ValueError(f"{style.id}: emphasis_column {emphasis_column} is out of range for {columns} columns")

    align_cmd = _ALIGN_COMMAND[tokens["alignment"]]
    vbar = tokens["borders"] == "full_grid"
    if columns <= 2:
        col_width = rf"\dimexpr(\textwidth-{8 * columns}pt)/{columns}\relax"
        col_token = rf">{{{align_cmd}}}p{{{col_width}}}"
        env = "longtable"
    else:
        col_token = rf">{{{align_cmd}}}X"
        env = "xltabular"
    colspec = ("| " + " | ".join([col_token] * columns) + " |") if vbar else " ".join([col_token] * columns)
    table_open = (
        rf"\begin{{{env}}}{{{colspec}}}" if env == "longtable"
        else rf"\begin{{{env}}}{{\textwidth}}{{{colspec}}}"
    )

    lines: list[str] = [f"% table-style: {style.id} ({style.label})"]
    lines.append(r"\Needspace{4\baselineskip}")
    lines.append(r"\begingroup")
    lines.append(_FONT_SIZE[tokens["density"]])
    lines.append(rf"\renewcommand{{\arraystretch}}{{{_ARRAYSTRETCH[tokens['padding']]}}}")
    lines.append(rf"\setlength{{\tabcolsep}}{{{_PADDING_PT[tokens['padding']]}}}")
    if tokens["row_rhythm"] == "alternating":
        lines.append(r"\rowcolors{2}{white}{gray!10}")
    lines.append(table_open)
    if caption and tokens["caption"] == "above":
        lines.append(rf"\caption{{{convert_inline(caption)}}}\\")
    if tokens["borders"] in ("full_grid", "horizontal_only"):
        lines.append(r"\hline")

    is_emphasis_column_style = tokens["row_rhythm"] == "column_emphasis"
    header_cells = [
        _emphasize(convert_inline(cell), is_emphasis_column=is_emphasis_column_style and idx == emphasis_column, bold=True)
        for idx, cell in enumerate(header)
    ]
    header_line = " & ".join(header_cells) + r" \\"
    if tokens["header"] == "gray_shaded":
        lines.append(r"\rowcolor[gray]{0.92}")
        lines.append(header_line)
    elif tokens["header"] in _WHITE_TEXT_ROWCOLOR:
        lines.append(_WHITE_TEXT_ROWCOLOR[tokens["header"]])
        colored_cells = ["{\\color{white} " + cell + "}" for cell in header_cells]
        lines.append(" & ".join(colored_cells) + r" \\")
    else:
        lines.append(header_line)
    lines.append(r"\hline")
    lines.append(r"\endhead")

    legend_values: set[str] = set()
    for row in rows:
        cells = []
        for idx, raw_cell in enumerate(row):
            clean, markers = strip_status_markers(raw_cell)
            text = convert_inline(clean)
            for value in markers:
                text += _indicator_suffix(value, status_indicators)
                legend_values.add(value)
            text = _emphasize(text, is_emphasis_column=is_emphasis_column_style and idx == emphasis_column)
            cells.append(text)
        lines.append(" & ".join(cells) + r" \\")
        if tokens["borders"] == "full_grid":
            lines.append(r"\hline")

    if notes and tokens["notes"] == "inline":
        lines.append(rf"\multicolumn{{{columns}}}{{l}}{{\textit{{{convert_inline(notes)}}}}} \\")
        if tokens["borders"] == "full_grid":
            lines.append(r"\hline")

    if tokens["borders"] == "horizontal_only":
        lines.append(r"\hline")

    lines.append(rf"\end{{{env}}}")
    lines.append(r"\endgroup")

    if caption and tokens["caption"] == "below":
        lines.append(r"{\small\itshape " + convert_inline(caption) + "}\\\\")
    if notes and tokens["notes"] == "below":
        lines.append(r"{\small\itshape " + convert_inline(notes) + "}\\\\")
    if legend_values:
        legend = "; ".join(
            rf"\textcolor[HTML]{{{status_indicators[value].color.lstrip('#')}}}{{{status_indicators[value].symbol}}} "
            rf"{status_indicators[value].label}"
            for value in sorted(legend_values)
        )
        lines.append(r"{\small " + legend + "}\\\\")
    lines.append("")

    return lines
