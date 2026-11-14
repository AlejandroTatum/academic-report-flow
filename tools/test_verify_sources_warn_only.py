"""warn-only-gates S2: failed sources warn; the record is written and verify_sources exits 0.

A missing or unreadable bibliography keeps exiting 2.
"""
from __future__ import annotations

from verify_sources import main, verify_sources
from test_verify_sources import doi_response, report, result_rows


def test_failed_sources_warn_write_the_record_and_exit_0(tmp_path, capsys) -> None:
    folder = report(tmp_path, "@article{a, title={A Study of Trees}, year={2020}, doi={10.1/a}}")
    assert main([str(folder)], fetch=lambda *_: doi_response(title="Other Topic Entirely")) == 0
    captured = capsys.readouterr()
    assert "a: MISMATCH" in captured.out
    destination = folder / "research" / "sources-verification.yml"
    assert captured.err.splitlines() == [
        f"warning: verify_sources: 1 of 1 entries failed; details in {destination}. The flow continues."
    ]
    assert result_rows(folder)[0]["status"] == "MISMATCH"


def test_verified_sources_print_no_warning(tmp_path, capsys) -> None:
    folder = report(tmp_path, "@article{a, title={A Study of Trees}, year={2020}, doi={10.1/a}}")
    assert verify_sources(folder, fetch=lambda *_: doi_response()) == 0
    assert capsys.readouterr().err == ""


def test_missing_bibliography_still_exits_2(tmp_path, capsys) -> None:
    folder = tmp_path / "report"
    folder.mkdir()
    (folder / "report.yml").write_text("title: Test report\n", encoding="utf-8")
    assert main([str(folder)]) == 2
    assert not (folder / "research" / "sources-verification.yml").exists()
