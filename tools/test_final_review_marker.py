"""Tests for the final human review marker in ``tools/final_review_marker.py``.

``final_review_state()`` is the predicate behind the delivery gate: the
publisher (``publish_pdf``) and the deliver entrypoint (``deliver_report``)
both refuse to publish unless a ``final-review.yml`` marker binds the exact
bytes of the PDF being published. Like the approval marker, the predicate is a
pure read: it never writes, never creates a directory, and never raises for a
bad marker -- every invalid shape is ``malformed`` data the caller can report.
A stale marker means the reviewed bytes are gone: the PDF is missing or its
hash no longer matches, so the human must review the current PDF again.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import final_review_marker

PDF_BYTES = b"%PDF-1.7\nfinal reviewed content\n"
OTHER_PDF_BYTES = b"%PDF-1.7\nrebuilt after review\n"


def _write_pdf(folder: Path, content: bytes = PDF_BYTES) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    pdf = folder / "final" / "report.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(content)
    return pdf


def _write_marker(folder: Path, body: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / "final-review.yml"
    marker.write_text(body, encoding="utf-8")
    return marker


def _marker_body(pdf: Path, *, pdf_sha: str | None = None) -> str:
    if pdf_sha is None:
        pdf_sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    return (
        "schema: academic.doc-final-review/v1\n"
        f"pdf_sha256: {pdf_sha}\n"
        "reviewed_at: 2026-09-10T16:30:00Z\n"
        "reviewed_by: Alejandro\n"
    )


def _snapshot(folder: Path) -> list[tuple[str, int, bool]]:
    return sorted(
        (path.name, path.stat().st_size, path.is_dir()) for path in folder.iterdir()
    )


def test_marker_constants_are_declared() -> None:
    """The marker contract is a stable, importable surface for both consumers."""
    assert final_review_marker.MARKER_NAME == "final-review.yml"
    assert final_review_marker.MARKER_SCHEMA == "academic.doc-final-review/v1"
    assert final_review_marker.REQUIRED_KEYS == (
        "pdf_sha256",
        "reviewed_at",
        "reviewed_by",
    )


def test_state_absent_current_and_stale(tmp_path: Path) -> None:
    """The bounded state vocabulary, derived read-only from disk."""
    # absent — there is no marker at all
    pdf_only = tmp_path / "pdf-only"
    _write_pdf(pdf_only)
    absent = final_review_marker.final_review_state(pdf_only, pdf_only / "final" / "report.pdf")
    assert absent.state == "absent"
    assert absent.reason == "final_review_marker_absent"
    assert "final-review.yml" in absent.detail
    assert absent.detail.isascii()

    # current — the marker hash equals the exact PDF bytes
    current_folder = tmp_path / "current"
    pdf = _write_pdf(current_folder)
    _write_marker(current_folder, _marker_body(pdf))
    current = final_review_marker.final_review_state(current_folder, pdf)
    assert current.state == "current"
    assert current.reason == ""
    assert current.detail == ""

    # stale — the PDF was rebuilt after the human reviewed it
    stale_folder = tmp_path / "stale"
    stale_pdf = _write_pdf(stale_folder)
    _write_marker(stale_folder, _marker_body(stale_pdf))
    stale_pdf.write_bytes(OTHER_PDF_BYTES)
    stale = final_review_marker.final_review_state(stale_folder, stale_pdf)
    assert stale.state == "stale"
    assert stale.reason == "final_review_marker_stale"
    assert "pdf_sha256" in stale.detail
    assert stale.detail.isascii()


def test_pdf_missing_after_review_is_stale_not_malformed(tmp_path: Path) -> None:
    """Reviewed bytes that disappeared are a stale review, not a broken marker."""
    folder = tmp_path / "pdf-gone"
    pdf = _write_pdf(folder)
    _write_marker(folder, _marker_body(pdf))
    pdf.unlink()

    state = final_review_marker.final_review_state(folder, pdf)

    assert state.state == "stale"
    assert state.reason == "final_review_marker_stale"
    assert state.detail.isascii()


def test_pdf_hash_override_produces_stale(tmp_path: Path) -> None:
    """TRIANGULATE: a recorded hash that never matched the bytes is stale too."""
    folder = tmp_path / "override"
    pdf = _write_pdf(folder)
    _write_marker(folder, _marker_body(pdf, pdf_sha="0" * 64))

    state = final_review_marker.final_review_state(folder, pdf)

    assert state.state == "stale"
    assert state.reason == "final_review_marker_stale"


def test_malformed_shapes_name_the_offender(tmp_path: Path) -> None:
    """Every invalid marker is malformed with a bounded, ASCII detail."""
    pdf = _write_pdf(tmp_path)
    good_sha = hashlib.sha256(PDF_BYTES).hexdigest()
    reviewed_at = "2026-09-10T16:30:00Z"

    def case(name: str) -> Path:
        folder = tmp_path / name
        folder.mkdir()
        return folder

    bad_yaml = case("bad-yaml")
    _write_marker(bad_yaml, "pdf_sha256: [unclosed\nreviewed_at: x\n")

    missing_sha = case("missing-sha")
    _write_marker(missing_sha, f"reviewed_at: {reviewed_at}\nreviewed_by: Alejandro\n")

    missing_at = case("missing-at")
    _write_marker(missing_at, f"pdf_sha256: {good_sha}\nreviewed_by: Alejandro\n")

    missing_by = case("missing-by")
    _write_marker(missing_by, f"pdf_sha256: {good_sha}\nreviewed_at: {reviewed_at}\n")

    blank_by = case("blank-by")
    _write_marker(
        blank_by,
        f"pdf_sha256: {good_sha}\nreviewed_at: {reviewed_at}\nreviewed_by: \"   \"\n",
    )

    for folder in (bad_yaml, missing_sha, missing_at, missing_by, blank_by):
        state = final_review_marker.final_review_state(folder, pdf)
        assert state.state == "malformed", f"{folder.name}: {state}"
        assert state.reason == "final_review_marker_malformed", folder.name
        assert state.detail.isascii(), folder.name

    bad_yaml_state = final_review_marker.final_review_state(bad_yaml, pdf)
    assert "final-review.yml" in bad_yaml_state.detail
    missing_sha_state = final_review_marker.final_review_state(missing_sha, pdf)
    assert "pdf_sha256" in missing_sha_state.detail


def test_extra_keys_are_ignored(tmp_path: Path) -> None:
    """Extra recorded data never invalidates a marker whose bound hash matches."""
    folder = tmp_path / "extra"
    pdf = _write_pdf(folder)
    _write_marker(folder, _marker_body(pdf) + "notes: looked good\n")

    state = final_review_marker.final_review_state(folder, pdf)

    assert state.state == "current"


def test_state_is_read_only_and_never_raises(tmp_path: Path) -> None:
    """A bad marker is data, not a crash, and nothing on disk is created."""
    folder = tmp_path / "read-only"
    pdf = _write_pdf(folder)
    _write_marker(folder, "pdf_sha256: [unclosed\n")
    before = _snapshot(folder)

    for _ in range(2):
        state = final_review_marker.final_review_state(folder, pdf)
        assert state.state == "malformed"
        assert _snapshot(folder) == before

    missing = tmp_path / "missing"
    missing.mkdir()
    assert final_review_marker.final_review_state(missing, pdf).state == "absent"
    assert sorted(path.name for path in missing.iterdir()) == []


# ---------------------------------------------------------------------------
# course-deliverables-hierarchy T2: bibliography binding for declared .bib
# ---------------------------------------------------------------------------


def _write_bib(folder: Path, text: str = "@book{a, title = \"T\"}\n") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    bib = folder / "sources.bib"
    bib.write_text(text, encoding="utf-8")
    return bib


def _marker_with_bibliography(pdf: Path, bib: Path, *, bib_sha: str | None = None) -> str:
    import yaml

    body = {
        "schema": final_review_marker.MARKER_SCHEMA,
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "bibliography_sha256": bib_sha or hashlib.sha256(bib.read_bytes()).hexdigest(),
        "reviewed_at": "2026-09-10T16:30:00Z",
        "reviewed_by": "Alejandro",
    }
    return yaml.safe_dump(body, sort_keys=False)


def test_marker_without_bibliography_request_keeps_the_pdf_only_contract(tmp_path: Path) -> None:
    """A pdf-only review (no bibliography argument) ignores any marker extra keys."""
    pdf = _write_pdf(tmp_path / "wf")
    _write_marker(tmp_path / "wf", _marker_body(pdf))

    state = final_review_marker.final_review_state(tmp_path / "wf", pdf)

    assert state.state == "current"


def test_marker_binds_declared_bibliography_bytes(tmp_path: Path) -> None:
    """With a declared bibliography the marker must bind its exact bytes too."""
    folder = tmp_path / "wf"
    pdf = _write_pdf(folder)
    bib = _write_bib(folder)
    _write_marker(folder, _marker_with_bibliography(pdf, bib))

    state = final_review_marker.final_review_state(folder, pdf, bibliography=bib)

    assert state.state == "current"
    assert state.reason == ""


def test_marker_without_bibliography_hash_is_malformed_when_declared(tmp_path: Path) -> None:
    """A declared bibliography makes a pdf-only marker invalid, never current."""
    folder = tmp_path / "wf"
    pdf = _write_pdf(folder)
    bib = _write_bib(folder)
    _write_marker(folder, _marker_body(pdf))

    state = final_review_marker.final_review_state(folder, pdf, bibliography=bib)

    assert state.state == "malformed"
    assert "bibliography_sha256" in state.detail


def test_marker_stale_when_bibliography_bytes_change(tmp_path: Path) -> None:
    """Editing the bibliography after the human OK stales the review."""
    folder = tmp_path / "wf"
    pdf = _write_pdf(folder)
    bib = _write_bib(folder)
    _write_marker(folder, _marker_with_bibliography(pdf, bib))
    bib.write_text("@book{a, title = \"CHANGED\"}\n", encoding="utf-8")

    state = final_review_marker.final_review_state(folder, pdf, bibliography=bib)

    assert state.state == "stale"
    assert "bibliography_sha256" in state.detail


def test_marker_stale_when_declared_bibliography_disappears(tmp_path: Path) -> None:
    """A declared bibliography that vanished is unreadable evidence, not a pass."""
    folder = tmp_path / "wf"
    pdf = _write_pdf(folder)
    bib = _write_bib(folder)
    _write_marker(folder, _marker_with_bibliography(pdf, bib))
    bib.unlink()

    state = final_review_marker.final_review_state(folder, pdf, bibliography=bib)

    assert state.state == "stale"
    assert "bibliography_sha256" in state.detail


# -- Bounded-edit carry (bounded-edit-approval T2) -----------------------------

import pytest  # noqa: E402
import yaml  # noqa: E402

REPORT_YML = "title: T\npdf: final/report.pdf\n"
REVIEW_BODY = "# Informe\n\nPreparado por Juan Perez para la catedra de simulacion.\n\n## Resultados\n\nTexto.\n"


def _validation(folder: Path, pdf: Path, *, result: str = "pass", pdf_sha: str | None = None, **extra: str) -> Path:
    data = {
        "schema": "academic.doc-validation/v1",
        "artifact_sha256": pdf_sha or hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "result": result,
        **extra,
    }
    path = folder / "validation.yml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _reviewed(folder: Path, text: str = REVIEW_BODY) -> tuple[Path, Path]:
    """A folder with body.md, a PDF and a recorded final review."""
    pdf = _write_pdf(folder)
    (folder / "report.yml").write_text(REPORT_YML, encoding="utf-8")
    body = folder / "body.md"
    body.write_text(text, encoding="utf-8")
    final_review_marker.record_final_review(folder, "Alejandro", pdf)
    return body, pdf


def _rebuild(pdf: Path) -> None:
    pdf.write_bytes(OTHER_PDF_BYTES)


def test_record_final_review_writes_marker_and_snapshot_together(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    body, pdf = _reviewed(folder)

    data = yaml.safe_load((folder / "final-review.yml").read_text(encoding="utf-8"))
    assert data["schema"] == final_review_marker.MARKER_SCHEMA
    assert data["pdf_sha256"] == hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert data["body_sha256"] == hashlib.sha256(body.read_bytes()).hexdigest()
    assert data["reviewed_by"] == "Alejandro" and data["reviewed_at"]
    assert "bibliography_sha256" not in data
    assert (folder / "reviewed-body.md").read_bytes() == body.read_bytes()
    assert final_review_marker.final_review_state(folder, pdf).state == "current"
    assert not [p for p in folder.iterdir() if p.name.endswith(".tmp")]


def test_record_final_review_binds_the_declared_bibliography(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    pdf = _write_pdf(folder)
    (folder / "body.md").write_text(REVIEW_BODY, encoding="utf-8")
    (folder / "report.yml").write_text(REPORT_YML, encoding="utf-8")
    bib = folder / "sources.bib"
    bib.write_text("@book{a, title={A}}\n", encoding="utf-8")

    final_review_marker.record_final_review(folder, "Alejandro", pdf, bibliography=bib)

    data = yaml.safe_load((folder / "final-review.yml").read_text(encoding="utf-8"))
    assert data["bibliography_sha256"] == hashlib.sha256(bib.read_bytes()).hexdigest()
    assert final_review_marker.final_review_state(folder, pdf, bibliography=bib).state == "current"


@pytest.mark.parametrize("missing", ["name", "pdf", "body", "report"])
def test_record_final_review_refuses_incomplete_input_and_writes_nothing(tmp_path: Path, missing: str) -> None:
    folder = tmp_path / "wf"
    pdf = _write_pdf(folder)
    (folder / "body.md").write_text(REVIEW_BODY, encoding="utf-8")
    (folder / "report.yml").write_text(REPORT_YML, encoding="utf-8")
    name = "Alejandro"
    if missing == "name":
        name = " "
    elif missing == "pdf":
        pdf.unlink()
    elif missing == "report":
        (folder / "report.yml").unlink()
    else:
        (folder / "body.md").unlink()
    before = sorted(p.name for p in folder.iterdir())

    with pytest.raises(ValueError):
        final_review_marker.record_final_review(folder, name, pdf)

    assert sorted(p.name for p in folder.iterdir()) == before


def test_final_review_cli_records_the_gate(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    folder.mkdir()
    (folder / "report.yml").write_text("title: T\npdf: final/report.pdf\n", encoding="utf-8")
    pdf = _write_pdf(folder)
    (folder / "body.md").write_text(REVIEW_BODY, encoding="utf-8")

    assert final_review_marker.main(["record", str(folder), "--by", "Alejandro"]) == 0

    assert final_review_marker.final_review_state(folder, pdf).state == "current"
    assert (folder / "reviewed-body.md").is_file()


def test_bounded_edit_with_a_passing_validation_of_the_current_pdf_is_carried(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    body, pdf = _reviewed(folder)
    body.write_text(REVIEW_BODY.replace("Juan", "Ana"), encoding="utf-8")
    _rebuild(pdf)
    _validation(folder, pdf)

    state = final_review_marker.final_review_state(folder, pdf)

    assert state.state == "carried"
    assert state.reason == ""
    assert state.detail == "bounded edit since final review (2 words)"
    assert state.ok


def test_carry_is_stale_when_the_validation_is_for_another_pdf(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    body, pdf = _reviewed(folder)
    body.write_text(REVIEW_BODY.replace("Juan", "Ana"), encoding="utf-8")
    _rebuild(pdf)
    _validation(folder, pdf, pdf_sha="0" * 64)
    assert final_review_marker.final_review_state(folder, pdf).state == "stale"


@pytest.mark.parametrize("shape", ["fail", "absent"])
def test_carry_is_stale_without_a_passing_validation(tmp_path: Path, shape: str) -> None:
    folder = tmp_path / "wf"
    body, pdf = _reviewed(folder)
    body.write_text(REVIEW_BODY.replace("Juan", "Ana"), encoding="utf-8")
    _rebuild(pdf)
    if shape == "fail":
        _validation(folder, pdf, result="fail")
    assert final_review_marker.final_review_state(folder, pdf).state == "stale"


def test_carry_is_stale_with_a_large_diff(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    body, pdf = _reviewed(folder)
    body.write_text(REVIEW_BODY + " ".join(["nuevo"] * 41) + "\n", encoding="utf-8")
    _rebuild(pdf)
    _validation(folder, pdf)
    assert final_review_marker.final_review_state(folder, pdf).state == "stale"


def test_carry_is_stale_after_a_heading_change(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    body, pdf = _reviewed(folder)
    body.write_text(REVIEW_BODY.replace("## Resultados", "## Hallazgos"), encoding="utf-8")
    _rebuild(pdf)
    _validation(folder, pdf)
    assert final_review_marker.final_review_state(folder, pdf).state == "stale"


def test_carry_is_stale_when_the_snapshot_is_missing_or_tampered(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    body, pdf = _reviewed(folder)
    body.write_text(REVIEW_BODY.replace("Juan", "Ana"), encoding="utf-8")
    _rebuild(pdf)
    _validation(folder, pdf)
    snapshot = folder / "reviewed-body.md"
    snapshot.write_text(REVIEW_BODY.replace("Juan", "Luis"), encoding="utf-8")
    assert final_review_marker.final_review_state(folder, pdf).state == "stale"
    snapshot.unlink()
    assert final_review_marker.final_review_state(folder, pdf).state == "stale"


def test_carry_with_a_declared_bibliography_needs_it_bound_in_the_validation(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    pdf = _write_pdf(folder)
    body = folder / "body.md"
    body.write_text(REVIEW_BODY, encoding="utf-8")
    (folder / "report.yml").write_text(REPORT_YML, encoding="utf-8")
    bib = folder / "sources.bib"
    bib.write_text("@book{a, title={A}}\n", encoding="utf-8")
    final_review_marker.record_final_review(folder, "Alejandro", pdf, bibliography=bib)
    body.write_text(REVIEW_BODY.replace("Juan", "Ana"), encoding="utf-8")
    _rebuild(pdf)

    _validation(folder, pdf)
    assert final_review_marker.final_review_state(folder, pdf, bibliography=bib).state == "stale"

    _validation(folder, pdf, bibliography_sha256=hashlib.sha256(bib.read_bytes()).hexdigest())
    assert final_review_marker.final_review_state(folder, pdf, bibliography=bib).state == "carried"

    bib.write_text("@book{a, title={B}}\n", encoding="utf-8")
    assert final_review_marker.final_review_state(folder, pdf, bibliography=bib).state == "stale"


def test_a_marker_without_a_body_hash_never_carries(tmp_path: Path) -> None:
    """A hand-written marker has no body_sha256, so no snapshot can vouch for it."""
    folder = tmp_path / "wf"
    pdf = _write_pdf(folder)
    (folder / "body.md").write_text(REVIEW_BODY, encoding="utf-8")
    (folder / "reviewed-body.md").write_text(REVIEW_BODY, encoding="utf-8")
    _write_marker(folder, _marker_body(pdf))
    _rebuild(pdf)
    _validation(folder, pdf)
    assert final_review_marker.final_review_state(folder, pdf).state == "stale"


def _bounded_edit_with_validated_rebuild(folder: Path) -> tuple[Path, Path]:
    body, pdf = _reviewed(folder)
    body.write_text(REVIEW_BODY.replace("Juan", "Ana"), encoding="utf-8")
    _rebuild(pdf)
    _validation(folder, pdf)
    return body, pdf


def test_carry_is_stale_when_the_render_settings_changed(tmp_path: Path) -> None:
    """The PDF may differ because report.yml changed, not body.md: that needs a fresh review."""
    folder = tmp_path / "wf"
    _, pdf = _bounded_edit_with_validated_rebuild(folder)
    (folder / "report.yml").write_text(REPORT_YML + "figure_placement: strict\n", encoding="utf-8")

    assert final_review_marker.final_review_state(folder, pdf).state == "stale"


def test_carry_holds_when_the_render_settings_are_unchanged(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _, pdf = _bounded_edit_with_validated_rebuild(folder)

    assert final_review_marker.final_review_state(folder, pdf).state == "carried"


def test_carry_ignores_delivery_only_settings(tmp_path: Path) -> None:
    """delivery_dir / deliver_bibliography never change the rendered PDF, so they do not stale a carry."""
    folder = tmp_path / "wf"
    _, pdf = _bounded_edit_with_validated_rebuild(folder)
    (folder / "report.yml").write_text(REPORT_YML + "delivery_dir: somewhere\n", encoding="utf-8")

    assert final_review_marker.final_review_state(folder, pdf).state == "carried"


def test_record_final_review_stores_the_render_digest(tmp_path: Path) -> None:
    import approval_marker

    folder = tmp_path / "wf"
    _reviewed(folder)

    data = yaml.safe_load((folder / "final-review.yml").read_text(encoding="utf-8"))
    assert data["render_sha256"] == approval_marker.render_digest(folder / "report.yml")


def test_a_marker_without_the_render_digest_never_carries(tmp_path: Path) -> None:
    """Markers recorded before the digest existed cannot vouch that the settings are unchanged."""
    folder = tmp_path / "wf"
    _, pdf = _bounded_edit_with_validated_rebuild(folder)
    marker = folder / "final-review.yml"
    data = yaml.safe_load(marker.read_text(encoding="utf-8"))
    del data["render_sha256"]
    marker.write_text(yaml.safe_dump(data), encoding="utf-8")

    assert final_review_marker.final_review_state(folder, pdf).state == "stale"


def test_a_missing_report_yml_never_carries(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _, pdf = _bounded_edit_with_validated_rebuild(folder)
    (folder / "report.yml").unlink()

    assert final_review_marker.final_review_state(folder, pdf).state == "stale"
