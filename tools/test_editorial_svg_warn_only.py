"""warn-only-gates S2: undersized print text warns; the check exits 0 and the SVG stays.

Unreadable or invalid input keeps exiting 2.
"""
from __future__ import annotations

from pathlib import Path

import yaml

import editorial_svg
from test_editorial_svg import CONCEPT_SPEC


def _rendered(tmp_path: Path) -> Path:
    spec = tmp_path / "map.yml"
    spec.write_text(yaml.safe_dump(CONCEPT_SPEC, allow_unicode=True), encoding="utf-8")
    out = tmp_path / "map.svg"
    assert editorial_svg.main(["render", str(spec), "--out", str(out)]) == 0
    return out


def test_print_size_fail_warns_and_exits_0(tmp_path: Path, capsys) -> None:
    out = _rendered(tmp_path)
    before = out.read_bytes()
    capsys.readouterr()
    assert editorial_svg.main(["check", str(out), "--min-pt", "40"]) == 0
    captured = capsys.readouterr()
    assert "pt < 40.0 pt" in captured.out
    assert captured.err.splitlines() == [
        "warning: print size check: FAIL (13.5 cm wide, minimum 40.0 pt); enlarge the listed text. "
        "The flow continues."
    ]
    assert out.read_bytes() == before


def test_print_size_pass_prints_no_warning(tmp_path: Path, capsys) -> None:
    out = _rendered(tmp_path)
    capsys.readouterr()
    assert editorial_svg.main(["check", str(out)]) == 0
    captured = capsys.readouterr()
    assert "print size check: PASS" in captured.out and captured.err == ""


def test_unreadable_svg_still_exits_2(tmp_path: Path, capsys) -> None:
    assert editorial_svg.main(["check", str(tmp_path / "missing.svg")]) == 2
    assert capsys.readouterr().err.startswith("editorial_svg: ")
