"""Body check in doc_status (task 9.2), using the very same function as
``content_check --body-check``; a FAIL is a warning (warn-only-gates S2)."""
from __future__ import annotations

from pathlib import Path

import pytest

import content_check
import doc_status
from conftest import _approval, _body, _cited_body, _report, _rubric, _sources_bib


def _ready(folder: Path, body: str | None = None) -> Path:
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    if body is None:
        _cited_body(folder)
    else:
        _body(folder, body)
    return folder


def test_clean_draft_reaches_the_verify_gate(tmp_path: Path) -> None:
    # verify-concise-drafts T8: verify precedes approval.
    status = doc_status.derive(_ready(tmp_path / "wf"))

    assert status.next_token == "verify"


def test_body_format_defect_is_a_warning_that_names_the_check_and_advances(tmp_path: Path) -> None:
    folder = _ready(tmp_path / "wf", "## Informe\n\nTexto con [@key1], [@key2], [@key3], [@key4], [@key5].\n")

    status = doc_status.derive(folder)

    # warn-only-gates S2: the body-check FAIL is a warning; the route advances to verify.
    draft = next(p for p in status.phases if p.name == "draft")
    assert status.next_token == "verify"
    assert draft.state == doc_status.DONE and draft.blocked_reason == ""
    assert draft.detail.startswith("warning: body_check_failed: body check fails: ")
    assert "body_format" in draft.detail and "level-1" in draft.detail


def test_uncited_sources_block_approval_and_name_the_failing_check(tmp_path: Path) -> None:
    """S1 (v1): uncited sources are a named finding, not a generation block."""
    status = doc_status.derive(_ready(tmp_path / "wf", "# Informe\n\nCuerpo sin citas.\n"))

    draft = next(p for p in status.phases if p.name == "draft")
    assert draft.state == doc_status.DONE
    assert status.next_token == "verify"
    assert "not a compliance pass" in draft.detail and "eligible_sources_cited" in draft.detail


def test_doc_status_uses_the_shared_body_check_function(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _ready(tmp_path / "wf")
    monkeypatch.setattr(
        content_check,
        "body_check_results",
        lambda _folder: [{"check": "citations_resolve", "ok": False, "detail": "forced failure"},
                         {"check": "rubric_checks", "ok": False, "detail": "forced finding"}],
    )

    status = doc_status.derive(folder)

    assert status.next_token == "verify"
    detail = next(p for p in status.phases if p.name == "draft").detail
    assert detail == "warning: body_check_failed: body check fails: citations_resolve: forced failure"
    assert "rubric_checks" not in detail


def test_current_approval_is_not_regated_by_the_body_check(tmp_path: Path) -> None:
    folder = _ready(tmp_path / "wf", "## Informe\n\nsin h1.\n")
    _approval(folder)

    draft = next(p for p in doc_status.derive(folder).phases if p.name == "draft")

    assert draft.state == doc_status.DONE
