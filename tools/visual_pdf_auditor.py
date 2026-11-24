#!/usr/bin/env python3
"""
Visual PDF Auditor — heuristic page-image analysis for academic reports.

Renders PDF pages to PNG via pdftoppm (no PyMuPDF required), then analyzes
each page for common visual risks in academic PDF output:

  - Near-blank pages (almost no ink at all)
  - Excessive whitespace (content stopping well short of the page bottom)
  - Large blank gaps above, below or beside the figures of a figure page
  - Ink/tone blocks touching page edges (possible clipping)
  - Possible orphan headings near page bottom
  - Suspiciously low content density
  - Table-like regions (grid/banding patterns)

Every finding is classified in exactly one place — ``page_issues()``. The
severity decision, the stderr header, the per-page tag list and ``visual_qa.md``
all read from it, so the report can never contradict itself.

Output artifacts:
  - Rendered page PNGs in <outdir>/rendered/page-*.png
  - Contact sheet (thumbnail grid) at <outdir>/contact_sheet.png
  - Report at <outdir>/visual_qa.md
  - Pixel hash per page at <outdir>/page_hashes.json; the next audit into the
    same <outdir> lists the changed pages in visual_qa.md and draws them in
    <outdir>/changed_contact_sheet.png
  - Optional JSON output with --json

Where artifacts land (see ``default_output_dir()``): a PDF inside the content
root keeps them in the content build tree; a PDF outside it keeps them beside
itself, never in the academic tree. ``-o/--output`` overrides both.

Exit codes:
  0 = PASS or PASS_WITH_WARNINGS
  1 = FAIL (probable defects)
  2 = fatal error (PDF not found, render failed, etc.)

Dependencies:
  - pdftoppm (from poppler-utils)
  - Pillow (PIL)

Integration note:
  This tool can be called from validate_report.py by adding a 'visual_pdf'
  validator. See pdf_layout_validation() in validate_report.py — the visual
  auditor complements that text-based check by analyzing page images.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from PIL import Image, ImageFilter, ImageStat

from report_config import CONTENT_ROOT


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_DPI = 150  # ~0.17 mm/px — good balance for heuristics
EDGE_MARGIN_PX = 5  # threshold from page edge to check for clipping
MIN_CONTENT_FRAC = 0.005  # ink fraction below this → WARNING
VERY_LOW_FRAC = 0.001  # ink fraction below this → FAIL (near-blank)
TABLE_EDGE_THRESHOLD = 0.004  # edge-pixel fraction to suspect a table

# Edge clipping — ink at the paper edge is LOCAL evidence, so it is measured
# locally. Averaging the 5 px strip over the full page height made the check
# unable to fire: at 150 DPI that strip is 5 × 1754 = 8 770 px and one clipped
# line of text darkens roughly 100 of them (1.1 %), always below the old 2 %
# page-wide threshold. The strip is scanned in overlapping bands instead, and
# one inked band is enough.
# The unit is a ROW of that strip, not a band. A band tall enough to hold a
# line with ascenders is about three times the x-height of a line without
# them, so the same clipped run measured 0.53 of its band in the first sample
# and 0.16 in the second. A threshold tuned on either one misses the other:
# it was tracking typography, not evidence. A row is inked or it is not.
EDGE_ROW_INK_MIN = 0.40  # fraction of the strip's width that makes a row inked.
# Measured across the corpus: a clipped row reaches 0.80 while every row of
# every clean page — covers, footers, page numbers and header rules included —
# measures 0.000, so the number sits in a wide empty gap.
EDGE_ROW_RUN_IN = 0.01  # consecutive inked rows (inches) required to report.
# Two rows at 150 DPI. The width threshold above already rejects dust — a
# speck covers a fifth of the strip, not two fifths — so this only guards
# against a single stray row. Deliberately not larger: on a real render the
# antialiased stems of a clipped line of lowercase type hold full coverage
# for just two rows before they fade, and that page loses content all the same.
EDGE_BAND_DARK = 200  # grey level below which an edge pixel counts as ink

# Excessive whitespace — a page whose content stops well short of the bottom
# while more content follows. This is the check the docstring always promised;
# MIN_CONTENT_FRAC only ever caught pages that were nearly empty (< 0.5 % ink),
# never a half-empty one (2–4 % ink).
WHITESPACE_TAIL_MIN_FRAC = 0.25  # trailing blank space, as a fraction of page
# height, that turns into a warning — a full quarter of the page below the last
# line. Measured over the reference corpus: pages that simply end on a short
# last line reach 0.21, the pages left half-empty by an injected page break
# reach 0.29–0.31, so the threshold sits between the two clusters.
WHITESPACE_INK_ROW_MIN = 0.002  # row ink fraction above which a row has content
WHITESPACE_SOLID_RUN_FRAC = 0.60  # a page whose ink is one contiguous block
# this tall (fraction of the used region) is figure/image dominated: a float
# page ends where its figure ends, which is not stray whitespace. Text and
# tables break into lines, so they never come close — 0.21 is the highest value
# measured on the reference corpus.

# Figure gaps (skill-visual-organization S4) — the whitespace check above
# exempts figure-dominated pages, so a float page with its figure centred
# between two blank bands, or a pinned figure followed by a third of a page of
# nothing, never surfaced. A page counts as a figure page when one contiguous
# inked block is at least FIGURE_BLOCK_MIN_FRAC of the page height: text and
# table lines break into rows far shorter than that.
FIGURE_BLOCK_MIN_FRAC = 0.15
FIGURE_GAP_MIN_FRAC = 0.25  # blank band, as a fraction of page height, worth
# a warning — the same quarter page the whitespace tail uses.
FIGURE_GAP_TOP_FRAC = 0.10  # where the text area starts (2.5 cm of A4 is
# 0.084); a running header above it is not content to measure from.

# Orphan-heading detection — "a short ink strip whose blank tail reaches the
# page bottom". Every pixel threshold below is normalized against `dpi`
# (inch * dpi); every other threshold is a fraction of page height/width.
ORPHAN_FOOTER_BAND_FRAC = 0.10  # bottom 10 % excluded from the scan (footer)
ORPHAN_INK_ROW_MIN = 0.01  # row ink fraction above this counts as "substantive"
ORPHAN_BLANK_TAIL_MIN_FRAC = 0.20  # blank tail below the last ink row, as a
# fraction of page height, required to even consider an orphan
ORPHAN_BLANK_ROW_MAX = 0.002  # row ink fraction at/below this is "blank" for
# the grow-up strip scan (below a table's vertical-rule density on purpose)
ORPHAN_LINE_MERGE_GAP_IN = 0.14  # blank run (inches) bridged when growing the
# strip upward — merges wrapped heading/paragraph lines
ORPHAN_MIN_HEIGHT_IN = 0.06  # minimum strip height (inches) to be heading-shaped
ORPHAN_MAX_HEIGHT_IN = 0.45  # maximum strip height (inches) to be heading-shaped
ORPHAN_MIN_ROW_FRAC = 0.04  # minimum peak row ink fraction within the strip
ORPHAN_MAX_ROW_FRAC = 0.90  # maximum peak row ink fraction within the strip
ORPHAN_MIN_TOP_FRAC = 0.20  # strip must start below this fraction of page height
ORPHAN_CONTENT_ABOVE_MIN_FRAC = 0.005  # min ink fraction required above the
# strip (between 15 % of height and the strip start) — rejects title-only pages


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class PageFinding:
    page: int
    near_blank: bool = False
    blank_reason: Optional[str] = None
    orphan_heading: bool = False
    orphan_confidence: Optional[float] = None
    edge_clipping: bool = False
    edge_side: Optional[str] = None
    low_density: bool = False
    density_frac: Optional[float] = None
    excessive_whitespace: bool = False
    whitespace_frac: Optional[float] = None
    figure_gap: bool = False
    figure_gap_frac: Optional[float] = None
    figure_gap_side: Optional[str] = None
    table_suspect: bool = False
    table_confidence: Optional[float] = None
    ink_center_of_mass_y: Optional[float] = None
    note: str = ""


@dataclass
class AuditResult:
    pdf_path: str
    total_pages: int = 0
    page_width_px: int = 0
    page_height_px: int = 0
    findings: list = field(default_factory=list)
    contact_sheet: str = ""
    artifacts_dir: str = ""
    render_success: bool = True
    severity: str = "PASS"  # PASS | PASS_WITH_WARNINGS | FAIL
    summary: str = ""
    # Pages whose pixels differ from the previous audit in the same output
    # directory; None when there is no comparable previous audit.
    changed_pages: Optional[list] = None


# ---------------------------------------------------------------------------
# Classification — the single definition of what a finding means
# ---------------------------------------------------------------------------

FAILURE = "FAILURE"  # a probable defect: the PDF should not ship like this
WARNING = "WARNING"  # a judgement call: a human has to look at the page
INFO = "INFO"  # context only, never affects severity


@dataclass
class PageIssue:
    level: str
    tag: str
    detail: str


def page_issues(finding: PageFinding, total_pages: int) -> list[PageIssue]:
    """Classify one page's findings. This is the ONLY place that decides what
    counts as a failure and what counts as a warning.

    The severity decision, the stderr header, the per-page tag list and
    ``visual_qa.md`` all derive from this function. They used to carry their own
    copies of the predicate, which drifted until the tool printed ``FAIL`` and
    ``0 failures`` in the same block.
    """
    issues: list[PageIssue] = []

    if finding.near_blank:
        issues.append(PageIssue(FAILURE, "NEAR_BLANK", finding.blank_reason or ""))

    if finding.edge_clipping:
        issues.append(
            PageIssue(FAILURE, "EDGE_CLIPPING", f"{finding.edge_side} edge"),
        )

    if finding.low_density:
        # Sparse interior pages are defects; the cover is sparse by design and
        # the closing page may hold nothing but a short bibliography.
        interior = 1 < finding.page < total_pages
        issues.append(
            PageIssue(
                FAILURE if interior else WARNING,
                "LOW_DENSITY",
                f"ink fraction={finding.density_frac}",
            ),
        )

    if finding.orphan_heading:
        issues.append(
            PageIssue(
                WARNING, "ORPHAN_HEADING", f"confidence={finding.orphan_confidence}",
            ),
        )

    if finding.excessive_whitespace:
        issues.append(
            PageIssue(
                WARNING,
                "EXCESSIVE_WHITESPACE",
                f"blank tail={finding.whitespace_frac} of page height",
            ),
        )

    if finding.figure_gap:
        issues.append(
            PageIssue(
                WARNING,
                "FIGURE_GAP",
                f"blank gap={finding.figure_gap_frac} of page height {finding.figure_gap_side} the figure",
            ),
        )

    if finding.table_suspect:
        issues.append(
            PageIssue(
                INFO, "TABLE_SUSPECT", f"confidence={finding.table_confidence}",
            ),
        )

    return issues


def count_flagged_pages(result: AuditResult, level: str) -> int:
    """Number of pages carrying at least one issue of *level*."""
    return sum(
        1
        for f in result.findings
        if any(i.level == level for i in page_issues(f, result.total_pages))
    )


def decide_severity(result: AuditResult) -> str:
    """PASS | PASS_WITH_WARNINGS | FAIL, from the classified findings."""
    if count_flagged_pages(result, FAILURE) > 0:
        return "FAIL"
    if count_flagged_pages(result, WARNING) > 0:
        return "PASS_WITH_WARNINGS"
    return "PASS"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_pdf_to_pngs(
    pdf_path: Path,
    output_dir: Path,
    dpi: int = DEFAULT_DPI,
) -> tuple[list[Path], int, int, int]:
    """Render PDF pages to grayscale PNG images via pdftoppm.

    Returns (png_paths, width_px, height_px, num_pages).
    """
    # Clean stale images from previous audit runs — prevents duplicate
    # page-1.png vs page-01.png collisions in the glob.
    for stale in output_dir.glob("page-*.png"):
        stale.unlink(missing_ok=True)

    # pdftoppm outputs prefix-1.png, prefix-2.png, …
    prefix = output_dir / "page"

    cmd = [
        "pdftoppm",
        "-png",
        "-r", str(dpi),
        "-gray",           # render as grayscale — saves I/O, enough for heuristics
        "-aa", "yes",
        "-aaVector", "yes",
        str(pdf_path),
        str(prefix),
    ]

    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=180,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"pdftoppm failed (exit {proc.returncode}): "
            f"{proc.stderr.strip() or '(no stderr)'}"
        )

    pngs = sorted(
        output_dir.glob("page-*.png"),
        key=lambda p: int(re.search(r"page-(\d+)", p.stem).group(1)),
    )

    if not pngs:
        raise RuntimeError("pdftoppm produced no output PNGs")

    # Collect dimensions from the first page
    with Image.open(pngs[0]) as img:
        w, h = img.size

    return pngs, w, h, len(pngs)


# ---------------------------------------------------------------------------
# Image-analysis helpers
# ---------------------------------------------------------------------------


def _pixels(img: Image.Image) -> list:
    """Return flat pixel list — compatible when ``getdata()`` is removed."""
    # getdata() is deprecated in Pillow 12; try the replacement first.
    try:
        return list(img.get_flattened_data())
    except AttributeError:
        return list(img.getdata())


def _grayscale(img: Image.Image) -> Image.Image:
    return img if img.mode == "L" else img.convert("L")


def ink_fraction(img: Image.Image, threshold: int = 240) -> float:
    """Proportion of pixels darker than *threshold* (i.e. ink/toner)."""
    gs = _grayscale(img)
    pixels = _pixels(gs)
    dark = sum(1 for p in pixels if p < threshold)
    return dark / len(pixels) if pixels else 0.0




def variance(img: Image.Image) -> float:
    """Normalised standard deviation of pixel intensities (0..1)."""
    stat = ImageStat.Stat(_grayscale(img))
    return stat.stddev[0] / 255.0 if stat.stddev[0] else 0.0


def edge_pixel_fraction(img: Image.Image) -> float:
    """Fraction of pixels that are strong edges (FIND_EDGES filter)."""
    gs = _grayscale(img)
    edges = gs.filter(ImageFilter.FIND_EDGES)
    stat = ImageStat.Stat(edges)
    mean = stat.mean[0]
    threshold = max(30, mean * 2.5)
    pixels = _pixels(edges)
    n_edge = sum(1 for p in pixels if p > threshold)
    return n_edge / len(pixels) if pixels else 0.0


def center_of_mass_y(img: Image.Image) -> float:
    """Vertical centroid of ink (0 = top, 1 = bottom)."""
    gs = _grayscale(img)
    h = gs.height
    total_dark = 0
    weighted = 0
    for y in range(h):
        for x in range(gs.width):
            if gs.getpixel((x, y)) < 240:
                total_dark += 1
                weighted += y
    if total_dark == 0:
        return 0.5
    return weighted / total_dark / h


# ---------------------------------------------------------------------------
# Heuristic checks (per page)
# ---------------------------------------------------------------------------


def check_near_blank(img: Image.Image) -> tuple[bool, Optional[str]]:
    """Return (is_near_blank, reason)."""
    gs = _grayscale(img)
    pixels = _pixels(gs)
    n_ink = sum(1 for p in pixels if p < 240)
    frac = n_ink / len(pixels)

    if frac < VERY_LOW_FRAC:
        return True, f"density={frac:.6f} (below VERY_LOW_FRAC={VERY_LOW_FRAC})"
    if frac < MIN_CONTENT_FRAC and variance(img) < 0.03:
        return True, f"density={frac:.6f}, variance too low"

    return False, None


def has_full_bleed_background(img: Image.Image, margin: int = 8) -> bool:
    """Detect if a page has a cover-like background image reaching the edges.

    Unlike a strict "full-bleed" check that requires all 4 sides, this detects
    also partial-bleed decorative backgrounds (common in UNL cover pages):

      Evidence — at least one is required:
        (A) Top edge near a corner has >15 % dark pixels (header decoration)
        (B) Right edge near top has >15 % dark pixels (side decoration)

      Disqualifiers — all must hold:
        (C) Left edge is clean (<2 % dark) throughout — distinguishes
            background corner decoration from full-width content clipping
        (D) Bottom edge is clean (<2 % dark)
        (E) Ink on the right edge is concentrated in the top 15 % and/or
            bottom 15 % of the page (corner decorations), not spanning
            the full page height

    Returns True when the page has background-like edge ink characteristic
    of a decorative cover, as opposed to content accidentally clipping.
    """
    w, h = img.size
    gs = _grayscale(img)

    # Right-edge per-band analysis
    right_full = gs.crop((w - margin, 0, w, h))
    rpx = _pixels(right_full)
    r_h = len(rpx) // margin  # approximate pixel rows
    r_dark_total = sum(1 for p in rpx if p < 200) / len(rpx) if rpx else 0.0

    # Right edge top 15 % band
    r_top_h = max(1, int(h * 0.15))
    right_top = gs.crop((w - margin, 0, w, r_top_h))
    rtp = _pixels(right_top)
    r_top_frac = sum(1 for p in rtp if p < 200) / len(rtp) if rtp else 0.0

    # Right edge bottom 15 % band
    r_bot = gs.crop((w - margin, h - r_top_h, w, h))
    rbp = _pixels(r_bot)
    r_bot_frac = sum(1 for p in rbp if p < 200) / len(rbp) if rbp else 0.0

    # Top edge left corner (first 15 % of width)
    t_left_w = max(1, int(w * 0.15))
    top_left = gs.crop((0, 0, t_left_w, margin))
    tlp = _pixels(top_left)
    top_left_frac = sum(1 for p in tlp if p < 200) / len(tlp) if tlp else 0.0

    # Top edge right corner (last 15 % of width)
    top_right = gs.crop((w - t_left_w, 0, w, margin))
    trp = _pixels(top_right)
    top_right_frac = sum(1 for p in trp if p < 200) / len(trp) if trp else 0.0

    # Left edge (should be clean for a decorated cover)
    left_edge = gs.crop((0, 0, margin, h))
    lep = _pixels(left_edge)
    left_frac = sum(1 for p in lep if p < 200) / len(lep) if lep else 0.0

    # Bottom edge (should be clean)
    bottom_edge = gs.crop((0, h - margin, w, h))
    bep = _pixels(bottom_edge)
    bot_frac = sum(1 for p in bep if p < 200) / len(bep) if bep else 0.0

    # Criteria
    crit_a = top_left_frac > 0.15 or top_right_frac > 0.15
    crit_b = r_top_frac > 0.15
    crit_c = left_frac < 0.02
    crit_d = bot_frac < 0.02
    # Right-edge ink is NOT spanning full height — it's concentrated
    # in top and/or bottom corners
    if r_dark_total > 0.02:
        r_mid_h = gs.crop((w - margin, int(h * 0.25), w, int(h * 0.75)))
        rmp = _pixels(r_mid_h)
        r_mid_frac = sum(1 for p in rmp if p < 200) / len(rmp) if rmp else 0.0
        crit_e = r_mid_frac < 0.01
    else:
        crit_e = True  # No right-edge ink at all — trivially satisfied

    # A cover is identified by what it HAS, not by what it lacks.
    #
    # Only crit_a and crit_b are evidence: ink actually reaching a paper edge.
    # crit_c, crit_d and crit_e are disqualifiers — every one of them is
    # satisfied by any page with tidy margins, including a blank one. Counting
    # them toward a "two out of five" score meant absence of ink was treated as
    # proof of artwork, and the function returned True for ordinary body pages.
    has_edge_artwork = crit_a or crit_b
    return has_edge_artwork and crit_c and crit_d and crit_e


def _longest_inked_run(strip: Image.Image) -> int:
    """Longest run of consecutive rows that are meaningfully inked.

    A row, not a band, is the natural unit here. Averaging over a band
    reintroduces the very dilution this check exists to avoid, just at a
    smaller scale: a band tall enough to hold a line of text with ascenders
    is roughly three times the x-height of a line without them, so the same
    clipped run measures 0.53 of the band in one font and 0.16 in another.
    Tuned on the first, it misses the second — a real page overflowing by
    361 pt audited clean.

    A row is either inked or it is not, whatever the type size, so the run
    length carries the evidence and the threshold stops tracking typography.
    """
    gs = _grayscale(strip)
    w, h = gs.size
    if w == 0 or h == 0:
        return 0

    px = _pixels(gs)
    longest = current = 0
    for y in range(h):
        row = px[y * w : (y + 1) * w]
        inked = sum(1 for p in row if p < EDGE_BAND_DARK) / w
        current = current + 1 if inked >= EDGE_ROW_INK_MIN else 0
        longest = max(longest, current)
    return longest


def check_edge_clipping(
    img: Image.Image, margin: int = EDGE_MARGIN_PX, *, dpi: int = DEFAULT_DPI,
) -> Optional[str]:
    """Return edge name if ink reaches the page edge, else None.

    Evidence is local: a single clipped line of text has to trip this, and a
    whole-strip average cannot see one — it is about 1 % of a full-height
    strip, below any threshold ordinary page furniture would survive.

    The unit is a row of the strip, and the evidence is how many inked rows
    run consecutively. Anything shaped like a line of type clears the minimum
    run; anti-aliasing dust and a stray speck do not, whatever the type size.

    Pages with a full-bleed background (detected by *has_full_bleed_background*)
    are skipped — the background image is expected to reach the paper edge
    and is NOT actual content clipping.
    """
    if has_full_bleed_background(img):
        return None

    w, h = img.size
    gs = _grayscale(img)
    min_run = max(2, round(EDGE_ROW_RUN_IN * dpi))

    # Top and bottom strips are rotated so that every strip is scanned
    # row-by-row across its short axis by the same code.
    rotate = Image.Transpose.ROTATE_90
    strips = {
        "left": gs.crop((0, 0, margin, h)),
        "right": gs.crop((w - margin, 0, w, h)),
        "top": gs.crop((0, 0, w, margin)).transpose(rotate),
        "bottom": gs.crop((0, h - margin, w, h)).transpose(rotate),
    }
    for side, strip in strips.items():
        if _longest_inked_run(strip) >= min_run:
            return side
    return None


def _row_ink_profile(gs: Image.Image, threshold: int = 240) -> list[float]:
    """Return, for each row of *gs* (already grayscale), the fraction of
    pixels darker than *threshold*."""
    px_data = _pixels(gs)
    w = gs.width
    return [
        sum(1 for p in px_data[y * w : (y + 1) * w] if p < threshold) / w
        for y in range(gs.height)
    ]


def _grow_up(rows: list[float], last: int, blank_row_max: float, merge_gap: int) -> int:
    """Walk upward from row *last*, extending the strip start while a blank
    run shorter than *merge_gap* rows is bridged (merged into the strip)."""
    start = last
    blank_run = 0
    y = last
    while y > 0:
        y -= 1
        if rows[y] > blank_row_max:
            start = y
            blank_run = 0
        else:
            blank_run += 1
            if blank_run > merge_gap:
                break
    return start


def check_orphan_heading(
    img: Image.Image,
    *,
    dpi: int = DEFAULT_DPI,
    is_cover: bool = False,
    is_last_page: bool = False,
) -> tuple[bool, Optional[float]]:
    """Check for a possible orphan heading stranded near the page bottom.

    Signature: a short ink strip (heading-shaped) whose blank tail reaches
    the page bottom — because its body content was pushed to the next page.
    Scans the whole page below ~15 % of height, excluding only the bottom
    ``ORPHAN_FOOTER_BAND_FRAC`` footer band. All pixel thresholds are
    normalized against *dpi*.

    Two pages are exempt by index rather than by image analysis. The cover is
    decorative and sparse by design. The last page cannot strand a heading at
    all: an orphan means the heading's content moved onto the *following*
    page, and there is no following page — trailing blank space there is just
    where the document ends.
    """
    if is_cover or is_last_page:
        return False, None

    w, h = img.size
    px_per_in = max(1.0, float(dpi))
    scan_end = int(h * (1.0 - ORPHAN_FOOTER_BAND_FRAC))
    rows = _row_ink_profile(_grayscale(img), threshold=240)

    # 1. last substantive ink row inside the scan region
    last = None
    for y in range(scan_end - 1, -1, -1):
        if rows[y] > ORPHAN_INK_ROW_MIN:
            last = y
            break
    if last is None:
        return False, None  # blank page — near_blank owns it

    # 2. blank tail must reach the scan bottom
    blank_tail = (scan_end - 1 - last) / h
    if blank_tail < ORPHAN_BLANK_TAIL_MIN_FRAC:
        return False, None

    # 3. grow the strip upward, merging wrapped lines via the DPI-normalized gap
    merge_gap = max(1, round(ORPHAN_LINE_MERGE_GAP_IN * px_per_in))
    start = _grow_up(rows, last, ORPHAN_BLANK_ROW_MAX, merge_gap)

    # 4. heading-shaped guards
    strip_in = (last - start + 1) / px_per_in
    if not (ORPHAN_MIN_HEIGHT_IN <= strip_in <= ORPHAN_MAX_HEIGHT_IN):
        return False, None
    peak = max(rows[start : last + 1])
    if not (ORPHAN_MIN_ROW_FRAC <= peak < ORPHAN_MAX_ROW_FRAC):
        return False, None
    if start < h * ORPHAN_MIN_TOP_FRAC:
        return False, None
    above = img.crop((0, int(h * 0.15), w, start))
    if ink_fraction(above) < ORPHAN_CONTENT_ABOVE_MIN_FRAC:
        return False, None

    return True, round(min(1.0, blank_tail / 0.5), 2)


def check_low_density(img: Image.Image) -> tuple[bool, float]:
    """Return (is_low_density, ink_fraction)."""
    frac = ink_fraction(img)
    return frac < MIN_CONTENT_FRAC, round(frac, 6)


def check_excessive_whitespace(
    img: Image.Image,
    *,
    is_cover: bool = False,
    is_last_page: bool = False,
) -> tuple[bool, Optional[float]]:
    """Check whether content stops well short of the page bottom.

    Returns (is_excessive, blank_tail_fraction). The signature this looks for
    is a page carrying ordinary amounts of ink whose last line sits a quarter
    of a page or more above the footer band, while the document continues on
    the next page — what an injected ``\\Needspace`` or a forced page break
    leaves behind. It is deliberately a WARNING: whether that whitespace is a
    defect or a wanted break is a human judgement.

    Four kinds of legitimately short page are excluded:

      - the cover and the closing page (by index, as the orphan check does):
        nothing follows the last page, so its trailing space is just the end
        of the document;
      - a page too empty to be content at all — ``check_near_blank()`` and
        ``check_low_density()`` already own those;
      - a page dominated by one figure: its ink is a single contiguous block
        rather than lines of text, and a float page ends where its figure ends.

    A page that ends a chapter is NOT excluded, because nothing in the page
    image distinguishes it from the same page broken by accident. The warning
    points at the page and leaves the call to the reader.
    """
    if is_cover or is_last_page:
        return False, None

    if ink_fraction(img) < MIN_CONTENT_FRAC:
        return False, None  # the density checks own this page

    gs = _grayscale(img)
    h = gs.height
    rows = _row_ink_profile(gs)
    scan_end = int(h * (1.0 - ORPHAN_FOOTER_BAND_FRAC))  # ignore the footer band
    ink_rows = [y for y in range(scan_end) if rows[y] > WHITESPACE_INK_ROW_MIN]
    if not ink_rows:
        return False, None

    first, last = ink_rows[0], ink_rows[-1]
    blank_tail = (scan_end - 1 - last) / h
    if blank_tail < WHITESPACE_TAIL_MIN_FRAC:
        return False, None

    # Figure-dominated page: the ink is one contiguous block, not text lines.
    used = last - first + 1
    longest_run = 0
    run = 0
    for y in range(first, last + 1):
        run = run + 1 if rows[y] > WHITESPACE_INK_ROW_MIN else 0
        longest_run = max(longest_run, run)
    if longest_run / used > WHITESPACE_SOLID_RUN_FRAC:
        return False, None

    return True, round(blank_tail, 3)


def check_figure_gaps(
    img: Image.Image,
    *,
    is_cover: bool = False,
    is_last_page: bool = False,
) -> tuple[bool, Optional[float], Optional[str]]:
    """Report a large blank band on a page that carries a figure.

    Returns (is_reported, gap_fraction, side) where side is ``above`` (from
    the top of the text area to the first content), ``below`` (from the last
    content to the footer band) or ``between`` (inside the page, between two
    blocks of content). Only pages with a figure-sized solid block are
    measured; text pages belong to ``check_excessive_whitespace()``. Like that
    check it is a WARNING: whether the gap is wanted is a human judgement.
    The cover and the closing page are exempt for the same reasons.
    """
    if is_cover or is_last_page:
        return False, None, None
    if ink_fraction(img) < MIN_CONTENT_FRAC:
        return False, None, None  # the density checks own this page

    gs = _grayscale(img)
    h = gs.height
    rows = _row_ink_profile(gs)
    top = int(h * FIGURE_GAP_TOP_FRAC)
    scan_end = int(h * (1.0 - ORPHAN_FOOTER_BAND_FRAC))
    inked = [rows[y] > WHITESPACE_INK_ROW_MIN for y in range(scan_end)]

    longest = run = 0
    for y in range(top, scan_end):
        run = run + 1 if inked[y] else 0
        longest = max(longest, run)
    if longest / h < FIGURE_BLOCK_MIN_FRAC:
        return False, None, None

    ink_rows = [y for y in range(top, scan_end) if inked[y]]
    first, last = ink_rows[0], ink_rows[-1]
    candidates = [((first - top) / h, "above"), ((scan_end - 1 - last) / h, "below")]
    blank = 0
    for y in range(first, last + 1):
        if inked[y]:
            if blank:
                candidates.append((blank / h, "between"))
            blank = 0
        else:
            blank += 1
    gap, side = max(candidates, key=lambda item: item[0])
    if gap < FIGURE_GAP_MIN_FRAC:
        return False, None, None
    return True, round(gap, 3), side


def check_table_like(img: Image.Image) -> tuple[bool, Optional[float]]:
    """Detect likely table regions via edge density + row-band transitions."""
    gs = _grayscale(img)
    edges = gs.filter(ImageFilter.FIND_EDGES)
    stat = ImageStat.Stat(edges)

    if (stat.mean[0] or 0) < 5:
        return False, None

    epf = edge_pixel_fraction(img)
    if epf < TABLE_EDGE_THRESHOLD:
        return False, None

    # Build horizontal projection
    px_data = _pixels(gs)
    row_ink = []
    for y in range(gs.height):
        row = px_data[y * gs.width : (y + 1) * gs.width]
        row_ink.append(sum(1 for p in row if p < 200) / len(row))

    transitions = sum(
        1 for i in range(1, len(row_ink))
        if (row_ink[i] > 0.02) != (row_ink[i - 1] > 0.02)
    )

    if transitions > 30:
        conf = round(min(1.0, (transitions - 30) / 80), 2)
        return True, conf

    return False, None


# ---------------------------------------------------------------------------
# Contact sheet
# ---------------------------------------------------------------------------


def create_contact_sheet(
    png_paths: list[Path],
    output_path: Path,
    cols: int = 4,
    thumb_size: tuple[int, int] = (300, 424),
) -> Path:
    """Build a grid thumbnail of all pages and save as PNG.

    Each thumbnail is labelled with the page number in the top-left corner.
    """
    thumbs: list[Image.Image] = []
    for p in png_paths:
        im = Image.open(p)
        im.thumbnail(thumb_size, Image.LANCZOS)
        thumbs.append(im)

    if not thumbs:
        msg = "No page images for contact sheet"
        raise ValueError(msg)

    rows_needed = (len(thumbs) + cols - 1) // cols
    gap = 4
    total_w = cols * thumb_size[0] + (cols - 1) * gap
    total_h = rows_needed * thumb_size[1] + (rows_needed - 1) * gap

    sheet = Image.new("RGB", (total_w, total_h), (245, 245, 245))
    from PIL import ImageDraw  # lazy import

    for idx, page_img in enumerate(thumbs):
        x = (idx % cols) * (thumb_size[0] + gap)
        y = (idx // cols) * (thumb_size[1] + gap)
        sheet.paste(page_img, (x, y))
        draw = ImageDraw.Draw(sheet)
        draw.text((x + 3, y + 3), str(idx + 1), fill=(200, 0, 0))

    sheet.save(output_path, "PNG")
    return output_path


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------


def _now_str() -> str:
    """Return a compact timestamp via /bin/date."""
    try:
        return subprocess.run(
            ["date", "+%Y-%m-%d %H:%M:%S"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        return "(unknown date)"


PAGE_HASHES_NAME = "page_hashes.json"
CHANGED_CONTACT_SHEET_NAME = "changed_contact_sheet.png"


def _changed_pages_text(changed: Optional[list]) -> str:
    if changed is None:
        return "first audit, inspect every page"
    if not changed:
        return "none"
    pages = ", ".join(str(p) for p in changed)
    return f"{pages} (inspect these; unchanged pages keep the previous verdict)"


def _previous_page_hashes(output_dir: Path, dpi: int) -> Optional[list]:
    """The previous audit's page hashes at the same DPI, or None when unusable."""
    try:
        data = json.loads((output_dir / PAGE_HASHES_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("dpi") != dpi or not isinstance(data.get("pages"), list):
        return None
    return data["pages"]


def _page_hash(img: Image.Image) -> str:
    """Hash of the rendered pixels, so PDF metadata from a rebuild never counts."""
    return hashlib.sha256(f"{img.mode}{img.size}".encode() + img.tobytes()).hexdigest()


def write_visual_qa_report(result: AuditResult, output_path: Path) -> Path:
    """Write visual_qa.md — human-readable per-page audit report."""
    sev = result.severity
    icon = {"PASS": "✅", "PASS_WITH_WARNINGS": "⚠️", "FAIL": "❌"}.get(sev, "❓")

    lines = [
        f"# Visual QA Report — `{Path(result.pdf_path).name}`",
        "",
        "## Summary",
        "",
        f"- **Status**: {icon} {sev}",
        f"- **Failure pages**: {count_flagged_pages(result, FAILURE)}",
        f"- **Warning pages**: {count_flagged_pages(result, WARNING)}",
        f"- **Pages analysed**: {result.total_pages}",
        f"- **Render resolution**: {result.page_width_px}×{result.page_height_px} px ({DEFAULT_DPI} DPI)",
    ]
    if result.contact_sheet:
        lines.append(f"- **Contact sheet**: `{result.contact_sheet}`")
    lines.append(f"- **Changed pages**: {_changed_pages_text(result.changed_pages)}")
    lines.append(f"- **Artifacts**: `{result.artifacts_dir}/`")
    lines.append("")

    lines.append("## Severity Guide")
    lines.append("")
    lines.append("| Level | Meaning |")
    lines.append("|-------|---------|")
    lines.append("| **PASS** | No issues detected |")
    lines.append("| **PASS_WITH_WARNINGS** | Minor issues — inspect manually |")
    lines.append("| **FAIL** | Probable defects requiring correction |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Per-Page Findings")
    lines.append("")

    # Same classifier as the severity decision and the stderr header.
    flagged = [
        (f, page_issues(f, result.total_pages)) for f in result.findings
    ]
    flagged = [(f, issues) for f, issues in flagged if issues]

    if not flagged:
        lines.append("*No significant issues detected.*")
        lines.append("")

    for f, issues in flagged:
        lines.append(f"### Page {f.page}")
        lines.append("")
        if f.ink_center_of_mass_y is not None:
            lines.append(f"- Center of mass (Y): {f.ink_center_of_mass_y:.3f}")
        for issue in issues:
            lines.append(f"- **{issue.level}** · {issue.tag} — {issue.detail}")
        if f.note:
            lines.append(f"- Note: {f.note}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        f"_Generated by `visual_pdf_auditor.py` on {_now_str()}_"
    )
    lines.append("")

    text = "\n".join(lines) + "\n"
    output_path.write_text(text, encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# Main audit pipeline
# ---------------------------------------------------------------------------


def audit_pdf(
    pdf_path: Path,
    output_dir: Path,
    dpi: int = DEFAULT_DPI,
) -> AuditResult:
    """Run full visual audit on *pdf_path*, placing artifacts under *output_dir*."""
    pdf_path = pdf_path.resolve()
    output_dir = output_dir.resolve()
    artifacts_dir = output_dir / "rendered"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    result = AuditResult(
        pdf_path=str(pdf_path),
        artifacts_dir=str(artifacts_dir),
    )

    # ---- 1. Render ----
    try:
        pngs, page_w, page_h, n_pages = render_pdf_to_pngs(
            pdf_path, artifacts_dir, dpi,
        )
    except (FileNotFoundError, RuntimeError, subprocess.TimeoutExpired) as exc:
        result.render_success = False
        result.severity = "FAIL"
        result.summary = f"Render failed: {exc}"
        return result

    result.page_width_px = page_w
    result.page_height_px = page_h
    result.total_pages = n_pages
    previous_hashes = _previous_page_hashes(output_dir, dpi)
    page_hashes: list[str] = []

    # ---- 2. Per-page analysis ----
    for idx, png in enumerate(pngs):
        page_num = idx + 1
        with Image.open(png) as img:
            page_hashes.append(_page_hash(img))
            finding = PageFinding(page=page_num)

            # Near-blank
            blank, reason = check_near_blank(img)
            finding.near_blank = blank
            finding.blank_reason = reason

            # Edge clipping — individual pages with full-bleed background
            # are handled inside check_edge_clipping()
            side = check_edge_clipping(img, dpi=dpi)
            if side:
                finding.edge_clipping = True
                finding.edge_side = side

            # Orphan heading — the cover (page 1) and the final page are
            # exempted by index, not by has_full_bleed_background() (it returns
            # True even for ordinary/blank pages, so it cannot be used as a
            # guard here). The last page has no following page for content to
            # have been pushed onto, so it cannot strand a heading.
            orphan, conf = check_orphan_heading(
                img,
                dpi=dpi,
                is_cover=(page_num == 1),
                is_last_page=(page_num == n_pages),
            )
            finding.orphan_heading = orphan
            finding.orphan_confidence = conf

            # Low density
            low, dens = check_low_density(img)
            finding.low_density = low
            finding.density_frac = dens

            # Excessive whitespace — same index exemptions as the orphan
            # check: the cover is sparse by design, and the last page has no
            # following content that could have been pulled up onto it.
            blank, tail = check_excessive_whitespace(
                img,
                is_cover=(page_num == 1),
                is_last_page=(page_num == n_pages),
            )
            finding.excessive_whitespace = blank
            finding.whitespace_frac = tail

            # Figure gaps — the pages the whitespace check exempts as
            # figure-dominated; a page it already flagged is not told twice.
            if not blank:
                gap, gap_frac, gap_side = check_figure_gaps(
                    img,
                    is_cover=(page_num == 1),
                    is_last_page=(page_num == n_pages),
                )
                finding.figure_gap = gap
                finding.figure_gap_frac = gap_frac
                finding.figure_gap_side = gap_side

            # Table suspect
            tbl, tblc = check_table_like(img)
            finding.table_suspect = tbl
            finding.table_confidence = tblc

            # Centre of mass
            finding.ink_center_of_mass_y = center_of_mass_y(img)

            result.findings.append(finding)

    # ---- 3. Contact sheet ----
    try:
        cs_path = output_dir / "contact_sheet.png"
        create_contact_sheet(pngs, cs_path)
        result.contact_sheet = str(cs_path)
    except Exception as exc:
        result.contact_sheet = f"ERROR: {exc}"

    # ---- 3b. Changed pages since the previous audit (T7) ----
    if previous_hashes is not None:
        result.changed_pages = [
            index + 1 for index, digest in enumerate(page_hashes)
            if index >= len(previous_hashes) or previous_hashes[index] != digest
        ]
    changed_sheet = output_dir / CHANGED_CONTACT_SHEET_NAME
    changed_sheet.unlink(missing_ok=True)
    if result.changed_pages:
        try:
            create_contact_sheet([pngs[p - 1] for p in result.changed_pages], changed_sheet)
        except Exception:
            pass  # the full contact sheet still covers every page
    (output_dir / PAGE_HASHES_NAME).write_text(
        json.dumps({"dpi": dpi, "pages": page_hashes}, indent=2) + "\n", encoding="utf-8",
    )

    # ---- 4. Severity ---- (classified once, in page_issues())
    failures = count_flagged_pages(result, FAILURE)
    warnings = count_flagged_pages(result, WARNING)
    result.severity = decide_severity(result)

    result.summary = (
        f"{result.total_pages} pages · "
        f"{failures} failures · {warnings} warnings"
    )

    # ---- 5. Report ----
    report_path = output_dir / "visual_qa.md"
    write_visual_qa_report(result, report_path)
    result.summary += f"\nReport: {report_path}"

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


# Code root, kept for callers that import it. Audit artefacts themselves (page
# renders, contact sheet, visual_qa.md) are build output for a specific report,
# so their default location lives in the content tree — but only for PDFs that
# actually belong to it. See default_output_dir().
ROOT = Path(__file__).resolve().parents[1]

AUDIT_DIR_NAME = "visual-audits"


def default_output_dir(
    pdf_path: Path, content_root: Optional[Path] = None,
) -> Path:
    """Where audit artefacts go when ``--output`` is not given.

    Two rules, both of which the old default broke:

      - A PDF that lives under the content root keeps its artefacts inside the
        content build tree (``<content root>/build/visual-audits/…``), where
        the existing report workflows look for them. A PDF from anywhere else
        keeps them beside itself, so auditing a throwaway file in a temp
        directory can never deposit renders in the academic tree.
      - The leaf directory is derived from the PDF's own location, not just its
        basename, so two same-named PDFs from different directories cannot
        overwrite each other's results.
    """
    root = (content_root if content_root is not None else CONTENT_ROOT).resolve()
    pdf = pdf_path.resolve()

    if pdf.is_relative_to(root):
        # e.g. reports/c4/outputs/doc.pdf → build/visual-audits/reports/c4/outputs/doc
        relative = pdf.parent.relative_to(root)
        return root / "build" / AUDIT_DIR_NAME / relative / pdf.stem

    return pdf.parent / AUDIT_DIR_NAME / pdf.stem


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="visual_pdf_auditor",
        description=(
            "Heuristic page-image auditor for academic PDFs. "
            "Renders pages via pdftoppm, analyses with PIL, "
            "and produces a visual_qa.md report + contact sheet."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s report.pdf\n"
            "  %(prog)s report.pdf -o /tmp/audit/\n"
            "  %(prog)s report.pdf --dpi 200 --json\n"
            "\n"
            "Detects: near-blank pages, orphan headings, edge clipping,\n"
            "low content density, and table-like regions.\n"
            "\n"
            "Exit: 0 PASS / PASS_WITH_WARNINGS, 1 FAIL, 2 FATAL\n"
        ),
    )
    parser.add_argument(
        "pdf", type=Path, help="Path to the PDF file to audit",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help=(
            "Output directory. Default: inside the content root, "
            "build/visual-audits/<path-of-the-pdf>/<pdf-stem>/; for a PDF "
            "outside it, <pdf-directory>/visual-audits/<pdf-stem>/"
        ),
    )
    parser.add_argument(
        "--dpi", type=int, default=DEFAULT_DPI,
        help=f"Render resolution in DPI (default: {DEFAULT_DPI})",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Print machine-readable JSON report to stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    pdf = args.pdf
    if not pdf.exists():
        print(f"ERROR: PDF not found: {pdf}", file=sys.stderr)
        return 2

    outdir = args.output or default_output_dir(pdf)

    try:
        result = audit_pdf(pdf, outdir, dpi=args.dpi)
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(asdict(result), indent=2, default=str))
    else:
        _print_summary(result)

    return 0 if result.severity in ("PASS", "PASS_WITH_WARNINGS") else 1


def _print_summary(result: AuditResult) -> None:
    """Pretty-print audit results to stderr/stdout."""
    sep = "=" * 58
    print(f"\n{sep}", file=sys.stderr)
    print(f"  Visual PDF Audit: {Path(result.pdf_path).name}", file=sys.stderr)
    print(f"{sep}", file=sys.stderr)
    print(f"  Severity:  {result.severity}", file=sys.stderr)
    print(f"  Pages:     {result.total_pages}", file=sys.stderr)
    # Same classifier as the severity decision — never a second predicate here.
    failures = count_flagged_pages(result, FAILURE)
    warnings = count_flagged_pages(result, WARNING)
    print(f"  Failures:  {failures}", file=sys.stderr)
    print(f"  Warnings:  {warnings}", file=sys.stderr)
    print(f"{sep}", file=sys.stderr)
    if result.contact_sheet:
        print(f"  Contact:   {result.contact_sheet}", file=sys.stderr)
    print(f"  Report:    {Path(result.artifacts_dir).parent / 'visual_qa.md'}", file=sys.stderr)
    print(f"{sep}\n", file=sys.stderr)

    for f in result.findings:
        issues = page_issues(f, result.total_pages)
        tag = " | ".join(
            f"{i.level}: {i.tag} ({i.detail})" if i.detail else f"{i.level}: {i.tag}"
            for i in issues
        ) or "OK"
        print(f"  [Page {f.page:2d}] {tag}", file=sys.stderr)

    print(file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
