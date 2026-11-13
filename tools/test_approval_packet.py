"""One approval packet: preview PDF, per-criterion summary and missing items (verify-concise-drafts T8, S2; #64)."""
from __future__ import annotations

from pathlib import Path

import approval_packet
import content_check
import pytest
from approval_marker import DRAFT_DIR_ENV, draft_preview_path, write_draft_record
from conftest import _cited_body, _report, _rubric, _sources_bib, _verification


@pytest.fixture(autouse=True)
def isolated_drafts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The preview lives in a temp dir (S4); keep each test's out of the real one."""
    monkeypatch.setenv(DRAFT_DIR_ENV, str(tmp_path / "system-tmp"))


def _folder(tmp_path: Path) -> Path:
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    _cited_body(folder)
    return folder


def _verify(folder: Path, requirements: list[dict] | None = None, **extra: object) -> int:
    path = _verification(folder, requirements=requirements, **extra)
    return content_check.main([str(folder), "--verification", str(path)])


def _fresh_preview(folder: Path) -> Path:
    pdf = draft_preview_path(folder)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-draft")
    write_draft_record(pdf, folder / "body.md")
    return pdf


def test_packet_links_the_fresh_preview_and_the_body(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    pdf = _fresh_preview(folder)
    _verify(folder)
    text = approval_packet.render(folder)
    assert f"- Draft PDF: [{pdf.name}]({pdf.resolve().as_uri()})" in text
    assert f"- body.md: [body.md]({(folder / 'body.md').resolve().as_uri()})" in text
    assert "STALE" not in text


def test_packet_flags_a_preview_older_than_the_body(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    _fresh_preview(folder)
    _cited_body(folder, "# Informe\n\nOtro cuerpo [@key1], [@key2], [@key3], [@key4] y [@key5].\n")
    text = approval_packet.render(folder)
    assert "STALE: rebuild the draft with draft_pdf.py" in text


def test_packet_without_a_preview_says_so(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    assert "- Draft PDF: missing: build the draft with draft_pdf.py" in (
        approval_packet.render(folder))


def test_packet_summarizes_per_criterion_and_lists_missing_items(tmp_path: Path, capsys) -> None:
    """#64: the human gets one row per criterion, never the per-requirement evidence matrix."""
    folder = _folder(tmp_path)
    _fresh_preview(folder)
    capsys.readouterr()
    assert _verify(folder, requirements=[
        {"criterion": "objetivo", "requirement": "A goal | measurable", "status": "found",
         "location": "## Informe", "evidence": "Cuerpo con fuentes"},
        {"criterion": "metodologia", "requirement": "One Wokwi link per part", "status": "missing",
         "location": "", "evidence": ""},
        {"criterion": "metodologia", "requirement": "A results table", "status": "found",
         "location": "## Informe", "evidence": "Cuerpo con fuentes"},
    ], unmapped_paragraphs=["Como es sabido"], findings=["WARNING: repeats the intro"]) == 0
    # warn-only-gates S2: the fail verdict is recorded and warned, exit 0.
    assert capsys.readouterr().err == (
        "warning: content_check_failed: content-check.yml recorded result: fail\n")
    text = approval_packet.render(folder)
    assert "## Verify: fail (2/3 requirements found)" in text
    assert "| Criterion | Status | Found |\n|---|---|---|\n| objetivo | cumple | 1/1 |\n| metodologia | falta | 1/2 |" in text
    assert "Cuerpo con fuentes" not in text and "| Evidence |" not in text
    matrix = (folder / content_check.CONTENT_CHECK_NAME).resolve().as_uri()
    assert f"Full requirement matrix (for agents): [content-check.yml]({matrix})" in text
    assert "### Missing (1)\n- metodologia: One Wokwi link per part" in text
    assert "### Deletion candidates (1)\n- Como es sabido" in text
    assert "- WARNING: repeats the intro" in text


def test_passing_verify_has_no_missing_items(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    _fresh_preview(folder)
    assert _verify(folder) == 0
    text = approval_packet.render(folder)
    assert "## Verify: pass (2/2 requirements found)" in text
    assert "### Missing (0)\n- none" in text


def test_stale_verify_shows_no_old_matrix(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    _verify(folder)
    _cited_body(folder, "# Informe\n\nOtro cuerpo [@key1], [@key2], [@key3], [@key4] y [@key5].\n")
    text = approval_packet.render(folder)
    assert "## Verify: stale: re-run the verifier (content_check.py --verify-brief --since verification.yml)" in text
    assert "| Criterion |" not in text


def test_absent_verify_says_run_it(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    assert "## Verify: absent: run the verifier first (content_check.py --verify-brief)" in (
        approval_packet.render(folder))


def test_latest_docx_draft_is_linked(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    drafts = folder / "borrador"
    drafts.mkdir()
    (drafts / "x-borrador-v01.docx").write_bytes(b"a")
    latest = drafts / "x-borrador-v02.docx"
    latest.write_bytes(b"b")
    assert f"- DOCX draft: [{latest.name}]({latest.resolve().as_uri()})" in approval_packet.render(folder)


def test_cli_prints_the_packet_and_rejects_a_missing_folder(tmp_path: Path, capsys) -> None:
    folder = _folder(tmp_path)
    assert approval_packet.main([str(folder)]) == 0
    assert "# Approval packet" in capsys.readouterr().out
    assert approval_packet.main([str(tmp_path / "nope")]) == 2
    assert "approval packet input error: report folder not found" in capsys.readouterr().err


def test_the_temporary_draft_is_the_preview(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    assert approval_packet.preview_pdf(folder) == draft_preview_path(folder)


def test_open_flag_opens_a_fresh_preview(tmp_path: Path, capsys, monkeypatch) -> None:
    folder = _folder(tmp_path)
    pdf = _fresh_preview(folder)
    opened: list[Path] = []
    monkeypatch.setattr(approval_packet.pdf_viewer, "open_pdf", lambda path: opened.append(path))
    assert approval_packet.main([str(folder), "--open"]) == 0
    out = capsys.readouterr()
    assert "# Approval packet" in out.out
    assert opened == [pdf]
    assert f"opened {pdf.resolve()}" in out.err


def test_open_flag_never_opens_a_stale_or_missing_preview(tmp_path: Path, capsys, monkeypatch) -> None:
    folder = _folder(tmp_path)
    opened: list[Path] = []
    monkeypatch.setattr(approval_packet.pdf_viewer, "open_pdf", lambda path: opened.append(path))
    assert approval_packet.main([str(folder), "--open"]) == 0
    assert "preview not opened: rebuild the preview first" in capsys.readouterr().err
    _fresh_preview(folder)
    _cited_body(folder, "# Informe\n\nOtro cuerpo [@key1], [@key2], [@key3], [@key4] y [@key5].\n")
    assert approval_packet.main([str(folder), "--open"]) == 0
    assert "preview not opened: rebuild the preview first" in capsys.readouterr().err
    assert opened == []


def test_open_flag_reports_a_viewer_failure(tmp_path: Path, capsys, monkeypatch) -> None:
    folder = _folder(tmp_path)
    _fresh_preview(folder)
    monkeypatch.setattr(approval_packet.pdf_viewer, "open_pdf", lambda path: "no PDF viewer found")
    assert approval_packet.main([str(folder), "--open"]) == 0
    assert "preview not opened: no PDF viewer found" in capsys.readouterr().err


def test_without_open_flag_nothing_is_opened(tmp_path: Path, capsys, monkeypatch) -> None:
    folder = _folder(tmp_path)
    _fresh_preview(folder)
    opened: list[Path] = []
    monkeypatch.setattr(approval_packet.pdf_viewer, "open_pdf", lambda path: opened.append(path))
    assert approval_packet.main([str(folder)]) == 0
    assert opened == [] and capsys.readouterr().err == ""
