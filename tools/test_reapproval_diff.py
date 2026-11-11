"""Re-approval rounds show only the changes, never the whole draft again.

The plain draft PDF is built once, for the first approval prompt. Once the
reviewer has been shown a body (``approval_packet.py --open`` records it in
``presented-body.md``) or has approved one (``approved-body.md``), later rounds
need no draft rebuild: the packet shows the diff since that body.
"""
from __future__ import annotations

from pathlib import Path

import approval_packet
import doc_status
import pytest
from approval_marker import DRAFT_DIR_ENV, PRESENTED_NAME, draft_preview_path, record_approval, write_draft_record
from conftest import _cited_body, _report, _rubric, _sources_bib

FIRST = "# Informe\n\nPrimer parrafo intacto [@key1], [@key2], [@key3], [@key4] y [@key5].\n\nSegundo parrafo original.\n"
EDITED = "# Informe\n\nPrimer parrafo intacto [@key1], [@key2], [@key3], [@key4] y [@key5].\n\nSegundo parrafo corregido por el usuario.\n"


@pytest.fixture(autouse=True)
def isolated_drafts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DRAFT_DIR_ENV, str(tmp_path / "system-tmp"))


def _folder(tmp_path: Path) -> Path:
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    _cited_body(folder, FIRST)
    return folder


def _fresh_preview(folder: Path) -> Path:
    pdf = draft_preview_path(folder)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-draft")
    write_draft_record(pdf, folder / "body.md")
    return pdf


def _present(folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approval_packet.pdf_viewer, "open_pdf", lambda _pdf: None)
    assert approval_packet.main([str(folder), "--open"]) == 0


def test_open_records_the_presented_body(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _folder(tmp_path)
    _fresh_preview(folder)
    _present(folder, monkeypatch)
    assert (folder / PRESENTED_NAME).read_text(encoding="utf-8") == FIRST


def test_open_without_a_fresh_first_draft_records_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _folder(tmp_path)
    _present(folder, monkeypatch)
    assert not (folder / PRESENTED_NAME).exists()


def test_first_round_still_demands_the_draft_pdf(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    guidance = doc_status._guidance("approval", folder)
    assert "rebuild the draft PDF" in guidance
    assert "ask_user_choice" not in guidance


def test_later_round_needs_no_draft_rebuild(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _folder(tmp_path)
    _fresh_preview(folder)
    _present(folder, monkeypatch)
    _cited_body(folder, EDITED)

    guidance = doc_status._guidance("approval", folder)

    assert "rebuild the draft PDF" not in guidance
    assert "only the changes" in guidance
    assert "ask_user_choice" in guidance


def test_later_round_packet_shows_only_the_diff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _folder(tmp_path)
    _fresh_preview(folder)
    _present(folder, monkeypatch)
    _cited_body(folder, EDITED)

    text = approval_packet.render(folder)

    assert "## Changes since your last review (5 words)" in text
    assert "-Segundo parrafo original." in text
    assert "+Segundo parrafo corregido por el usuario." in text
    assert "Primer parrafo intacto" not in text
    assert "Draft PDF" not in text
    assert "STALE" not in text


def test_later_round_open_advances_the_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _folder(tmp_path)
    _fresh_preview(folder)
    _present(folder, monkeypatch)
    _cited_body(folder, EDITED)
    _present(folder, monkeypatch)

    assert (folder / PRESENTED_NAME).read_text(encoding="utf-8") == EDITED
    assert "## Changes since your last review: none" in approval_packet.render(folder)


def test_approved_snapshot_is_the_base_without_a_presented_body(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    record_approval(folder, "Alejandro")
    _cited_body(folder, EDITED)

    text = approval_packet.render(folder)

    assert "+Segundo parrafo corregido por el usuario." in text
    assert "rebuild the draft PDF" not in doc_status._guidance("approval", folder)


def test_later_round_verify_guidance_never_asks_for_the_draft(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _folder(tmp_path)
    assert "draft_pdf.py" not in doc_status._guidance("verify", folder)
    _fresh_preview(folder)
    _present(folder, monkeypatch)
    _cited_body(folder, EDITED)

    for reason in ("", "content_check_failed"):
        guidance = doc_status._guidance("verify", folder, blocked_reason=reason)
        assert "draft_pdf.py" not in guidance and "rebuild the preview" not in guidance
