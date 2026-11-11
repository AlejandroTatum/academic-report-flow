#!/usr/bin/env python3
"""Build phase: one command chains typeset, generate and validate.

``build.py <folder>`` runs, in order:

1. typeset: the same code as ``typeset.py auto <folder>`` (same messages,
   ``left for you:`` lines and check lines; it records the ``typeset`` timing).
   When the bind is refused or a typeset check fails nothing is built: finish
   ``body.typeset.md`` by hand and run the same command again. A report that
   does not use typeset (an ``approval.yml`` that predates it) skips the step.
2. generate and validate: the same code as ``build_report_auto.py <folder>``
   (same messages, refusals and exit status; it records the ``generate``
   timing). No option skips a gate.

After a successful build it prints what the validate phase still needs: an
inspection of every page of the final document, recorded in
``validation.yml``. It never writes ``validation.yml``, ``approval.yml``,
``final-review.yml`` or ``body.md``, and it grants no gate.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import build_report_auto
import typeset
from approval_marker import BODY_NAME
from report_config import TYPESET_BODY_NAME, load_report_config


def _typeset(folder: Path) -> bool:
    """Step 1; True when the build may go on."""
    if not typeset.typeset_in_use(folder):
        print(f"step 1/2: typeset skipped: this report renders {BODY_NAME} (approval.yml predates typeset)")
        return True
    print("step 1/2: typeset")
    status, results = typeset.run("auto", folder)
    if status == 0 and results is not None and all(item["ok"] for item in results):
        return True
    print(
        f"build stopped: typeset is not finished. Finish {folder / TYPESET_BODY_NAME} "
        f"(never {BODY_NAME}), then run build.py {folder} again; nothing was built.",
        file=sys.stderr,
    )
    return False


def _generate(folder: Path) -> int:
    """Step 2 through ``build_report_auto.main``; its exit status, as the CLI would give it."""
    saved = sys.argv
    sys.argv = ["build_report_auto.py", str(folder)]
    try:
        build_report_auto.main()
    except SystemExit as exc:
        if exc.code is None or isinstance(exc.code, int):
            return exc.code or 0
        print(exc.code, file=sys.stderr)
        return 1
    finally:
        sys.argv = saved
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build phase in one command: typeset (typeset.py auto), then generate and validate "
            "(build_report_auto.py). Stops before building while the typeset checks fail; never "
            "writes validation.yml, approval.yml, final-review.yml or body.md."
        )
    )
    parser.add_argument("folder", type=Path, help="report work folder with report.yml")
    args = parser.parse_args(argv)
    folder = args.folder
    if not _typeset(folder):
        return 1
    print("step 2/2: generate and validate")
    status = _generate(folder)
    if status != 0:
        return status
    config = load_report_config(folder)
    artifact = config.pdf_path if config.output_format == "pdf" else config.docx_path
    print(
        f"left for validate: inspect every page of {artifact} and record "
        f"{folder / 'validation.yml'}; build.py never writes it"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
