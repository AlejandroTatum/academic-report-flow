"""Plain-text draft rules (issue #96, odd/tasks/plain-text-draft.md S2-S3).

The draft body.md the user reviews and approves is plain text: only ``#``
headings and ``[@key]`` citations survive as markers. Backend formatting is
applied after approval in ``body.typeset.md``, so the draft body check rejects
it and the format's fixed headings are no longer checked at draft time.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import content_check
import doc_status
import link_check
from conftest import _cited_body, _report, _rubric, _sources_bib
from rubric_checks import run_checks

CITES = "[@key1] [@key2] [@key3] [@key4] [@key5]"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(url: str, method: str) -> int:
        raise AssertionError(f"network access attempted: {method} {url}")

    monkeypatch.setattr(link_check, "default_fetcher", refuse)


def _folder(tmp_path: Path, body: str, extra_report: str = "") -> Path:
    folder = tmp_path / "wf"
    _report(folder)
    if extra_report:
        report = folder / "report.yml"
        report.write_text(report.read_text(encoding="utf-8") + extra_report, encoding="utf-8")
    _sources_bib(folder)
    _rubric(folder)
    _cited_body(folder, body)
    return folder


def _checks(folder: Path) -> dict[str, dict]:
    return {item["check"]: item for item in content_check.body_check_results(folder)}


@pytest.mark.parametrize(
    "line,label",
    [
        ("El error es $e = 0.5$ en total.", "math"),
        ("$$x^2 + 1$$", "math"),
        ("Usa \\varepsilon como tolerancia.", "LaTeX command"),
        ("| a | b |", "table"),
        ("![Grafica](graficas/f.png)", "image"),
        ("Un **dato** importante.", "bold"),
        ("<!-- table-style: datos purpose=x -->", "HTML comment"),
    ],
)
def test_draft_body_check_rejects_backend_formatting_with_its_line(
    tmp_path: Path, line: str, label: str
) -> None:
    folder = _folder(tmp_path, f"# Informe\n\nTexto con {CITES}.\n\n{line}\n")

    check = _checks(folder)["plain_text"]

    assert check["ok"] is False
    assert f"line 5 ({label})" in check["detail"]
    assert "plain text" in check["detail"] and "typeset" in check["detail"]


def test_draft_body_check_cli_exits_1_and_writes_nothing_on_formatting(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path, f"# Informe\n\nEl error es $e$ con {CITES}.\n")
    before = sorted(p.name for p in folder.iterdir())

    assert content_check.main([str(folder), "--body-check"]) == 1

    out = capsys.readouterr().out
    assert "[FAIL] plain_text: backend formatting in the plain-text draft at line 3 (math)" in out
    assert sorted(p.name for p in folder.iterdir()) == before


def test_plain_draft_passes_with_headings_citations_unicode_figure_line_and_url(tmp_path: Path) -> None:
    body = (
        "# Informe\n\n"
        f"El error relativo es e = |x1 − x0| / |x1| · 100 % y la velocidad 3 m/s² {CITES}.\n\n"
        "Figura: Convergencia del método (graficas/conv.png)\n\n"
        "Repositorio: https://example.org/repo\n"
    )
    folder = _folder(tmp_path, body)

    checks = _checks(folder)

    assert checks["plain_text"]["ok"] is True, checks["plain_text"]["detail"]
    assert checks["body_format"]["ok"] is True, checks["body_format"]["detail"]


def test_code_is_content_not_formatting(tmp_path: Path) -> None:
    body = (
        f"# Informe\n\nTexto {CITES} y `a | b` en linea.\n\n"
        "```matlab\nx = $a; % \\alpha\n| t |\n```\n"
    )
    folder = _folder(tmp_path, body)

    assert _checks(folder)["plain_text"]["ok"] is True


def test_draft_still_needs_a_level_one_heading(tmp_path: Path) -> None:
    folder = _folder(tmp_path, f"## Informe\n\nTexto {CITES}.\n")

    check = _checks(folder)["body_format"]

    assert check["ok"] is False and "level-1" in check["detail"]


def test_draft_no_longer_checks_fixed_format_headings(tmp_path: Path) -> None:
    folder = _folder(tmp_path, f"# Cualquier titulo\n\nTexto {CITES}.\n", extra_report="format: ape\n")

    checks = _checks(folder)

    assert "ape_structure" not in checks
    assert "aa_structure" not in checks


def test_doc_status_keeps_draft_pending_on_formatting(tmp_path: Path) -> None:
    folder = _folder(tmp_path, f"# Informe\n\nEl error es $e$ con {CITES}.\n")

    phase = doc_status._phase_draft(folder, None, None)

    assert phase.state == doc_status.PENDING
    assert phase.blocked_reason == "body_check_failed"
    assert "plain_text: backend formatting in the plain-text draft at line 3 (math)" in phase.detail


@pytest.mark.parametrize(
    "check,expected",
    [
        ({"type": "figure_referenced"}, True),
        ({"type": "figure_referenced", "count": 2}, False),
        ({"type": "link_present", "pattern": "example.org/repo"}, True),
        ({"type": "link_present", "pattern": "other"}, False),
    ],
)
def test_rubric_checks_accept_plain_figure_lines_and_bare_urls(
    tmp_path: Path, check: dict, expected: bool
) -> None:
    body = "# Informe\n\nFigura: Convergencia (graficas/conv.png)\n\nVer https://example.org/repo\n"

    result, = run_checks(tmp_path, [{"id": "x", "checks": [check]}], body)

    assert result.ok is expected, result.detail
