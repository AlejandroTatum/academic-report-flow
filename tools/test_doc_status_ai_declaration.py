"""The AI declaration is part of every format unless the user opts out."""
from __future__ import annotations

import shlex
import sys
from pathlib import Path

import pytest
import yaml

import doc_status
from conftest import (
    _approval,
    _body,
    _choose_format,
    _config,
    _final_review,
    _pdf,
    _report,
    _rubric,
    _sources_bib,
    _validation,
)

DECLARATION = (
    "ai_declaration:\n"
    "  title: Declaración de uso de IA generativa\n"
    "  format: markdown\n"
    "  text: |\n"
    "    | Herramienta | Uso |\n"
    "    |---|---|\n"
    "    | Claude | Redacción |\n"
    "ai_declaration_position: after_bibliography\n"
)


def _format_phase(folder: Path) -> doc_status.PhaseState:
    return doc_status._phase_format(folder, _config(folder), None)


def _folder(tmp_path: Path, extra: str = "") -> Path:
    folder = tmp_path / "wf"
    _report(folder)
    _choose_format(folder, "aa")
    if extra:
        report = folder / "report.yml"
        report.write_text(report.read_text(encoding="utf-8") + extra, encoding="utf-8")
    return folder


def test_missing_ai_declaration_keeps_format_pending_and_is_named(tmp_path: Path) -> None:
    phase = _format_phase(_folder(tmp_path))

    assert phase.state == doc_status.PENDING
    assert phase.detail == "missing format metadata: ai_declaration"


def test_ai_declaration_present_completes_format(tmp_path: Path) -> None:
    assert _format_phase(_folder(tmp_path, DECLARATION)).state == doc_status.DONE


def test_string_declaration_and_spanish_alias_count(tmp_path: Path) -> None:
    assert _format_phase(_folder(tmp_path, 'ai_declaration: "Se usó Claude."\n')).state == doc_status.DONE
    assert _format_phase(_folder(tmp_path / "b", 'declaracion_ia: "Se usó Claude."\n')).state == doc_status.DONE


def test_explicit_opt_out_does_not_block_format(tmp_path: Path) -> None:
    assert _format_phase(_folder(tmp_path, "ai_declaration: false\n")).state == doc_status.DONE


def test_empty_declaration_is_still_missing(tmp_path: Path) -> None:
    for name, value in (("empty", '""'), ("map", "{}"), ("null", "null")):
        phase = _format_phase(_folder(tmp_path / name, f"ai_declaration: {value}\n"))
        assert phase.state == doc_status.PENDING and "ai_declaration" in phase.detail


def test_missing_declaration_is_listed_with_the_other_missing_fields(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _choose_format(folder, "aa", output=None)

    phase = _format_phase(folder)

    assert phase.state == doc_status.PENDING
    assert phase.detail.endswith("output, ai_declaration")


def test_guidance_tells_the_agent_to_write_the_declaration(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    guidance = doc_status._guidance("format", folder, _config(folder))

    for needle in ("ai_declaration", "Tabla A", "Tabla B", "verbatim", "summary",
                   "format: markdown", "ai_declaration_position: after_bibliography",
                   "ai_declaration: false", "explicit"):
        assert needle in guidance, needle


def test_a_built_report_is_never_sent_back_to_format(tmp_path: Path) -> None:
    built = _folder(tmp_path / "built")
    _pdf(built)
    assert _format_phase(built).state == doc_status.DONE

    validated = _folder(tmp_path / "validated")
    _validation(validated, pdf=_pdf(validated))
    assert _format_phase(validated).state == doc_status.DONE

    reviewed = _folder(tmp_path / "reviewed")
    _final_review(reviewed, pdf=_pdf(reviewed))
    assert _format_phase(reviewed).state == doc_status.DONE


def test_a_preview_pdf_older_than_approval_does_not_waive_the_declaration(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    _pdf(folder)
    _approval(folder)
    import os
    pdf = _config(folder).pdf_path
    os.utime(pdf, (1, 1))

    assert _format_phase(folder).state == doc_status.PENDING


APPROVAL_NOTE = (
    "; ai_declaration is not part of this batch: after approval the format phase applies the "
    "course decision, or asks it once on its own"
)


def test_approval_batch_never_asks_the_user_for_the_declaration(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    suffix = doc_status._approval_format_suffix(folder, _config(folder), None)

    assert "still missing: ai_declaration" not in suffix
    assert suffix.endswith(APPROVAL_NOTE)
    assert "never ask whether to include it" not in suffix


@pytest.fixture
def content_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "content"
    root.mkdir()
    monkeypatch.setenv("REPORT_CONTENT_ROOT", str(root))
    return root


def _ask_clause(folder: Path, content_root: Path) -> str:
    command = shlex.join([sys.executable, str(doc_status.ROOT / "tools" / "course_memory.py"), str(folder)])
    return (
        "; when ai_declaration is missing and the course has no decision in "
        f"{content_root / 'academic-sources' / 'fisica' / 'feedback.yml'}, ask ONE ask_user_choice question "
        "with the options \"Incluir declaracion de IA (recomendado)\" first and \"Omitir\" second "
        "(show the first label with the accent on declaracion), record the answer with "
        f"{command} --ai-declaration include (or omit; that course is never asked again), then write it in "
        f"{folder / 'report.yml'}"
    )


def test_guidance_asks_once_when_neither_the_course_nor_report_yml_decides(tmp_path: Path, content_root: Path) -> None:
    folder = _folder(tmp_path)
    guidance = doc_status._guidance("format", folder, _config(folder))

    assert _ask_clause(folder, content_root) in guidance
    assert "it is not a question" not in guidance and "never ask whether" not in guidance
    assert guidance.isascii()
    assert doc_status.AI_DECLARATION_OPTIONS == ("Incluir declaración de IA (recomendado)", "Omitir")


@pytest.mark.parametrize("decision", ["include", "omit"])
def test_guidance_applies_a_recorded_course_decision_without_asking(
    tmp_path: Path, content_root: Path, decision: str
) -> None:
    course = content_root / "academic-sources" / "fisica"
    course.mkdir(parents=True)
    (course / "feedback.yml").write_text(
        yaml.safe_dump({"schema": "academic.course-feedback/v1", "ai_declaration": decision}), encoding="utf-8"
    )
    folder = _folder(tmp_path)
    guidance = doc_status._guidance("format", folder, _config(folder))

    assert (
        f"; when ai_declaration is missing, apply the course decision ai_declaration: {decision} "
        f"({course / 'feedback.yml'}) without asking: write it in {folder / 'report.yml'}"
    ) in guidance
    assert "Incluir declaracion de IA (recomendado)" not in guidance


def test_guidance_maps_include_and_omit_to_report_yml(tmp_path: Path, content_root: Path) -> None:
    folder = _folder(tmp_path)
    guidance = doc_status._guidance("format", folder, _config(folder))

    assert "include writes the declaration text as `ai_declaration: {format: markdown, text: ...}`" in guidance
    assert "omit writes `ai_declaration: false`" in guidance
