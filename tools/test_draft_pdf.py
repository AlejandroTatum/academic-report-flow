"""Tests for ``tools/draft_pdf.py``: the plain, template-free preapproval draft (S4).

The draft turns ``body.md`` into a simple PDF with no cover, logos or course
template, in a temporary directory outside the report and delivery folders, and
records the ``body.md`` sha256 so ``doc_status`` still detects a stale preview.
The LaTeX compiler is replaced by a fake that writes a PDF and keeps the ``.tex``
it was handed, so the tests need no TeX engine.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import approval_marker
import approval_packet
import build_latex_report
import doc_status
import draft_pdf
import pdf_viewer
from conftest import _body, _config, _report, _sources_bib

AA_BODY = "# Informe\n\nTexto con una cita [@key1] y la ecuacion $x^2$.\n\n![Grafico](figures/g.png)\n"


@pytest.fixture(autouse=True)
def isolated_drafts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    drafts = tmp_path / "system-tmp"
    monkeypatch.setenv(approval_marker.DRAFT_DIR_ENV, str(drafts))
    return drafts


@pytest.fixture
def compiled(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Replace the LaTeX engine: write a PDF and keep the ``.tex`` that was compiled."""
    seen: dict[str, str] = {}

    def fake_compile(config) -> None:
        seen["tex"] = config.tex_path.read_text(encoding="utf-8")
        seen["tex_path"] = str(config.tex_path)
        config.pdf_path.parent.mkdir(parents=True, exist_ok=True)
        config.pdf_path.write_bytes(b"%PDF-1.4\n%%EOF\n")

    monkeypatch.setattr(draft_pdf, "compile_latex", fake_compile)
    return seen


def _aa_folder(tmp_path: Path) -> Path:
    """An AA report: full course metadata, UNL cover machinery, a delivery folder and sources."""
    folder = tmp_path / "wf"
    _report(folder)
    with (folder / "report.yml").open("a", encoding="utf-8") as stream:
        stream.write(
            f"format: aa\ndelivery_dir: {tmp_path / 'Documents' / 'entrega'}\n"
            "metadata:\n  title: Informe Redes\n  subject: Redes de Datos\n"
            "  teacher: Docente Prueba\n  student: Alejandro Padilla\n  date: 2026-11-05\n"
        )
    _sources_bib(folder)
    (folder / "figures").mkdir()
    (folder / "figures" / "g.png").write_bytes(b"\x89PNG\r\n")
    _body(folder, AA_BODY)
    return folder


def _snapshot(folder: Path) -> set[str]:
    return {str(p.relative_to(folder)) for p in folder.rglob("*")}


def test_draft_uses_the_plain_template_without_cover_or_logos(tmp_path: Path, compiled: dict[str, str]) -> None:
    folder = _aa_folder(tmp_path)

    draft_pdf.render_draft(folder)

    assert "Non-institutional (plain) report template" in compiled["tex"]
    # TeX comments carry template placeholders; only typeset lines can reach the page.
    tex = "\n".join(line for line in compiled["tex"].splitlines() if not line.lstrip().startswith("%"))
    for institutional in (
        build_latex_report.LOGO_FILENAME,
        build_latex_report.BACKGROUND_FILENAME,
        "Universidad Nacional de Loja",
        "Docente Prueba",
        "Redes de Datos",
    ):
        assert institutional not in tex
    assert "Informe Redes" in tex and "x^2" in tex and r"\cite{key1}" in tex


def test_draft_is_written_outside_the_report_and_delivery_folders(
    tmp_path: Path, compiled: dict[str, str], isolated_drafts: Path
) -> None:
    folder = _aa_folder(tmp_path)
    config = _config(folder)
    before = _snapshot(folder)

    pdf = draft_pdf.render_draft(folder)

    assert pdf.is_file()
    assert pdf == approval_marker.draft_preview_path(folder)
    assert isolated_drafts in pdf.parents
    assert folder.resolve() not in pdf.resolve().parents
    assert config.delivery_folder().resolve() not in pdf.resolve().parents
    assert not config.delivery_folder().exists()
    assert _snapshot(folder) == before
    assert not config.pdf_path.exists()


def test_draft_copies_figures_next_to_its_own_build(tmp_path: Path, compiled: dict[str, str]) -> None:
    folder = _aa_folder(tmp_path)

    pdf = draft_pdf.render_draft(folder)

    assert str(folder) not in compiled["tex"]
    copied = list((pdf.parent / "figures").glob("*g.png"))
    assert len(copied) == 1 and copied[0].read_bytes() == b"\x89PNG\r\n"


def test_draft_prints_the_bibliography_from_sources_bib(tmp_path: Path, compiled: dict[str, str]) -> None:
    folder = _aa_folder(tmp_path)

    pdf = draft_pdf.render_draft(folder)

    assert r"\printbibliography" in compiled["tex"]
    assert (pdf.parent / "sources.bib").is_file()


def test_draft_records_the_body_hash_and_goes_stale_after_an_edit(tmp_path: Path, compiled: dict[str, str]) -> None:
    folder = _aa_folder(tmp_path)
    pdf = draft_pdf.render_draft(folder)

    record = approval_marker.draft_record_path(pdf)
    assert record.read_text(encoding="utf-8").strip() == approval_marker.sha256_file(folder / "body.md")
    assert approval_marker.draft_preview_is_fresh(folder)

    _body(folder, AA_BODY + "\nOtro parrafo.\n")

    assert not approval_marker.draft_preview_is_fresh(folder)


def test_failed_compile_leaves_no_fresh_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _aa_folder(tmp_path)
    pdf = approval_marker.draft_preview_path(folder)
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-old")
    approval_marker.write_draft_record(pdf, folder / "body.md")
    assert approval_marker.draft_preview_is_fresh(folder)

    def broken(config) -> None:
        raise SystemExit("latex failed")

    monkeypatch.setattr(draft_pdf, "compile_latex", broken)
    with pytest.raises(SystemExit):
        draft_pdf.render_draft(folder)

    assert not approval_marker.draft_preview_is_fresh(folder)


def test_doc_status_asks_for_the_draft_until_it_is_fresh(tmp_path: Path, compiled: dict[str, str]) -> None:
    folder = _aa_folder(tmp_path)

    stale = doc_status._guidance("approval", folder)
    assert "rebuild the draft PDF" in stale and "draft_pdf.py" in stale
    assert "--no-approval-check" not in stale

    draft_pdf.render_draft(folder)
    fresh = doc_status._guidance("approval", folder)
    assert "rebuild the draft PDF" not in fresh
    assert str(approval_marker.draft_preview_path(folder)) in fresh

    _body(folder, AA_BODY + "\nEditado.\n")
    assert "rebuild the draft PDF" in doc_status._guidance("approval", folder)


def test_approval_packet_links_and_opens_the_draft(
    tmp_path: Path, compiled: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _aa_folder(tmp_path)
    pdf = draft_pdf.render_draft(folder)
    opened: list[Path] = []
    monkeypatch.setattr(pdf_viewer, "open_pdf", lambda path: opened.append(Path(path)))

    text = approval_packet.render(folder)
    assert f"- Draft PDF: [{pdf.name}]({pdf.resolve().as_uri()})" in text
    assert "STALE" not in text

    assert approval_packet.main([str(folder), "--open"]) == 0
    assert opened == [pdf]

    _body(folder, AA_BODY + "\nEditado.\n")
    opened.clear()
    assert "STALE: rebuild the draft with" in approval_packet.render(folder)
    approval_packet.main([str(folder), "--open"])
    assert opened == []


def test_cli_opens_the_draft_unless_no_open(
    tmp_path: Path, compiled: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _aa_folder(tmp_path)
    opened: list[Path] = []
    monkeypatch.setattr(pdf_viewer, "open_pdf", lambda path: opened.append(Path(path)))

    assert draft_pdf.main([str(folder), "--no-open"]) == 0
    assert opened == []

    assert draft_pdf.main([str(folder)]) == 0
    assert opened == [approval_marker.draft_preview_path(folder)]


def test_draft_refuses_a_folder_without_body(tmp_path: Path, compiled: dict[str, str]) -> None:
    folder = tmp_path / "wf"
    _report(folder)

    with pytest.raises(SystemExit):
        draft_pdf.render_draft(folder)


def _uncited_folder(tmp_path: Path, *, uncited: bool) -> Path:
    """An academic report whose body cites nothing and whose .bib holds one @misc entry."""
    folder = tmp_path / "wf"
    _report(folder)
    with (folder / "report.yml").open("a", encoding="utf-8") as stream:
        stream.write("metadata:\n  title: Informe Simulacion\n  student: Alejandro Padilla\n  date: 2026-11-05\n")
        if uncited:
            stream.write("uncited_bibliography: true\n")
    (folder / "sources.bib").write_text('@misc{slides5, title = "Diapositivas semana 5"}\n', encoding="utf-8")
    _body(folder, "# Informe\n\nTexto sin ninguna cita.\n")
    return folder


def test_draft_prints_the_whole_bibliography_of_an_uncited_bibliography_report(
    tmp_path: Path, compiled: dict[str, str]
) -> None:
    folder = _uncited_folder(tmp_path, uncited=True)

    pdf = draft_pdf.render_draft(folder)

    assert pdf.is_file()
    assert r"\nocite{*}" in compiled["tex"] and r"\printbibliography" in compiled["tex"]
    assert "Non-institutional (plain) report template" in compiled["tex"]
    assert "slides5" in (pdf.parent / "sources.bib").read_text(encoding="utf-8")
    # The report itself stays strict: the draft's leniency must not leak into its config.
    assert _config(folder).uncited_bibliography is True


def test_draft_without_uncited_bibliography_omits_the_bibliography_when_nothing_is_cited(
    tmp_path: Path, compiled: dict[str, str]
) -> None:
    folder = _uncited_folder(tmp_path, uncited=False)

    draft_pdf.render_draft(folder)

    assert r"\nocite" not in compiled["tex"]
    assert "Bibliography omitted" in compiled["tex"]
    assert r"\printbibliography" not in "\n".join(
        line for line in compiled["tex"].splitlines() if not line.lstrip().startswith("%")
    )
