"""The one Markdown image pattern every builder and check shares.

A caption may contain one level of balanced brackets, so a citation such as
``![Figura 1. Datos de [@inec2025tic].](figures/x.png)`` is still an image
(#101). An optional ``{width=70%}`` / ``{height=50%}`` attribute block may
follow the image (#103); ``figure_size`` reads it.
"""
from __future__ import annotations

import re

_CAPTION = r"(?:[^\[\]\n]|\[[^\[\]\n]*\])*"
IMAGE_PATTERN = re.compile(
    rf"!\[(?P<caption>{_CAPTION})\]\((?P<src>[^)\n]+)\)(?:\{{(?P<attrs>[^}}\n]*)\}})?"
)
_SIZE_ATTR = re.compile(r"\b(?P<key>width|height)\s*=\s*(?P<value>\d+(?:\.\d+)?)\s*%")


def figure_size(attrs: str | None) -> dict[str, float]:
    """Return the ``width``/``height`` fractions (0-1] an attribute block sets."""
    sizes: dict[str, float] = {}
    for match in _SIZE_ATTR.finditer(attrs or ""):
        value = float(match.group("value")) / 100
        if 0 < value <= 1:
            sizes[match.group("key")] = value
    return sizes
