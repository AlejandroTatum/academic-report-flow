"""Typeset phase (issue #96, odd/tasks/plain-text-draft.md S4-S6).

After approval the plain-text ``body.md`` is formatted only in
``body.typeset.md``, bound to the approved bytes by ``typeset.yml``. Builds
render the typeset body while that binding is current; approvals recorded
before this change need no typeset.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

import approval_marker
import build_report_auto
import doc_status
import typeset
from conftest import DEFAULT_BODY, _approval, _choose_format, _config, _mtime, _pdf, _report, _sources_bib
from report_config import ReportConfig, read_yaml

T0 = 1_700_000_000.0
FORMATTED = "# Informe\n\nCuerpo del documento con fuentes [@key1], [@key2], [@key3], [@key4] y [@key5]; $e_a$.\n"


def _approved(tmp_path: Path, body: str = DEFAULT_BODY) -> Path:
    """A work folder whose current body.md was approved under the new contract."""
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    (folder / "body.md").write_text(body, encoding="utf-8")
    approval_marker.record_approval(folder, "Ana")
    return folder


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check(folder: Path) -> dict[str, dict]:
    return {item["check"]: item for item in typeset.check_results(folder)}


def test_record_approval_writes_typeset_required(tmp_path: Path) -> None:
    folder = _approved(tmp_path)

    assert read_yaml(folder / "approval.yml")["typeset"] == "required"
    assert approval_marker.approval_state(folder).state == "current"


def test_bind_refuses_missing_body_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    before = sorted(p.name for p in folder.iterdir())

    assert typeset.main(["bind", str(folder)]) == 1

    err = capsys.readouterr().err
    assert "typeset not bound:" in err and "body.md" in err
    assert sorted(p.name for p in folder.iterdir()) == before


def test_bind_copies_the_approved_body_and_records_its_hash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _approved(tmp_path)

    assert typeset.main(["bind", str(folder)]) == 0

    assert (folder / "body.typeset.md").read_text(encoding="utf-8") == DEFAULT_BODY
    binding = read_yaml(folder / "typeset.yml")
    assert binding["schema"] == "academic.typeset/v1"
    assert binding["body_sha256"] == _sha(folder / "body.md")
    assert f"bound {folder / 'body.typeset.md'} to body.md" in capsys.readouterr().out


def test_bind_keeps_existing_typeset_text_and_rebinds(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    (folder / "body.typeset.md").write_text(FORMATTED, encoding="utf-8")

    assert typeset.main(["bind", str(folder)]) == 0

    assert (folder / "body.typeset.md").read_text(encoding="utf-8") == FORMATTED
    assert read_yaml(folder / "typeset.yml")["body_sha256"] == _sha(folder / "body.md")


def test_check_passes_a_bound_formatted_body(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _approved(tmp_path)
    (folder / "body.typeset.md").write_text(FORMATTED, encoding="utf-8")
    typeset.bind(folder)

    assert typeset.main(["check", str(folder)]) == 0
    assert all(item["ok"] for item in typeset.check_results(folder))
    assert "[ok] citations_match" in capsys.readouterr().out


def test_check_fails_when_body_changed_since_bind(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    typeset.bind(folder)
    (folder / "body.md").write_text(DEFAULT_BODY + "\nOtra linea.\n", encoding="utf-8")

    check = _check(folder)["binding"]

    assert check["ok"] is False
    assert "body.md changed since typeset" in check["detail"]


def test_check_applies_rendering_rules_to_the_typeset_body(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    (folder / "body.typeset.md").write_text(DEFAULT_BODY + "\nVelocidad 3 m/s\u00b2.\n", encoding="utf-8")
    typeset.bind(folder)

    check = _check(folder)["body_format"]

    assert check["ok"] is False and "line 5" in check["detail"] and "m/s$^2$" in check["detail"]


def test_check_requires_the_same_citations(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    (folder / "body.typeset.md").write_text(
        "# Informe\n\nCuerpo con [@key1], [@key2], [@key3], [@key4] y [@nueva].\n", encoding="utf-8"
    )
    typeset.bind(folder)

    check = _check(folder)["citations_match"]

    assert check["ok"] is False
    assert "missing: key5" in check["detail"] and "added: nueva" in check["detail"]


def test_check_enforces_fixed_format_headings_in_the_typeset_body(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    _choose_format(folder, "ape")
    typeset.bind(folder)

    check = _check(folder)["ape_structure"]

    assert check["ok"] is False


def test_check_has_no_fixed_headings_check_for_the_free_ieee_essay(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    _choose_format(folder, "ieee")
    (folder / "body.typeset.md").write_text(
        "# Resumen\n\nTexto.\n\n# Un título libre\n\nTexto con [@key1].\n", encoding="utf-8"
    )
    typeset.bind(folder)

    checks = _check(folder)

    assert not any(name.endswith("_structure") for name in checks)
    assert "citations_match" in checks


def _ape_typeset(tmp_path: Path, titles: tuple[str, ...]) -> Path:
    folder = _approved(tmp_path)
    _choose_format(folder, "ape")
    (folder / "body.typeset.md").write_text(
        "".join(f"# {title}\n\nTexto con [@key1].\n\n" for title in titles), encoding="utf-8"
    )
    typeset.bind(folder)
    return folder


def test_check_names_the_expected_ape_heading_when_a_title_is_wrong(tmp_path: Path) -> None:
    from validate_report import APE_BODY_HEADINGS

    titles = tuple("Materiales y Herramientas" if t.startswith("Materiales") else t for t in APE_BODY_HEADINGS)

    check = _check(_ape_typeset(tmp_path, titles))["ape_structure"]

    assert check["ok"] is False
    assert "Materiales, Reactivos, Equipos y Herramientas" in check["detail"]


def test_check_passes_the_correct_ape_headings(tmp_path: Path) -> None:
    from validate_report import APE_BODY_HEADINGS

    assert _check(_ape_typeset(tmp_path, APE_BODY_HEADINGS))["ape_structure"]["ok"] is True


def test_body_path_resolves_to_a_current_typeset_body(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    (folder / "body.typeset.md").write_text(FORMATTED, encoding="utf-8")
    typeset.bind(folder)

    assert _config(folder).body_path == folder / "body.typeset.md"

    (folder / "body.md").write_text(DEFAULT_BODY + "\nCambio.\n", encoding="utf-8")
    assert _config(folder).body_path == folder / "body.md"


def test_explicit_body_key_still_wins(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    typeset.bind(folder)

    config = ReportConfig(folder=folder, raw={**read_yaml(folder / "report.yml"), "body": "otro.md"})

    assert config.body_path == folder / "otro.md"


def test_phase_order_puts_typeset_between_format_and_generate() -> None:
    phases = doc_status.PHASES
    assert phases.index("format") + 1 == phases.index("typeset") == phases.index("generate") - 1


def test_phase_typeset_legacy_approval_is_done(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _approval(folder)

    phase = doc_status._phase_typeset(folder, _config(folder), None)

    assert phase.state == doc_status.DONE
    assert "legacy approval" in phase.detail


def test_phase_typeset_pending_until_bound_then_done(tmp_path: Path) -> None:
    folder = _approved(tmp_path)

    pending = doc_status._phase_typeset(folder, _config(folder), None)
    assert pending.state == doc_status.PENDING
    assert pending.detail == "body.typeset.md missing"
    guidance = doc_status._guidance("typeset", folder)
    assert "typeset.py" in guidance and "bind" in guidance and "never in" in guidance

    typeset.bind(folder)
    done = doc_status._phase_typeset(folder, _config(folder), None)
    assert done.state == doc_status.DONE


def test_phase_typeset_pending_with_failures(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    typeset.bind(folder)
    (folder / "body.md").write_text(DEFAULT_BODY + "\nCambio.\n", encoding="utf-8")

    phase = doc_status._phase_typeset(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert "binding: body.md changed since typeset" in phase.detail


def test_generate_pending_when_typeset_is_newer_than_the_pdf(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    typeset.bind(folder)
    _mtime(folder / "report.yml", T0)
    _mtime(folder / "approval.yml", T0 + 60)
    _pdf(folder, mtime=T0 + 120)
    _mtime(folder / "body.typeset.md", T0 + 180)

    phase = doc_status._phase_generate(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert "older than body.typeset.md" in phase.detail


def test_final_build_refuses_without_a_current_typeset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _approved(tmp_path)
    monkeypatch.setattr(sys, "argv", ["build_report_auto.py", str(folder)])
    monkeypatch.setattr(build_report_auto, "build_with_records", lambda *a: pytest.fail("built"))

    with pytest.raises(SystemExit) as exc:
        build_report_auto.main()

    assert "TYPESET REQUIRED" in str(exc.value)
    assert "body.typeset.md missing" in str(exc.value)


def test_build_gate_open_for_legacy_and_bound_typesets(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    _report(legacy)
    _approval(legacy)
    assert typeset.build_gate(legacy) is None

    folder = _approved(tmp_path)
    typeset.bind(folder)
    assert typeset.build_gate(folder) is None


PREVIEW_LINE = (
    "PREVIEW FINDINGS: el borrador es texto plano; el formato se corrige en "
    "body.typeset.md después de la aprobación, nunca en body.md."
)


class _Validation:
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        self.warnings: list[str] = []


def _run_build(
    folder: Path,
    monkeypatch: pytest.MonkeyPatch,
    flags: list[str],
    errors: list[str],
    build_error: BaseException | None = None,
) -> None:
    config = _config(folder)
    monkeypatch.setattr(sys, "argv", ["build_report_auto.py", str(folder), *flags])
    monkeypatch.setattr(build_report_auto, "load_report_config", lambda _f: config)
    monkeypatch.setattr(build_report_auto, "validate", lambda _c: _Validation(errors))
    monkeypatch.setattr(build_report_auto, "sha256_file", lambda _p: "h")

    def fake_build(_config: ReportConfig, _args: object) -> None:
        if build_error:
            raise build_error

    monkeypatch.setattr(build_report_auto, "build_backend", fake_build)
    build_report_auto.main()


def test_preview_build_reports_validation_errors_as_findings_and_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    (folder / "body.md").write_text(DEFAULT_BODY, encoding="utf-8")
    before = (folder / "body.md").read_bytes()

    _run_build(folder, monkeypatch, ["--no-approval-check"], ["La tabla 1 no cabe", "Figura sin pie"])

    out = capsys.readouterr().out
    assert PREVIEW_LINE in out.splitlines()
    assert "- La tabla 1 no cabe" in out
    assert "- Figura sin pie" in out
    assert "VALIDATION FAILED" not in out
    assert (folder / "body.md").read_bytes() == before


def test_preview_build_failure_still_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    (folder / "body.md").write_text(DEFAULT_BODY, encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        _run_build(
            folder, monkeypatch, ["--no-approval-check"], ["x"], build_error=SystemExit("latex failed")
        )

    assert str(exc.value) == "latex failed"


def test_final_build_validation_errors_warn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """warn-only-gates S2: final-build validation errors warn on stderr, never stop the build."""
    folder = _approved(tmp_path)
    typeset.bind(folder)

    _run_build(folder, monkeypatch, [], ["La tabla 1 no cabe"])

    captured = capsys.readouterr()
    assert captured.err.startswith("warning: VALIDATION FAILED:\n- La tabla 1 no cabe")
    assert PREVIEW_LINE not in captured.out


def test_approval_guidance_is_content_review_not_layout_repair() -> None:
    text = doc_status._GUIDANCE["approval"]

    assert "fix layout defects" not in text
    assert "content review" in text
    assert "body.typeset.md" in text


# issue #98: a rebind proves the post-approval edit reached body.typeset.md.
EDITED = DEFAULT_BODY.replace("Cuerpo del documento", "Cuerpo revisado del documento")


def _bound_then_edited(tmp_path: Path, edited: str = EDITED) -> Path:
    folder = _approved(tmp_path)
    (folder / "body.typeset.md").write_text(FORMATTED, encoding="utf-8")
    typeset.bind(folder)
    (folder / "body.md").write_text(edited, encoding="utf-8")
    assert approval_marker.approval_state(folder).state == "carried"
    return folder


def _files(folder: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir()) if p.is_file()}


def test_bind_records_a_snapshot_of_the_bound_body(tmp_path: Path) -> None:
    folder = _approved(tmp_path)

    typeset.bind(folder)

    assert (folder / "typeset-source.md").read_bytes() == (folder / "body.md").read_bytes()


def test_rebind_refuses_while_inserted_words_are_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _bound_then_edited(tmp_path)
    before = _files(folder)

    assert typeset.main(["bind", str(folder)]) == 1

    err = capsys.readouterr().err
    assert "typeset not bound: the body.md edit is not in body.typeset.md (missing: «revisado»)" in err
    assert _files(folder) == before


def test_rebind_refuses_while_removed_text_remains(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _bound_then_edited(tmp_path, DEFAULT_BODY.replace("Cuerpo del documento", "Cuerpo documento"))
    before = _files(folder)

    assert typeset.main(["bind", str(folder)]) == 1

    err = capsys.readouterr().err
    assert "typeset not bound: the body.md edit is not in body.typeset.md (still present: «Cuerpo del documento»)" in err
    assert _files(folder) == before


def test_rebind_accepts_the_edit_applied_in_the_typeset_body(tmp_path: Path) -> None:
    folder = _bound_then_edited(tmp_path)
    (folder / "body.typeset.md").write_text(
        FORMATTED.replace("Cuerpo del documento", "Cuerpo **revisado** del documento"), encoding="utf-8"
    )

    assert typeset.main(["bind", str(folder)]) == 0

    assert read_yaml(folder / "typeset.yml")["body_sha256"] == _sha(folder / "body.md")
    assert (folder / "typeset-source.md").read_bytes() == (folder / "body.md").read_bytes()
    assert typeset.main(["check", str(folder)]) == 0


# issue #98: a typeset body the build would render is always checked, legacy or not.
def test_build_gate_checks_a_bound_typeset_on_a_legacy_report(tmp_path: Path) -> None:
    folder = tmp_path / "legacy"
    _report(folder)
    _sources_bib(folder)
    _approval(folder)
    (folder / "body.typeset.md").write_text("## Informe\n\nTexto [@key1].\n", encoding="utf-8")
    typeset.bind(folder)
    _gate(folder, "block")

    gate = typeset.build_gate(folder)
    assert gate is not None and "body_format" in gate and "citations_match" in gate
    phase = doc_status._phase_typeset(folder, _config(folder), None)
    assert phase.state == doc_status.PENDING and "body_format" in phase.detail


# odd/tasks/skill-visual-organization.md S3: no empty, ragged or split cells.
def test_check_fails_on_empty_ragged_and_split_table_cells(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    (folder / "body.typeset.md").write_text(
        "# Informe\n\n"
        "| Clase | | Máscara |\n"
        "|---|---|---|\n"
        "| A | 1 a 126 | 255.0.0.0 |\n"
        "| B |  | 255.255.0.0 |\n"
        "| C | 192 a 223 |\n"
        "| D | 224 a 239 | sin máscara | multicast |\n"
        "| E | 240 a 255 | `a | b` \\| c |\n",
        encoding="utf-8",
    )
    typeset.bind(folder)

    check = _check(folder)["table_cells"]

    assert check["ok"] is False
    assert check["detail"] == (
        "line 3: empty header cell in column 2; "
        "line 6: empty cell in column 2 (write — if nothing applies); "
        "line 7: 2 cells, the header has 3 (ragged row); "
        "line 8: 4 cells, the header has 3 (a stray ';' or '|' split a cell?); "
        "line 9: 4 cells, the header has 3 (a stray ';' or '|' split a cell?)"
    )


def test_check_passes_full_tables_and_keeps_citations_in_one_cell(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    (folder / "body.md").write_text(
        "# Informe\n\nTabla 1. Sensores (equipo; tensión; fuente).\n\n"
        "- Sensor; 3,3 V; ver [@key1; @key2]\n- Motor; 5 V; ver [@key3; @key4; @key5]\n",
        encoding="utf-8",
    )
    assert typeset.main(["auto", str(folder)]) == 0

    checks = _check(folder)

    assert checks["table_cells"] == {"check": "table_cells", "ok": True, "detail": "no empty, ragged or split cells"}
    assert checks["citations_match"]["ok"]
    assert "| Sensor | 3,3 V | ver [@key1; @key2] |" in (folder / "body.typeset.md").read_text(encoding="utf-8")


# S5: no literal 'Figura:' line or figure path left as text.
def test_check_fails_on_a_leftover_figura_line_or_figure_path(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    (folder / "body.typeset.md").write_text(
        "# Informe\n\n"
        "Figura: Partes de una dirección IPv6 y su forma abreviada (figures/diag-03-ipv6-estructura.png) "
        "La Tabla 8 resume los tipos de direcciones.\n\n"
        "Ver la topología (figures/pt-01.png) arriba.\n\n"
        "![Bien](figures/ok.png)\n\n"
        "```\n"
        "Figura: en código (figures/code.png)\n"
        "```\n",
        encoding="utf-8",
    )
    typeset.bind(folder)

    check = _check(folder)["figure_leftovers"]

    assert check["ok"] is False
    assert check["detail"] == (
        "line 3: literal 'Figura:' text: write it as ![caption](path) on its own line; "
        "line 3: figure path '(figures/diag-03-ipv6-estructura.png)' outside an image; "
        "line 5: figure path '(figures/pt-01.png)' outside an image"
    )


def test_check_passes_images_and_prose_that_mentions_figures(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    (folder / "body.typeset.md").write_text(
        "# Informe\n\nLa figura muestra el montaje (Figura 2).\n\n![Montaje](figures/montaje.png){width=70%}\n"
        "Fuente <https://x.example/figures/a.png>.\n",
        encoding="utf-8",
    )
    typeset.bind(folder)

    assert _check(folder)["figure_leftovers"] == {
        "check": "figure_leftovers",
        "ok": True,
        "detail": "every figure is an image",
    }


# odd/tasks/skill-visual-organization.md S7: report.yml typeset_gate decides
# whether failing typeset checks stop the build (block) or only warn (default).


def _gate(folder: Path, value: str) -> None:
    with (folder / "report.yml").open("a", encoding="utf-8") as handle:
        handle.write(f"typeset_gate: {value}\n")


def _failing_typeset(tmp_path: Path, gate: str | None) -> Path:
    folder = tmp_path / "legacy"
    _report(folder)
    _sources_bib(folder)
    _approval(folder)
    (folder / "body.typeset.md").write_text("## Informe\n\nTexto [@key1].\n", encoding="utf-8")
    typeset.bind(folder)
    if gate is not None:
        _gate(folder, gate)
    return folder


@pytest.mark.parametrize("gate", [None, "warn"])
def test_build_gate_warn_lets_the_build_run_and_prints_the_failures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], gate: str | None
) -> None:
    folder = _failing_typeset(tmp_path, gate)

    assert typeset.build_gate(folder) is None

    err = capsys.readouterr().err
    assert "typeset warning" in err and "body_format" in err and "citations_match" in err
    assert "typeset_gate: block" in err


def test_build_gate_block_stops_the_build_and_prints_no_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _failing_typeset(tmp_path, "block")

    gate = typeset.build_gate(folder)

    assert gate is not None and "body_format" in gate and "citations_match" in gate
    assert "typeset warning" not in capsys.readouterr().err


def test_build_gate_warn_still_blocks_a_stale_binding(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    typeset.bind(folder)
    _gate(folder, "warn")
    (folder / "body.md").write_text(DEFAULT_BODY + "\nCambio.\n", encoding="utf-8")

    gate = typeset.build_gate(folder)

    assert gate is not None and "binding" in gate


@pytest.mark.parametrize("gate", [None, "warn"])
def test_phase_typeset_warn_is_done_with_warnings(tmp_path: Path, gate: str | None) -> None:
    folder = _failing_typeset(tmp_path, gate)

    phase = doc_status._phase_typeset(folder, _config(folder), None)

    assert phase.state == doc_status.DONE
    assert "warning: typeset_check: body_format:" in phase.detail
    assert "warning: typeset_check: citations_match:" in phase.detail


def test_phase_typeset_block_stays_pending(tmp_path: Path) -> None:
    folder = _failing_typeset(tmp_path, "block")

    phase = doc_status._phase_typeset(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING
    assert "typeset check fails" in phase.detail and "warning" not in phase.detail


def test_phase_typeset_warn_keeps_a_stale_binding_pending(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    typeset.bind(folder)
    _gate(folder, "warn")
    (folder / "body.md").write_text(DEFAULT_BODY + "\nCambio.\n", encoding="utf-8")

    phase = doc_status._phase_typeset(folder, _config(folder), None)

    assert phase.state == doc_status.PENDING and "binding" in phase.detail


@pytest.mark.parametrize(("gate", "builds"), [("warn", True), ("block", False)])
def test_final_build_follows_the_typeset_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, gate: str, builds: bool
) -> None:
    folder = _failing_typeset(tmp_path, gate)
    built = []
    monkeypatch.setattr(sys, "argv", ["build_report_auto.py", str(folder), "--tex-only"])
    monkeypatch.setattr(build_report_auto, "build_with_records", lambda *a: built.append(a) or sys.exit(0))

    with pytest.raises(SystemExit) as exc:
        build_report_auto.main()

    if builds:
        assert built and exc.value.code == 0
    else:
        assert not built and "TYPESET REQUIRED" in str(exc.value) and "body_format" in str(exc.value)


# odd/tasks/skill-visual-organization.md S9: a bold term inside a sentence is
# fine; a line that is only bold still fails as a pseudo-heading.
def test_check_accepts_bold_terms_in_sentences_but_not_bold_only_lines(tmp_path: Path) -> None:
    folder = _approved(tmp_path)
    (folder / "body.typeset.md").write_text(
        "# Informe\n\nLa **dirección MAC** identifica la tarjeta y el **ARP** la resuelve.\n\n"
        "- Cada entrada **ARP** dura minutos.\n",
        encoding="utf-8",
    )
    typeset.bind(folder)
    assert _check(folder)["body_format"]["ok"]

    (folder / "body.typeset.md").write_text("# Informe\n\n**Dirección MAC**\n\nTexto.\n", encoding="utf-8")
    typeset.bind(folder)
    check = _check(folder)["body_format"]
    assert not check["ok"] and "bold-only line" in check["detail"]
