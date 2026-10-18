"""Approval-phase tests for ``tools/doc_status.py`` (slice 2b-i).

Slice 2b-i ships the approval derivation. Like the 2a suite, these tests call the
handler directly and assert its raw ``done|pending|blocked`` token, detail and
blocked reason; ``derive``, the renderers and the CLI are slice 2c, and the
generate/validate/deliver derivations are slices 2b-ii/2b-iii. The approval handler
maps ``tools/approval_marker.py`` onto a phase state, so these tests drive that
predicate through its four disk shapes (absent, current, stale, malformed).
Artifact shapes come from ``tools/conftest.py``.
"""
from __future__ import annotations

from pathlib import Path


def test_legacy_verify_is_pending_and_requests_independent_verifier(tmp_path: Path) -> None:
    import yaml
    import doc_status
    from conftest import _report, _body, _sources_bib, _rubric, _approval, _content_check

    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    _body(folder)
    _approval(folder)
    _content_check(folder)
    marker_path = folder / "content-check.yml"
    marker = yaml.safe_load(marker_path.read_text())
    legacy = {key: marker[key] for key in (
        "schema", "body_sha256", "checked_at", "criteria", "findings", "mechanical", "result"
    )}
    legacy["mechanical"] = [entry for entry in marker["mechanical"] if entry["check"] != "rubric_checks"]
    marker_path.write_text(yaml.safe_dump(legacy))
    status = doc_status.derive(folder)
    verify = doc_status._phase_verify(folder, None, None)
    assert verify.state == doc_status.PENDING
    assert "independent verifier" in status.gate and "judge" not in status.gate
    assert "--verification verification.yml" in status.gate
    assert "malformed" not in status.gate


def test_malformed_verify_guidance_requests_verifier_and_content_check(tmp_path: Path) -> None:
    import doc_status
    from conftest import _report, _body, _sources_bib, _rubric, _approval, _content_check

    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    _body(folder)
    _approval(folder)
    _content_check(folder, mechanical=[])
    status = doc_status.derive(folder)
    assert "independent verifier" in status.gate and "judge" not in status.gate
    assert "--verification verification.yml" in status.gate
    assert "content_check.py" in status.gate


def test_failed_verify_guidance_requires_user_orders_and_reapproval(tmp_path: Path) -> None:
    import doc_status
    from conftest import _report, _body, _sources_bib, _rubric, _approval, _content_check

    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    _body(folder)
    _approval(folder)
    _content_check(folder, result="fail", criteria=[{"id": "objetivo", "status": "flojo"}, {"id": "metodologia", "status": "cumple"}])
    status = doc_status.derive(folder)
    assert "user's literal edit orders" in status.gate
    assert "approval_packet.py" in status.gate
    assert "--open" in status.gate
    assert "--verify-brief --since verification.yml" in status.gate
    assert "re-approve" not in status.gate
    assert "run the check" not in status.gate


import doc_status
from conftest import (
    _approval,
    _body,
    _config,
    _marker_text,
    _report,
    _sources_bib,
)


def _fresh_draft(folder: Path) -> Path:
    """Write a draft PDF plus the record of the body.md bytes it rendered."""
    from approval_marker import draft_record_path, sha256_file

    pdf = _config(folder).pdf_path
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-draft")
    draft_record_path(pdf).write_text(sha256_file(folder / "body.md") + "\n", encoding="utf-8")
    return pdf


def test_approval_absent_is_pending_not_blocked(tmp_path: Path) -> None:
    """A missing marker is ordinary progress, so later phases wait, not abort."""
    folder = tmp_path / "wf"
    _report(folder)

    phase = doc_status._phase_approval(folder, _config(folder), None)

    assert phase.name == "approval"
    assert phase.state == doc_status.PENDING
    assert phase.blocked_reason == ""
    assert "approval.yml" in phase.detail
    assert not (folder / "approval.yml").exists()


def test_approval_current_is_done(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _approval(folder)

    phase = doc_status._phase_approval(folder, _config(folder), None)

    assert phase.state == doc_status.DONE
    assert phase.blocked_reason == ""
    assert phase.state != doc_status.BLOCKED
    # The marker binds exactly one artifact, body.md (approval_marker.py
    # REQUIRED_KEYS); the detail must name it and nothing else.
    assert "body.md" in phase.detail
    assert "preview.md" not in phase.detail


def test_approval_body_hash_mismatch_is_pending_for_reapproval(tmp_path: Path) -> None:
    """A body edited after approval routes back to approval, never blocks the route."""
    folder = tmp_path / "wf"
    _report(folder)
    _approval(folder, body_sha256="0" * 64)

    phase = doc_status._phase_approval(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert phase.blocked_reason == ""
    assert "body.md" in phase.detail
    assert "re-approve" in phase.detail
    assert phase.state != doc_status.DONE


def test_approval_unrelated_edit_after_approval_stays_done(tmp_path: Path) -> None:
    """TRIANGULATE: the marker binds only body.md; editing an unrelated artifact
    (sources.bib) is not an approval event, so the phase stays done."""
    folder = tmp_path / "wf"
    _report(folder)
    _approval(folder)
    _sources_bib(folder, count=6)

    phase = doc_status._phase_approval(folder, _config(folder), None)

    assert phase.state == doc_status.DONE
    assert phase.blocked_reason == ""


def test_approval_body_edited_after_approval_is_pending(tmp_path: Path) -> None:
    """TRIANGULATE: editing body.md after approval sends the route back to approval."""
    folder = tmp_path / "wf"
    _report(folder)
    _approval(folder)
    _body(folder, "# Informe\n\nOtro cuerpo.\n")

    phase = doc_status._phase_approval(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert phase.blocked_reason == ""
    assert "re-approve" in phase.detail


def test_approval_marker_without_body_hash_is_malformed(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _approval(folder, drop=("body_sha256",))

    phase = doc_status._phase_approval(folder, _config(folder), None)

    assert phase.state == doc_status.BLOCKED
    assert phase.blocked_reason == "approval_marker_malformed"
    assert phase.state != doc_status.DONE


def test_approval_body_missing_with_marker_present_is_malformed(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _approval(folder)
    (folder / "body.md").unlink()

    phase = doc_status._phase_approval(folder, _config(folder), None)

    assert phase.state == doc_status.BLOCKED
    assert phase.blocked_reason == "approval_marker_malformed"


def test_approval_blank_required_key_is_malformed(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _approval(folder, approved_by="   ")

    phase = doc_status._phase_approval(folder, _config(folder), None)

    assert phase.state == doc_status.BLOCKED
    assert phase.blocked_reason == "approval_marker_malformed"
    assert phase.state != doc_status.DONE


def test_approval_unparsable_marker_is_malformed_not_absent(tmp_path: Path) -> None:
    """TRIANGULATE: a bad marker is named, never silently treated as absent."""
    folder = tmp_path / "wf"
    _report(folder)
    _marker_text(folder, "body_sha256: [unclosed\n")

    phase = doc_status._phase_approval(folder, _config(folder), None)

    assert phase.state == doc_status.BLOCKED
    assert phase.blocked_reason == "approval_marker_malformed"


def test_approval_derivation_never_repairs_the_marker(tmp_path: Path) -> None:
    """A stale or malformed marker is data the tool reports, never rewrites."""
    folder = tmp_path / "wf"
    _report(folder)
    marker = _approval(folder, body_sha256="0" * 64)
    before = marker.read_bytes()

    doc_status._phase_approval(folder, _config(folder), None)

    assert marker.read_bytes() == before


# ---------------------------------------------------------------------------
# Task 9.1: the format decisions ride on the approval batch
# ---------------------------------------------------------------------------


def _verified_folder(folder: Path, **report_extra: object) -> None:
    """A folder past approval and verify, with the format answers recorded."""
    from conftest import _content_check, _choose_format, _cited_body, _rubric, _skip_research, _sources_bib

    _report(folder)
    _skip_research(folder)
    _sources_bib(folder)
    _rubric(folder)
    _cited_body(folder)
    _approval(folder)
    _content_check(folder)
    _choose_format(folder, "aa", **report_extra)


def test_format_recorded_with_approval_goes_straight_to_generate(tmp_path: Path) -> None:
    """Format, output and metadata recorded at approval: no separate format stop."""
    folder = tmp_path / "wf"
    _verified_folder(folder)

    status = doc_status.derive(folder)

    phases = {phase.name: phase for phase in status.phases}
    assert phases["format"].state == doc_status.DONE
    assert status.next_token == "generate"


def test_format_without_output_is_pending_and_names_only_output(tmp_path: Path) -> None:
    """PDF/DOCX has no default: a recorded format without ``output:`` stays pending."""
    folder = tmp_path / "wf"
    _verified_folder(folder, output=None)

    status = doc_status.derive(folder)

    phases = {phase.name: phase for phase in status.phases}
    assert phases["format"].state == "current"
    assert phases["format"].detail.endswith("output")
    assert "subject" not in phases["format"].detail
    assert status.next_token == "format"


def test_approval_guidance_asks_the_format_batch(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _body(folder)
    _fresh_draft(folder)

    guidance = doc_status._guidance("approval", folder)

    for token in ("ask_user_choice", "AA", "APE", "libre", "PDF", "DOCX", "same batch", "never infer"):
        assert token in guidance


def test_approval_guidance_records_format_answers_even_when_changes_are_requested(tmp_path: Path) -> None:
    """#80: format answers are report.yml data; only approval.yml waits for the approve."""
    folder = tmp_path / "wf"
    _report(folder)
    _body(folder)
    _fresh_draft(folder)

    guidance = doc_status._guidance("approval", folder)

    assert "as soon as" in guidance
    assert "even when the user requests changes" in guidance
    assert "only when approval.yml is written" not in guidance


def test_unchosen_format_offers_ape_aa_acd_or_libre(tmp_path: Path) -> None:
    """aa-acd-templates S5: every format prompt offers APE, AA, ACD or libre."""
    folder = tmp_path / "wf"
    _report(folder)
    _body(folder)
    _fresh_draft(folder)
    documents = tmp_path / "Documents"

    approval = doc_status._guidance("approval", folder, documents_root=documents)
    fmt = doc_status._guidance("format", folder, documents_root=documents)
    state = doc_status._phase_format(folder, doc_status.ReportConfig.load(folder), documents)

    assert "document format APE, AA, ACD or libre" in approval
    assert "for APE, AA, ACD or libre" in fmt
    assert state.detail == "format not chosen: ask the user APE, AA, ACD or libre"


def test_approval_guidance_asks_only_approval_once_the_format_is_recorded(tmp_path: Path) -> None:
    """#80: after a change request the gate asks only to approve body.md."""
    from conftest import _choose_format

    folder = tmp_path / "wf"
    _report(folder)
    _body(folder)
    _fresh_draft(folder)
    _choose_format(folder, "aa")

    guidance = doc_status._guidance("approval", folder, documents_root=tmp_path / "Documents")

    assert "ask only whether the user approves" in guidance
    assert "APE, AA, ACD or libre" not in guidance
    assert "PDF or DOCX" not in guidance
    assert "--no-approval-check" in guidance


def test_approval_guidance_names_only_the_format_fields_still_missing(tmp_path: Path) -> None:
    """#80: a recorded format without ``output:`` reopens only ``output``."""
    from conftest import _choose_format

    folder = tmp_path / "wf"
    _report(folder)
    _body(folder)
    _fresh_draft(folder)
    _choose_format(folder, "aa", output=None)

    guidance = doc_status._guidance("approval", folder, documents_root=tmp_path / "Documents")

    assert "still missing: output" in guidance
    assert "APE, AA, ACD or libre" not in guidance


def _course_documents(tmp_path: Path) -> Path:
    documents = tmp_path / "Documents"
    repo = documents / "Academicos" / "redes"
    repo.mkdir(parents=True)
    (repo / "AGENTS.md").write_text("- `unidad-<n>/<tipo>-<m>-<tema>/`\n", encoding="utf-8")
    return documents


def test_approval_guidance_names_a_missing_course_folder_as_a_field(tmp_path: Path) -> None:
    """Review R2-approval-gaps-string-parse: no message text spliced in as a field list."""
    from conftest import _choose_format

    documents = _course_documents(tmp_path)
    folder = tmp_path / "wf"
    _report(folder, subject="Redes")
    _body(folder)
    _fresh_draft(folder)
    _choose_format(folder, "aa")

    guidance = doc_status._guidance("approval", folder, documents_root=documents)

    assert "still missing: delivery folder" in guidance
    assert "delivery_dir not set" not in guidance
    assert "missing format metadata" not in guidance


def test_approval_guidance_with_an_unusable_folder_asks_only_approval(tmp_path: Path) -> None:
    """A folder problem is not a format field: approve, and the format phase reports it."""
    from conftest import _choose_format

    delivery = tmp_path / "entrega"
    delivery.mkdir()
    (delivery / "vieja.html").write_text("<html></html>", encoding="utf-8")
    folder = tmp_path / "wf"
    _report(folder)
    _body(folder)
    _fresh_draft(folder)
    _choose_format(folder, "aa", delivery_dir=f'"{delivery}"')

    guidance = doc_status._guidance("approval", folder, documents_root=tmp_path / "Documents")

    assert "ask only whether the user approves" in guidance
    assert "still missing" not in guidance
    assert "delivery folder unusable" in guidance


def test_approval_guidance_with_a_blocked_format_asks_only_approval(tmp_path: Path) -> None:
    """Review R3-blocked-approval-untested: a blocked format is reported, never re-asked."""
    from conftest import _choose_format

    folder = tmp_path / "wf"
    _report(folder)
    _body(folder)
    _fresh_draft(folder)
    _choose_format(folder, "zz")

    guidance = doc_status._guidance("approval", folder, documents_root=tmp_path / "Documents")

    assert "ask only whether the user approves" in guidance
    assert "the format phase still reports: format=zz not recognized" in guidance
    assert "APE, AA, ACD or libre" not in guidance
    assert "still missing" not in guidance


def test_format_guidance_asks_only_missing_fields(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)

    assert "only the missing" in doc_status._guidance("format", folder)


def test_approval_guidance_previews_the_pdf_before_asking(tmp_path: Path) -> None:
    """Task 11(a): build and inspect a preview first, then show its path with body.md."""
    folder = tmp_path / "wf"
    _report(folder)
    _body(folder)
    _fresh_draft(folder)

    guidance = doc_status._guidance("approval", folder)

    for token in ("--no-approval-check", "preview", "inspect", "before asking", "file://"):
        assert token in guidance
    assert "never the final" in guidance
    assert str(folder) in guidance


def test_approval_guidance_asks_format_spec_when_libre(tmp_path: Path) -> None:
    """Task 11(b): choosing libre needs format_spec in the same batch, as a structured choice."""
    folder = tmp_path / "wf"
    _report(folder)
    _body(folder)
    _fresh_draft(folder)

    guidance = doc_status._guidance("approval", folder)

    assert "format_spec" in guidance
    assert "libre" in guidance
    assert "sin portada" in guidance and "con portada" in guidance


def test_approval_gate_demands_a_rebuild_when_no_draft_record_exists(tmp_path: Path) -> None:
    """#59: no record of a rendered draft means the gate must not be presented."""
    folder = tmp_path / "wf"
    _report(folder)
    _body(folder)

    guidance = doc_status._guidance("approval", folder)

    assert "rebuild the draft PDF" in guidance
    assert "--no-approval-check" in guidance
    assert "ask_user_choice" not in guidance


def test_approval_gate_demands_a_rebuild_when_body_changed_after_the_draft(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _body(folder)
    _fresh_draft(folder)
    _body(folder, "# Informe\n\nEditado despues del PDF.\n")

    guidance = doc_status._guidance("approval", folder)

    assert "rebuild the draft PDF" in guidance
    assert "ask_user_choice" not in guidance


def test_approval_gate_with_a_fresh_draft_lists_absolute_paths(tmp_path: Path) -> None:
    """#60: the matching record unlocks the prompt, which names both files."""
    folder = tmp_path / "wf"
    _report(folder)
    _body(folder)
    pdf = _fresh_draft(folder)

    guidance = doc_status._guidance("approval", folder)

    assert "rebuild the draft PDF" not in guidance
    assert "ask_user_choice" in guidance
    assert str(pdf) in guidance
    assert str(folder / "body.md") in guidance


# verify-concise-drafts T8 (S2): verify runs before approval, one approval packet.


def test_verify_precedes_approval_in_the_route() -> None:
    assert doc_status.PHASES.index("verify") < doc_status.PHASES.index("approval")


def test_an_unverified_draft_routes_to_verify_not_approval(tmp_path: Path) -> None:
    from conftest import _cited_body, _rubric

    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    _cited_body(folder)
    assert doc_status.derive(folder).next_token == "verify"


def test_a_verified_draft_routes_to_approval(tmp_path: Path) -> None:
    from conftest import _cited_body, _content_check, _rubric

    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    _cited_body(folder)
    _content_check(folder)
    assert doc_status.derive(folder).next_token == "approval"


def test_verify_guidance_reuses_the_previous_verification(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    assert "--verify-brief --since verification.yml when it exists" in doc_status._guidance("verify", folder)


def test_approval_gate_with_a_fresh_draft_prints_the_packet(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _body(folder)
    _fresh_draft(folder)
    guidance = doc_status._guidance("approval", folder)
    assert "approval_packet.py" in guidance
    assert "--open" in guidance
    assert str(folder) in guidance


def test_approval_guidance_inspects_only_changed_preview_pages(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _body(folder)
    _fresh_draft(folder)
    guidance = doc_status._guidance("approval", folder)
    assert "visual_pdf_auditor.py" in guidance
    assert "only the Changed pages" in guidance
    assert "inspect every page," not in guidance


def test_a_bounded_edit_after_approval_reports_done_with_the_carried_detail(tmp_path: Path) -> None:
    import approval_marker
    import doc_status
    from conftest import _body

    folder = tmp_path / "wf"
    body = _body(folder, "# Informe\n\nPreparado por Juan Perez.\n")
    approval_marker.record_approval(folder, "Alejandro")
    body.write_text("# Informe\n\nPreparado por Ana Perez.\n", encoding="utf-8")

    phase = doc_status._phase_approval(folder, None, None)

    assert phase.state == doc_status.DONE
    assert phase.detail == "bounded edit since approval (2 words)"


def test_an_unbounded_edit_after_approval_is_still_pending(tmp_path: Path) -> None:
    import approval_marker
    import doc_status
    from conftest import _body

    folder = tmp_path / "wf"
    body = _body(folder, "# Informe\n\nPreparado por Juan Perez.\n")
    approval_marker.record_approval(folder, "Alejandro")
    body.write_text("# Otro titulo\n\nPreparado por Juan Perez.\n", encoding="utf-8")

    phase = doc_status._phase_approval(folder, None, None)

    assert phase.state == doc_status.PENDING
    assert "re-approve" in phase.detail


def test_generate_rebuilds_after_a_carried_edit_but_not_for_an_untouched_body(tmp_path: Path) -> None:
    """A carried approval skips the question, never the rebuild: the PDF must postdate body.md."""
    import approval_marker
    import doc_status
    from conftest import _body, _config, _mtime, _pdf, _report

    t0 = 1_700_000_000.0
    folder = tmp_path / "wf"
    _report(folder)
    body = _body(folder, "# Informe\n\nPreparado por Juan Perez.\n")
    approval_marker.record_approval(folder, "Alejandro")
    _mtime(folder / "report.yml", t0)
    _mtime(folder / "approval.yml", t0 + 60)
    _mtime(body, t0 + 30)
    _pdf(folder, mtime=t0 + 120)
    assert doc_status._phase_generate(folder, _config(folder), None).state == doc_status.DONE

    body.write_text("# Informe\n\nPreparado por Ana Perez.\n", encoding="utf-8")
    _mtime(body, t0 + 180)

    phase = doc_status._phase_generate(folder, _config(folder), None)
    assert phase.state == doc_status.PENDING
    assert "body.md" in phase.detail
