"""``output:`` gate, effective source minimum and unfinished intake (task 9.2)."""
from __future__ import annotations

from pathlib import Path

import doc_status
from conftest import (
    _approval,
    _body,
    _choose_format,
    _config,
    _final_review,
    _pdf,
    _published,
    _report,
    _rubric,
    _sources_bib,
    _validation,
    _mtime,
)

SLUG = "informe-de-laboratorio"


def _format_phase(folder: Path, root: Path | None = None) -> doc_status.PhaseState:
    return doc_status._phase_format(folder, _config(folder), root)


def _legacy_folder(folder: Path) -> Path:
    """Format chosen, no ``output:`` recorded (reports from before task 9.1)."""
    _report(folder)
    _choose_format(folder, "aa", output=None)
    return folder


def test_new_run_without_output_still_asks_for_it(tmp_path: Path) -> None:
    phase = _format_phase(_legacy_folder(tmp_path / "wf"))

    assert phase.state == doc_status.PENDING and phase.detail.endswith("output")


def test_generated_pdf_alone_does_not_waive_the_output_answer(tmp_path: Path) -> None:
    folder = _legacy_folder(tmp_path / "wf")
    _pdf(folder)

    assert _format_phase(folder).state == doc_status.PENDING


def test_legacy_validated_pdf_without_output_is_not_pulled_back_to_format(tmp_path: Path) -> None:
    folder = _legacy_folder(tmp_path / "wf")
    pdf = _pdf(folder)
    _validation(folder, pdf=pdf)

    phase = _format_phase(folder)

    assert phase.state == doc_status.DONE and "pdf" in phase.detail.lower()


def test_legacy_delivered_pdf_without_output_is_not_pulled_back_to_format(tmp_path: Path) -> None:
    folder = _legacy_folder(tmp_path / "wf")
    pdf = _pdf(folder)
    root = tmp_path / "Documents"
    _published(root, category="Academicos/fisica", slug=SLUG, source=pdf)

    assert _format_phase(folder, root).state == doc_status.DONE


def test_explicit_output_wins_over_the_legacy_rule(tmp_path: Path) -> None:
    folder = _legacy_folder(tmp_path / "wf")
    pdf = _pdf(folder)
    _validation(folder, pdf=pdf)
    (folder / "report.yml").write_text(
        (folder / "report.yml").read_text(encoding="utf-8") + "output: docx\n", encoding="utf-8"
    )

    assert _format_phase(folder).state == doc_status.DONE


def test_invalid_output_value_is_blocked_and_named(tmp_path: Path) -> None:
    folder = _legacy_folder(tmp_path / "wf")
    (folder / "report.yml").write_text(
        (folder / "report.yml").read_text(encoding="utf-8") + "output: odt\n", encoding="utf-8"
    )

    phase = _format_phase(folder)

    assert phase.state == doc_status.BLOCKED
    assert "odt" in phase.detail and phase.blocked_reason == "unknown_output"


def test_valid_output_values_stay_done(tmp_path: Path) -> None:
    for value in ("pdf", "DOCX"):
        folder = tmp_path / value
        _report(folder)
        _choose_format(folder, "aa", output=value)
        assert _format_phase(folder).state == doc_status.DONE


def test_research_guidance_states_the_effective_minimum(tmp_path: Path) -> None:
    default = tmp_path / "default"
    _report(default)
    custom = tmp_path / "custom"
    _report(custom)
    (custom / "report.yml").write_text(
        (custom / "report.yml").read_text(encoding="utf-8") + "min_sources: 2\n", encoding="utf-8"
    )

    assert "at least 5 " in doc_status._guidance("research", default)
    assert "at least 2 " in doc_status._guidance("research", custom)
    assert "at least 5" not in doc_status._guidance("research", custom)


def test_research_gate_message_prints_the_effective_number(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    (folder / "report.yml").write_text(
        (folder / "report.yml").read_text(encoding="utf-8") + "min_sources: 2\n", encoding="utf-8"
    )
    _sources_bib(folder, count=1)

    phase = doc_status._phase_research(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING and "1/2" in phase.detail


def test_folder_without_report_yml_is_an_unfinished_intake(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _sources_bib(folder)
    _rubric(folder)
    _body(folder)

    status = doc_status.derive(folder)

    assert status.next_token == "intake"
    assert next(p for p in status.phases if p.name == "intake").detail == "report.yml missing"


def _finished_folder(tmp_path: Path) -> tuple[Path, Path, Path]:
    folder = tmp_path / "wf"
    _report(folder)
    pdf = _pdf(folder)
    root = tmp_path / "Documents"
    return folder, pdf, root


def test_delivered_needs_a_current_final_review_and_a_published_version(tmp_path: Path) -> None:
    folder, pdf, root = _finished_folder(tmp_path)
    config = _config(folder)
    _published(root, category="Academicos/fisica", slug=SLUG, source=pdf)

    # A published version without a current final-review.yml is not delivered.
    assert doc_status._phase_review(folder, config, root).state == doc_status.PENDING
    assert doc_status._phase_deliver(folder, config, root).state == doc_status.DONE

    # A current final-review.yml without a published version is not delivered either.
    other = tmp_path / "other"
    _report(other)
    _pdf(other)
    _final_review(other, pdf=other / "final" / "report.pdf")
    assert doc_status._phase_review(other, _config(other), root).state == doc_status.DONE
    assert doc_status._phase_deliver(other, _config(other), tmp_path / "empty").state == doc_status.PENDING

    # Both conditions together.
    _final_review(folder, pdf=pdf)
    assert doc_status._phase_review(folder, config, root).state == doc_status.DONE


def test_research_phase_reports_the_uncited_bibliography(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    (folder / "report.yml").write_text(
        (folder / "report.yml").read_text(encoding="utf-8") + "uncited_bibliography: true\n",
        encoding="utf-8",
    )
    (folder / "sources.bib").write_text("@misc{slides, title={Slides}}\n", encoding="utf-8")

    phase = doc_status._phase_research(folder, _config(folder), None)

    assert phase.state == doc_status.DONE
    assert phase.detail == "sources.bib lists 1 entry (uncited bibliography)"


def test_research_guidance_for_uncited_bibliography_does_not_ask_for_five(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    (folder / "report.yml").write_text(
        (folder / "report.yml").read_text(encoding="utf-8") + "uncited_bibliography: true\n",
        encoding="utf-8",
    )
    (folder / "sources.bib").write_text("% empty\n", encoding="utf-8")

    guidance = doc_status._guidance("research", folder, _config(folder))

    assert "at least 5" not in guidance
    assert "at least 1 entry" in guidance


def _course_repo(documents: Path, subject: str = "redes") -> Path:
    repo = documents / "Academicos" / subject
    repo.mkdir(parents=True)
    (repo / "AGENTS.md").write_text("- `unidad-<n>/<tipo>-<m>-<tema>/`\n", encoding="utf-8")
    return repo


def _course_report(folder: Path) -> Path:
    _report(folder, subject="Redes")
    _choose_format(folder, "aa")
    return folder


def test_course_repo_without_delivery_dir_keeps_format_pending(tmp_path: Path) -> None:
    """The destination is fixed before the build, never moved after approval."""
    documents = tmp_path / "Documents"
    repo = _course_repo(documents)
    folder = _course_report(tmp_path / "wf")

    phase = _format_phase(folder, documents)

    assert phase.state == doc_status.PENDING
    assert "delivery_dir" in phase.detail and str(repo) in phase.detail


def test_course_repo_with_delivery_dir_completes_format(tmp_path: Path) -> None:
    documents = tmp_path / "Documents"
    _course_repo(documents)
    folder = _course_report(tmp_path / "wf")
    report = folder / "report.yml"
    report.write_text(report.read_text(encoding="utf-8") + 'delivery_dir: "/x/unidad-1/aa-1-t/documento/"\n')

    assert _format_phase(folder, documents).state == doc_status.DONE


def _with_delivery_dir(folder: Path, delivery: Path) -> Path:
    report = folder / "report.yml"
    report.write_text(report.read_text(encoding="utf-8") + f'delivery_dir: "{delivery}"\n', encoding="utf-8")
    return folder


def test_unusable_delivery_folder_keeps_format_pending_before_the_build(tmp_path: Path) -> None:
    """#83: the publisher's refusal surfaces when delivery_dir is recorded, not at deliver."""
    delivery = tmp_path / "curso" / "unidad-1" / "ejercicio-2-taylor" / "documento"
    delivery.mkdir(parents=True)
    (delivery / "practica-vieja.html").write_text("<html></html>", encoding="utf-8")
    folder = _with_delivery_dir(_course_report(tmp_path / "wf"), delivery)
    _rubric(folder)
    _sources_bib(folder)
    _body(folder)
    _approval(folder)

    phase = _format_phase(folder, tmp_path / "Documents")
    status = doc_status.derive(folder, documents_root=tmp_path / "Documents")

    assert phase.state == doc_status.PENDING
    assert phase.detail.startswith("delivery folder unusable: La carpeta de entrega solo puede contener")
    assert str(delivery) in phase.detail
    assert {p.name: p.state for p in status.phases}["generate"] == doc_status.PENDING
    assert (delivery / "practica-vieja.html").is_file()


def test_delivery_dir_naming_a_file_is_a_reason_not_a_crash(tmp_path: Path) -> None:
    """Review R3-oserror-unbound-delivery: an unreadable folder keeps format pending."""
    delivery = tmp_path / "entrega"
    delivery.write_text("not a folder", encoding="utf-8")
    folder = _with_delivery_dir(_course_report(tmp_path / "wf"), delivery)

    phase = _format_phase(folder, tmp_path / "Documents")

    assert phase.state == doc_status.PENDING
    assert phase.detail.startswith(f"delivery folder unusable: {delivery} is not a readable folder (")
    assert delivery.read_text(encoding="utf-8") == "not a folder"


def test_delivery_folder_with_only_versioned_finals_completes_format(tmp_path: Path) -> None:
    delivery = tmp_path / "entrega"
    delivery.mkdir()
    folder = _with_delivery_dir(_course_report(tmp_path / "wf"), delivery)
    (delivery / f"{_config(folder).document_slug}-v001.pdf").write_bytes(b"%PDF-1.4\n")

    assert _format_phase(folder, tmp_path / "Documents").state == doc_status.DONE


def test_readme_beside_the_versioned_final_completes_format(tmp_path: Path) -> None:
    delivery = tmp_path / "entrega"
    delivery.mkdir()
    folder = _with_delivery_dir(_course_report(tmp_path / "wf"), delivery)
    (delivery / f"{_config(folder).document_slug}-v001.pdf").write_bytes(b"%PDF-1.4\n")
    (delivery / "README.md").write_text("Aquí va el informe entregado en PDF.\n", encoding="utf-8")

    assert _format_phase(folder, tmp_path / "Documents").state == doc_status.DONE


def test_readme_plus_another_foreign_file_still_blocks_format(tmp_path: Path) -> None:
    delivery = tmp_path / "entrega"
    delivery.mkdir()
    folder = _with_delivery_dir(_course_report(tmp_path / "wf"), delivery)
    (delivery / "README.md").write_text("x", encoding="utf-8")
    (delivery / "borrador.docx").write_bytes(b"x")

    phase = _format_phase(folder, tmp_path / "Documents")

    assert phase.state == doc_status.PENDING
    assert phase.detail.startswith("delivery folder unusable: La carpeta de entrega solo puede contener")


def test_missing_delivery_folder_completes_format(tmp_path: Path) -> None:
    folder = _with_delivery_dir(_course_report(tmp_path / "wf"), tmp_path / "todavia-no-existe")

    assert _format_phase(folder, tmp_path / "Documents").state == doc_status.DONE


def test_course_repo_rule_does_not_reopen_an_already_built_report(tmp_path: Path) -> None:
    documents = tmp_path / "Documents"
    _course_repo(documents)
    folder = _course_report(tmp_path / "wf")
    _pdf(folder)

    assert _format_phase(folder, documents).state == doc_status.DONE


def test_no_course_repo_keeps_the_previous_format_rule(tmp_path: Path) -> None:
    documents = tmp_path / "Documents"
    documents.mkdir()
    folder = _course_report(tmp_path / "wf")

    assert _format_phase(folder, documents).state == doc_status.DONE


def test_libre_report_is_not_held_for_a_course_folder(tmp_path: Path) -> None:
    """The course layout names practices (aa/ape); a libre document has no slot."""
    documents = tmp_path / "Documents"
    _course_repo(documents)
    folder = tmp_path / "wf"
    _report(folder, subject="Redes")
    _choose_format(folder, "libre", format_spec="documento sobrio")

    assert _format_phase(folder, documents).state == doc_status.DONE


def test_course_folder_pending_message_offers_the_manual_way_out(tmp_path: Path) -> None:
    documents = tmp_path / "Documents"
    _course_repo(documents)
    folder = _course_report(tmp_path / "wf")

    assert "or set delivery_dir by hand" in _format_phase(folder, documents).detail


def test_preview_built_before_approval_does_not_waive_the_course_folder(tmp_path: Path) -> None:
    """#72: the draft preview shares the final path and always predates approval."""
    documents = tmp_path / "Documents"
    _course_repo(documents)
    folder = _course_report(tmp_path / "wf")
    _approval(folder)
    _mtime(folder / "approval.yml", 2_000)
    _mtime(_pdf(folder), 1_000)

    phase = _format_phase(folder, documents)

    assert phase.state == doc_status.PENDING
    assert "delivery_dir" in phase.detail


def test_final_build_after_approval_keeps_its_course_folder_status(tmp_path: Path) -> None:
    documents = tmp_path / "Documents"
    _course_repo(documents)
    folder = _course_report(tmp_path / "wf")
    _approval(folder)
    _mtime(folder / "approval.yml", 1_000)
    _mtime(_pdf(folder), 2_000)

    assert _format_phase(folder, documents).state == doc_status.DONE


def test_final_build_with_the_same_mtime_as_approval_counts_as_final(tmp_path: Path) -> None:
    """#72 R3-mtime-tie-coverage: ``>=`` counts a tie as final, as _phase_generate does."""
    documents = tmp_path / "Documents"
    _course_repo(documents)
    folder = _course_report(tmp_path / "wf")
    _approval(folder)
    _mtime(folder / "approval.yml", 1_500)
    _mtime(_pdf(folder), 1_500)

    assert _format_phase(folder, documents).state == doc_status.DONE


def test_rewriting_approval_after_a_final_build_reopens_format_and_generate(tmp_path: Path) -> None:
    """#72 R3-mtime-marker-rewrite: a newer approval.yml turns the PDF back into a
    preview, so format waits for delivery_dir and generate asks for a rebuild."""
    documents = tmp_path / "Documents"
    _course_repo(documents)
    folder = _course_report(tmp_path / "wf")
    _approval(folder)
    _mtime(_pdf(folder), 1_000)
    _mtime(folder / "approval.yml", 2_000)

    assert _format_phase(folder, documents).state == doc_status.PENDING
    assert doc_status._phase_generate(folder, _config(folder), documents).state != doc_status.DONE


def test_delivery_folder_that_is_a_file_keeps_format_pending_without_crashing(tmp_path: Path) -> None:
    """Review R3-delivery-scan-exceptions: an OSError is a reason, never a crash."""
    target = tmp_path / "entrega.pdf"
    target.write_bytes(b"%PDF-1.4\n")
    folder = _with_delivery_dir(_course_report(tmp_path / "wf"), target)

    phase = _format_phase(folder, tmp_path / "Documents")
    status = doc_status.derive(folder, documents_root=tmp_path / "Documents")

    assert phase.state == doc_status.PENDING
    assert phase.detail.startswith("delivery folder unusable: ")
    assert str(target) in phase.detail
    assert "derivation_error" not in status.blocked_reasons


def test_extra_files_after_a_final_build_leave_format_done(tmp_path: Path) -> None:
    """Review R3-delivery-check-after-build: the up-front check never re-gates a built report.

    Deliver still refuses the folder; format and the phases after it keep their state.
    """
    delivery = tmp_path / "entrega"
    delivery.mkdir()
    folder = _with_delivery_dir(_course_report(tmp_path / "wf"), delivery)
    _approval(folder)
    _mtime(folder / "approval.yml", 1_000)
    _mtime(_pdf(folder), 2_000)
    (delivery / "notas.txt").write_text("ajeno", encoding="utf-8")

    assert _format_phase(folder, tmp_path / "Documents").state == doc_status.DONE
    deliver = doc_status._phase_deliver(folder, _config(folder), tmp_path / "Documents")
    assert deliver.state == doc_status.PENDING
    assert deliver.detail.startswith("delivery folder unusable: ")
