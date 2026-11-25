"""Orphan-heading check of the PDF layout validation (skill-visual-organization T11, S3).

A table cell whose text wraps can close a page with only a fragment of the
cell; pdftotext then shows a short capitalised line at the page foot that looks
like a heading. A fragment of a table cell is table content, never a heading.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import validate_report  # noqa: E402
from report_config import load_report_config  # noqa: E402

A4_PAGE_SIZE = "595.276 x 841.89 pts (A4)"


@pytest.fixture(autouse=True)
def _never_publish_outside_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    import importlib

    sandbox = tmp_path_factory.mktemp("global-outputs")
    for name in ("output_router", "report_config", "build_latex_report", "validate_report"):
        module = importlib.import_module(name)
        if hasattr(module, "GLOBAL_OUTPUTS"):
            monkeypatch.setattr(module, "GLOBAL_OUTPUTS", sandbox)


def _report(tmp_path: Path, body: str) -> Path:
    folder = tmp_path / "informe"
    folder.mkdir()
    (folder / "report.yml").write_text(
        "route: academic\ntype: technical_report\nbackend: latex\noutput: pdf\nformat: ape\n"
        "pdf: build/main.pdf\nmetadata:\n  title: \"Práctica\"\n  student: \"Ana\"\n"
        "  date: \"7 de agosto de 2026\"\n",
        encoding="utf-8",
    )
    (folder / "body.md").write_text(body, encoding="utf-8")
    (folder / "build").mkdir()
    (folder / "build" / "main.pdf").write_bytes(b"%PDF-1.5\n")
    return folder


def _validate(monkeypatch: pytest.MonkeyPatch, folder: Path, pages: list[str]) -> list[str]:
    monkeypatch.setattr(validate_report, "pdf_text_pages", lambda _pdf: pages)
    monkeypatch.setattr(validate_report, "pdfinfo", lambda _pdf: {"Pages": str(len(pages)), "Page size": A4_PAGE_SIZE})
    monkeypatch.setattr(
        validate_report, "run", lambda cmd: type("P", (), {"stdout": "image 1 0 0", "returncode": 0})()
    )
    return validate_report.pdf_layout_validation(load_report_config(folder)).errors


TABLE = (
    "# Resultados\n\nTabla 10. Resumen de los ataques.\n\n"
    "| Ataque | Efecto |\n|---|---|\n"
    "| Suplantación ARP | Desvía el tráfico de la víctima hacia el equipo atacante sin aviso |\n"
    "| **Desbordamiento** de la tabla `CAM` | El switch inunda todas las tramas |\n"
)


@pytest.mark.parametrize("fragment", ["Desvía el tráfico de la víctima", "Desbordamiento de la tabla CAM"])
def test_a_wrapped_table_cell_closing_a_page_is_not_an_orphan_heading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fragment: str
) -> None:
    folder = _report(tmp_path, TABLE)
    errors = _validate(monkeypatch, folder, [f"Tabla 10.\nSuplantación ARP\n{fragment}", "hacia el equipo\nTexto."])
    assert not any("huérfano" in e for e in errors), errors


def test_a_real_heading_closing_a_page_is_still_an_orphan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _report(tmp_path, TABLE)
    errors = _validate(monkeypatch, folder, ["Texto corriente.\nProcedimiento del laboratorio", "Contenido."])
    assert any("huérfano" in e for e in errors), errors


def test_a_whole_table_cell_closing_a_page_is_still_not_an_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _report(tmp_path, TABLE)
    errors = _validate(monkeypatch, folder, ["Tabla 10.\nSuplantación ARP", "Texto."])
    assert not any("huérfano" in e for e in errors), errors
