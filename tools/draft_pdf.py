#!/usr/bin/env python3
"""Plain draft PDF of ``body.md`` for the preapproval review.

The user approves content, not layout, so the draft skips the course template:
no cover, no logos, no institutional header, no validators. It renders ``body.md``
(and ``sources.bib`` for the references) through the plain LaTeX template in a
temporary directory outside the report and delivery folders, records the sha256
of the ``body.md`` it rendered next to the PDF (``doc_status`` and the approval
packet read it to detect a stale draft) and opens the PDF in the viewer. The
course template compiles once, in the final build after ``typeset``.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import pdf_viewer
from approval_marker import (
    BODY_NAME,
    draft_preview_dir,
    draft_preview_path,
    draft_record_path,
    sha256_file,
    write_draft_record,
)
from build_latex_report import compile_latex, render_tex
from markdown_image import IMAGE_PATTERN
from report_config import ReportConfig, read_yaml, resolve_in_folder

# report.yml keys that change how the body reads, not how the page looks.
CONTENT_KEYS = ("citation_style", "section_numbering", "figure_placement", "uncited_bibliography")
FIGURES_DIR = "figures"
REMOTE_SOURCE = ("http://", "https://", "data:")


def _copy_figures(body: str, folder: Path, target: Path) -> str:
    """Copy each local figure next to the draft and point the body at the copy.

    Figure paths are relative to the report (or to its ``build/``); the draft
    builds elsewhere, so the files travel with it. A figure that cannot be found
    keeps its path and the compiler front-end reports it.
    """
    copied: dict[str, str] = {}

    def rewrite(match: re.Match[str]) -> str:
        parts = match.group("src").strip().split(" ", 1)
        source = parts[0]
        if not source or source.startswith(REMOTE_SOURCE) or Path(source).suffix == "":
            return match.group(0)
        if source not in copied:
            origin = resolve_in_folder(folder, source)
            if not origin.is_file():
                origin = folder / "build" / source
            if not origin.is_file():
                return match.group(0)
            name = f"{len(copied) + 1:02d}-{origin.name}"
            (target / FIGURES_DIR).mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, target / FIGURES_DIR / name)
            copied[source] = f"{FIGURES_DIR}/{name}"
        tail = f" {parts[1]}" if len(parts) > 1 else ""
        return match.group(0).replace(match.group("src"), copied[source] + tail, 1)

    return IMAGE_PATTERN.sub(rewrite, body)


def _draft_config(folder: Path, target: Path) -> ReportConfig:
    """The plain-template config of the draft: course metadata and cover machinery stay behind."""
    report_yml = folder / "report.yml"
    original = ReportConfig(folder=folder, raw=read_yaml(report_yml) if report_yml.is_file() else {})
    meta = original.metadata
    raw = {
        "type": "essay",
        "backend": "latex",
        "template": "plain",
        "route": "other",
        "publish_global": False,
        "pdf": str(target / "draft.pdf"),
        "tex": str(target / "build" / "main.tex"),
        "body": str(target / BODY_NAME),
        "metadata": {key: meta[key] for key in ("title", "student", "date") if meta.get(key)},
    }
    raw.update({key: original.raw[key] for key in CONTENT_KEYS if key in original.raw})
    bib = original.bib_path
    if bib is not None:
        shutil.copy2(bib, target / bib.name)
        raw["bibliography"] = str(target / bib.name)
    return ReportConfig(folder=target, raw=raw)


def render_draft(folder: Path) -> Path:
    """Build the plain draft of ``folder`` and return its PDF path."""
    folder = Path(folder).resolve()
    body = folder / BODY_NAME
    if not body.is_file():
        raise SystemExit(f"{BODY_NAME} not found in {folder}")
    pdf = draft_preview_path(folder)
    target = draft_preview_dir(folder)
    # Hash first: an edit made while the build runs is not recorded as rendered.
    rendered = sha256_file(body)
    # Old record out first: a failed build must never look fresh.
    draft_record_path(pdf).unlink(missing_ok=True)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    (target / BODY_NAME).write_text(
        _copy_figures(body.read_text(encoding="utf-8"), folder, target), encoding="utf-8"
    )
    config = _draft_config(folder, target)
    config.tex_path.parent.mkdir(parents=True, exist_ok=True)
    config.tex_path.write_text(render_tex(config), encoding="utf-8")
    compile_latex(config)
    write_draft_record(pdf, body, rendered)
    return pdf


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a plain draft PDF of body.md (no cover, logos or course template) "
        "in a temporary directory and open it."
    )
    parser.add_argument("folder", type=Path, help="report folder with body.md")
    parser.add_argument("--no-open", action="store_true", help="build only; do not open the viewer (tests, CI)")
    args = parser.parse_args(argv)
    pdf = render_draft(args.folder)
    print(f"Draft PDF: {pdf}")
    if not args.no_open:
        error = pdf_viewer.open_pdf(pdf)
        print(f"draft not opened: {error}" if error else f"opened {pdf}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
