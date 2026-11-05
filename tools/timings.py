#!/usr/bin/env python3
"""Per-phase timings of the academic-report-flow, recorded by the tools that run the phases.

Each instrumented tool wraps its work in ``timed(folder, phase, tool)``, which appends
one entry (phase, tool, start, end, duration seconds, outcome) to ``timings.yml`` in
the report *work* folder -- never the delivery folder. The file is an append-only YAML
list, one entry per run, so overlapping runs (the verification and the draft preview
build run in parallel) each keep their own start and end.

Timings are informational. Recording never raises, never creates the work folder, and
never rewrites a file it cannot parse: a malformed or unwritable ``timings.yml`` is
ignored with a warning on stderr, and the tool's exit code and stdout stay unchanged.

``python tools/timings.py <work-folder>`` prints the per-phase totals, slowest first.
"""
from __future__ import annotations

import argparse
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import yaml

TIMINGS_NAME = "timings.yml"


def _warn(message: str) -> None:
    print(f"timings: {message}", file=sys.stderr)


def _load(path: Path) -> list[Any] | None:
    """The entries of ``path``; ``[]`` when absent or empty, ``None`` (after a warning) when unusable."""
    if not path.is_file():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        _warn(f"ignoring unreadable {path.name} ({type(exc).__name__})")
        return None
    if data is None:
        return []
    if not isinstance(data, list):
        _warn(f"ignoring {path.name}: expected a list of entries")
        return None
    return data


def record(folder: Path, phase: str, tool: str, started: datetime, ended: datetime, duration: float, outcome: str) -> None:
    """Append one entry to ``<folder>/timings.yml``; any failure only warns."""
    try:
        folder = Path(folder)
        if not folder.is_dir():
            return
        path = folder / TIMINGS_NAME
        if _load(path) is None:
            return
        entry = {
            "phase": phase,
            "tool": tool,
            "start": started.isoformat(timespec="seconds"),
            "end": ended.isoformat(timespec="seconds"),
            "duration_seconds": round(duration, 3),
            "outcome": outcome,
        }
        text = yaml.safe_dump([entry], sort_keys=False)
        if path.is_file() and path.stat().st_size and not _ends_with_newline(path):
            text = "\n" + text
        with path.open("a", encoding="utf-8") as stream:
            stream.write(text)
    except Exception as exc:  # informational: nothing here may break a phase tool
        _warn(f"not recorded ({type(exc).__name__}: {exc})")


def _ends_with_newline(path: Path) -> bool:
    with path.open("rb") as stream:
        stream.seek(-1, 2)
        return stream.read(1) == b"\n"


@contextmanager
def timed(folder: Path, phase: str, tool: str) -> Iterator[None]:
    """Measure the wrapped block and append it to the work folder's ``timings.yml``."""
    started = datetime.now(timezone.utc)
    clock = time.perf_counter()
    outcome = "ok"
    try:
        yield
    except BaseException:
        outcome = "error"
        raise
    finally:
        record(folder, phase, tool, started, datetime.now(timezone.utc), time.perf_counter() - clock, outcome)


def summarize(entries: list[Any]) -> list[tuple[str, int, float, float]]:
    """``(phase, runs, total seconds, longest run)`` per phase, slowest total first."""
    totals: dict[str, list[float]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        phase, seconds = entry.get("phase"), entry.get("duration_seconds")
        if isinstance(phase, str) and isinstance(seconds, (int, float)) and not isinstance(seconds, bool):
            totals.setdefault(phase, []).append(float(seconds))
    rows = [(phase, len(runs), sum(runs), max(runs)) for phase, runs in totals.items()]
    return sorted(rows, key=lambda row: (-row[2], row[0]))


def render_summary(rows: list[tuple[str, int, float, float]]) -> str:
    if not rows:
        return "no timings recorded\n"
    width = max(len("phase"), *(len(row[0]) for row in rows))
    lines = [f"{'phase':<{width}}  runs  total_s  longest_s"]
    lines += [f"{phase:<{width}}  {runs:>4}  {total:>7.1f}  {longest:>9.1f}" for phase, runs, total, longest in rows]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="timings.py",
        description="Print the per-phase totals recorded in timings.yml of a report work folder, slowest first.",
    )
    parser.add_argument("folder", metavar="work-folder", help="report work folder holding timings.yml")
    args = parser.parse_args(argv)
    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"work folder missing or not a directory: {folder}", file=sys.stderr)
        return 2
    entries = _load(folder / TIMINGS_NAME) or []
    sys.stdout.write(render_summary(summarize(entries)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
