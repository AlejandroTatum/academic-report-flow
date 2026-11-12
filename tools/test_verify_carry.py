"""A bounded edit after the check keeps the verification (no new verifier round).

``content_check`` snapshots the body it checked in ``checked-body.md``. When
``body.md`` later differs from ``body_sha256`` the marker still holds only if
that snapshot hashes to ``body_sha256``, the diff is bounded (the same
predicate as the approval gate), every ``found`` quote is still in the body and
the draft's mechanical checks still pass on the new bytes. A heading rename
carries too when the outline keeps its shape, every criterion section still
resolves and the rubric checks still pass (faster-verify-loop S2). Anything
else is ``stale``, as before.
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


# S2 (faster-verify-loop): a heading rename keeps the verification when the
# outline keeps its shape, the edit stays bounded and every criterion's
# section still resolves. The AA3 run renamed `### Referencias`.
RENAME_BODY = (
    "# Informe\n\nCuerpo con fuentes [@key1] y [@key2], mas [@key3], [@key4] y [@key5].\n\n"
    "## Objetivos\n\nMedir la deriva.\n\n## Metodologia\n\nSe midio dos veces.\n\n"
    "### Referencias\n\nLista de fuentes.\n"
)


def _renamed(folder: Path, criteria: tuple[dict, ...] | None = None) -> tuple[Path, bytes, bytes]:
    _report(folder)
    _sources_bib(folder)
    _rubric(folder, criteria=criteria)
    _cited_body(folder, RENAME_BODY)
    assert content_check.main([str(folder), "--verification", str(_verification(folder))]) == 0
    assert content_check.content_check_state(folder) == "pass"
    return (folder, (folder / content_check.CONTENT_CHECK_NAME).read_bytes(),
            (folder / content_check.CHECKED_SNAPSHOT_NAME).read_bytes())


def _unchanged(folder: Path, marker: bytes, snapshot: bytes) -> None:
    assert (folder / content_check.CONTENT_CHECK_NAME).read_bytes() == marker
    assert (folder / content_check.CHECKED_SNAPSHOT_NAME).read_bytes() == snapshot


def test_heading_rename_keeps_a_pass(tmp_path: Path) -> None:
    folder, marker, snapshot = _renamed(tmp_path / "wf")

    _edit(folder, "### Referencias", "### Fuentes de la decision")

    assert content_check.content_check_state(folder) == "pass"
    _unchanged(folder, marker, snapshot)


def test_heading_rename_with_a_level_change_is_stale(tmp_path: Path) -> None:
    folder, marker, snapshot = _renamed(tmp_path / "wf")

    _edit(folder, "### Referencias", "## Fuentes de la decision")

    assert content_check.content_check_state(folder) == "stale"
    _unchanged(folder, marker, snapshot)


def test_heading_swap_is_stale(tmp_path: Path) -> None:
    folder, marker, snapshot = _renamed(tmp_path / "wf")
    text = RENAME_BODY.replace("## Objetivos", "## TMP").replace("## Metodologia", "## Objetivos")
    _body(folder, text.replace("## TMP", "## Metodologia"))

    assert content_check.content_check_state(folder) == "stale"
    _unchanged(folder, marker, snapshot)


def test_added_heading_is_stale(tmp_path: Path) -> None:
    folder, marker, snapshot = _renamed(tmp_path / "wf")

    _edit(folder, "Lista de fuentes.\n", "Lista de fuentes.\n\n### Anexos\n")

    assert content_check.content_check_state(folder) == "stale"
    _unchanged(folder, marker, snapshot)


def test_removed_heading_is_stale(tmp_path: Path) -> None:
    folder, marker, snapshot = _renamed(tmp_path / "wf")

    _edit(folder, "### Referencias\n\n", "")

    assert content_check.content_check_state(folder) == "stale"
    _unchanged(folder, marker, snapshot)


@pytest.mark.parametrize(("extra", "state"), [(35, "pass"), (36, "stale")])
def test_heading_rename_counts_heading_words_in_the_limit(tmp_path: Path, extra: int, state: str) -> None:
    folder, marker, snapshot = _renamed(tmp_path / "wf")
    # The rename alone changes 5 words: 1 deleted, 4 inserted.
    _edit(folder, "### Referencias\n\nLista de fuentes.",
          "### Fuentes de la decision\n\nLista de fuentes. " + "palabra " * extra)

    assert content_check.content_check_state(folder) == state
    _unchanged(folder, marker, snapshot)


def test_heading_rename_hiding_a_criterion_section_is_stale(tmp_path: Path) -> None:
    folder, marker, snapshot = _renamed(tmp_path / "wf")

    _edit(folder, "## Objetivos", "## Metas")

    assert content_check.content_check_state(folder) == "stale"
    _unchanged(folder, marker, snapshot)


def test_heading_rename_failing_a_rubric_check_is_stale(tmp_path: Path) -> None:
    criteria = (
        {"id": "objetivo", "title": "Objetivo claro", "section": "Objetivos",
         "checks": [{"type": "heading_present", "section": "Referencias"}]},
        {"id": "metodologia", "title": "Metodologia descrita", "section": "Metodologia"},
    )
    folder, marker, snapshot = _renamed(tmp_path / "wf", criteria)

    _edit(folder, "### Referencias", "### Fuentes de la decision")

    assert content_check.content_check_state(folder) == "stale"
    _unchanged(folder, marker, snapshot)


@pytest.mark.parametrize("breakage", ["accepted_gaps", "quote", "citation"])
def test_heading_rename_keeps_the_bounded_conditions(tmp_path: Path, breakage: str) -> None:
    folder, marker, snapshot = _renamed(tmp_path / "wf")
    text = RENAME_BODY.replace("### Referencias", "### Fuentes de la decision")
    if breakage == "accepted_gaps":
        (folder / "accepted-gaps.yml").write_text("gaps: []\n", encoding="utf-8")
    elif breakage == "quote":
        text = text.replace("Cuerpo con fuentes", "Texto con fuentes")
    else:
        text = text.replace("[@key5]", "[@nokey]")
    _body(folder, text)

    assert content_check.content_check_state(folder) == "stale"
    _unchanged(folder, marker, snapshot)


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


def test_bounded_edit_carries_a_crlf_body(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    (folder / "body.md").write_bytes(DEFAULT_CITED_BODY.replace("\n", "\r\n").encode("utf-8"))
    assert content_check.main([str(folder), "--verification", str(_verification(folder))]) == 0
    assert (folder / content_check.CHECKED_SNAPSHOT_NAME).read_bytes() == (folder / "body.md").read_bytes()

    text = (folder / "body.md").read_bytes().replace(b"mas [@key3]", b"ademas de [@key3]")
    (folder / "body.md").write_bytes(text)

    assert content_check.content_check_state(folder) == "pass"


def test_bounded_edit_with_accepted_gaps_is_stale(tmp_path: Path) -> None:
    folder = _checked(tmp_path / "wf")
    (folder / "accepted-gaps.yml").write_text("gaps: []\n", encoding="utf-8")

    _edit(folder, "mas [@key3]", "ademas de [@key3]")

    assert content_check.content_check_state(folder) == "stale"
