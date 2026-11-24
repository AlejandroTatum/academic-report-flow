"""Blank gaps on figure pages (skill-visual-organization S4).

The excessive-whitespace check exempts figure-dominated pages, so a float
page with a figure centered between two blank bands, or a page left with a
third of its height empty under a pinned figure, audited clean. The figure-gap
check reports those gaps. It is a WARNING only: the user's delivery gates are
warn-only, and whether a gap is acceptable is a human call.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import visual_pdf_auditor as auditor  # noqa: E402
from test_excessive_whitespace import _page, _text_block, short_page  # noqa: E402

DPIS = (150, 300)


def block(top: float, bottom: float, dpi: int, text_above: tuple[float, float] | None = None) -> Image.Image:
    """A figure-like solid block between *top* and *bottom* (fractions of height)."""
    img, draw, w, h = _page(dpi)
    if text_above:
        _text_block(draw, w, dpi, round(h * text_above[0]), round(h * text_above[1]))
    draw.rectangle([dpi, round(h * top), w - dpi, round(h * bottom)], fill=90)
    # Page number in the footer band: never content.
    draw.rectangle([w // 2, round(h * 0.94), w // 2 + round(0.1 * dpi), round(h * 0.95)], fill=0)
    return img


def gaps(img: Image.Image, **kwargs):
    kwargs.setdefault("is_cover", False)
    kwargs.setdefault("is_last_page", False)
    return auditor.check_figure_gaps(img, **kwargs)


@pytest.mark.parametrize("dpi", DPIS)
def test_a_blank_band_under_a_figure_is_reported(dpi: int) -> None:
    flagged, frac, side = gaps(block(0.09, 0.55, dpi))
    assert flagged is True and side == "below"
    assert frac is not None and frac >= auditor.FIGURE_GAP_MIN_FRAC


@pytest.mark.parametrize("dpi", DPIS)
def test_a_figure_centred_between_two_blank_bands_is_reported(dpi: int) -> None:
    flagged, frac, side = gaps(block(0.42, 0.60, dpi))
    assert flagged is True and side == "above"
    assert frac >= auditor.FIGURE_GAP_MIN_FRAC


@pytest.mark.parametrize("dpi", DPIS)
def test_a_gap_between_text_and_a_figure_is_reported(dpi: int) -> None:
    flagged, _, side = gaps(block(0.55, 0.88, dpi, text_above=(0.09, 0.20)))
    assert flagged is True and side == "between"


@pytest.mark.parametrize("dpi", DPIS)
def test_a_page_filled_by_its_figures_is_not_reported(dpi: int) -> None:
    assert gaps(block(0.09, 0.87, dpi))[0] is False
    assert gaps(block(0.30, 0.87, dpi, text_above=(0.09, 0.28)))[0] is False


@pytest.mark.parametrize("dpi", DPIS)
def test_a_text_page_is_left_to_the_whitespace_check(dpi: int) -> None:
    assert gaps(short_page(dpi))[0] is False


@pytest.mark.parametrize("dpi", DPIS)
def test_cover_and_last_page_are_exempt(dpi: int) -> None:
    page = block(0.09, 0.55, dpi)
    assert gaps(page, is_cover=True)[0] is False
    assert gaps(page, is_last_page=True)[0] is False


def test_the_existing_whitespace_check_still_exempts_figure_pages() -> None:
    """The new tag sits beside EXCESSIVE_WHITESPACE; it does not change it."""
    assert auditor.check_excessive_whitespace(block(0.09, 0.55, 150))[0] is False


def test_a_figure_gap_is_a_warning_never_a_failure() -> None:
    finding = auditor.PageFinding(page=4, figure_gap=True, figure_gap_frac=0.31, figure_gap_side="below")
    issues = auditor.page_issues(finding, total_pages=9)
    assert [(i.level, i.tag) for i in issues] == [(auditor.WARNING, "FIGURE_GAP")]
    assert "0.31" in issues[0].detail and "below" in issues[0].detail
