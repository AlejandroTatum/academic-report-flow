"""A bounded edit after the check keeps the verification (no new verifier round).

``content_check`` snapshots the body it checked in ``checked-body.md``. When
``body.md`` later differs from ``body_sha256`` the marker still holds only if
that snapshot hashes to ``body_sha256``, the diff is bounded (the same
predicate as the approval gate), every ``found`` quote is still in the body and
the draft's mechanical checks still pass on the new bytes. Anything else is
``stale``, as before.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import content_check
import link_check
from conftest import DEFAULT_CITED_BODY, _body, _cited_body, _report, _rubric, _sources_bib, _verification


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(url: str, method: str) -> int:
        raise AssertionError(f"network access attempted: {method} {url}")

    monkeypatch.setattr(link_check, "default_fetcher", refuse)


def _checked(folder: Path, verification: Path | None = None) -> Path:
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    _cited_body(folder)
    path = verification if verification is not None else _verification(folder)
    assert content_check.main([str(folder), "--verification", str(path)]) in (0, 1)
    return folder


def _edit(folder: Path, old: str, new: str) -> None:
    body = folder / "body.md"
    text = body.read_text(encoding="utf-8")
    assert old in text
    _body(folder, text.replace(old, new))


def test_check_writes_the_body_snapshot(tmp_path: Path) -> None:
    folder = _checked(tmp_path / "wf")

    assert (folder / content_check.CHECKED_SNAPSHOT_NAME).read_text(encoding="utf-8") == DEFAULT_CITED_BODY


def test_bounded_edit_keeps_a_pass(tmp_path: Path) -> None:
    folder = _checked(tmp_path / "wf")
    marker = (folder / content_check.CONTENT_CHECK_NAME).read_bytes()

    _edit(folder, "mas [@key3]", "ademas de [@key3]")

    assert content_check.content_check_state(folder) == "pass"
    assert (folder / content_check.CONTENT_CHECK_NAME).read_bytes() == marker


def test_large_edit_is_stale(tmp_path: Path) -> None:
    folder = _checked(tmp_path / "wf")

    _edit(folder, "[@key5].\n", "[@key5].\n\n" + "palabra " * 41 + "\n")

    assert content_check.content_check_state(folder) == "stale"


def test_heading_edit_is_stale(tmp_path: Path) -> None:
    folder = _checked(tmp_path / "wf")

    _edit(folder, "# Informe", "# Reporte")

    assert content_check.content_check_state(folder) == "stale"


def test_untrusted_snapshot_is_stale(tmp_path: Path) -> None:
    folder = _checked(tmp_path / "wf")
    (folder / content_check.CHECKED_SNAPSHOT_NAME).write_text("# Otro\n", encoding="utf-8")

    _edit(folder, "mas [@key3]", "ademas de [@key3]")

    assert content_check.content_check_state(folder) == "stale"


def test_missing_snapshot_is_stale(tmp_path: Path) -> None:
    folder = _checked(tmp_path / "wf")
    (folder / content_check.CHECKED_SNAPSHOT_NAME).unlink()

    _edit(folder, "mas [@key3]", "ademas de [@key3]")

    assert content_check.content_check_state(folder) == "stale"


def test_bounded_edit_removing_a_found_quote_is_stale(tmp_path: Path) -> None:
    folder = _checked(tmp_path / "wf")

    _edit(folder, "Cuerpo con fuentes", "Texto con fuentes")

    assert content_check.content_check_state(folder) == "stale"


def test_bounded_edit_breaking_a_citation_is_stale(tmp_path: Path) -> None:
    folder = _checked(tmp_path / "wf")

    _edit(folder, "[@key5]", "[@nokey]")

    assert content_check.content_check_state(folder) == "stale"


def test_bounded_edit_keeps_a_fail(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    _cited_body(folder)
    failing = _verification(folder, requirements=[
        {"criterion": "objetivo", "requirement": "Demand", "status": "missing", "location": "", "evidence": ""},
        {"criterion": "metodologia", "requirement": "Demand", "status": "found", "location": "Cuerpo",
         "evidence": "Cuerpo con fuentes"},
    ])
    _checked(folder, failing)
    assert content_check.content_check_state(folder) == "fail"

    _edit(folder, "mas [@key3]", "ademas de [@key3]")

    assert content_check.content_check_state(folder) == "fail"
