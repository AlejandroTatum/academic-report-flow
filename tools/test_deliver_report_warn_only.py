"""warn-only-gates S2: deliver_report.py warns on quality gaps and still delivers.

A stale or missing validation receipt, a missing or stale final review, an
unresolved rubric, an unmapped guide inventory, a missing generated identity and
a carried gate over an unrebuilt PDF print ``warning: <message>`` on stderr and
the PDF is delivered (exit 0). Nothing to deliver or nothing readable still
refuses (exit 1): a missing PDF, an invalid report.yml, an unparseable receipt
or final review, a missing declared bibliography, a stale or malformed approval.yml (the user's
explicit approve), and no approval.yml without a current generated identity
(test_deliver_report_approval_anchor.py covers L3).
"""
from __future__ import annotations

from pathlib import Path

import pytest

import approval_marker
from conftest import (
    _approval,
    _bibliography,
    _declare_bibliography_delivery,
    _final_review,
    _pdf,
    _report,
    _sha256,
    _validation,
)
from deliver_report import main

SLUG = "informe-de-laboratorio"


def _ready(tmp_path: Path) -> tuple[Path, Path]:
    folder = tmp_path / "wf"
    _report(folder)
    _approval(folder)
    pdf = _pdf(folder)
    _validation(folder, pdf=pdf)
    _final_review(folder, pdf=pdf)
    return folder, pdf


def _current_generation(folder: Path, pdf: Path) -> None:
    """A current v1 generated identity: without approval.yml it is the integrity anchor (L3)."""
    approval_marker.write_generation_record(
        folder, pdf, approval_marker.generation_inputs(folder), approval_marker.sha256_file(pdf)
    )


def _deliver(folder: Path, documents: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str], str]:
    code = main([str(folder), "--documents-root", str(documents)])
    captured = capsys.readouterr()
    return code, captured.err.splitlines(), captured.out


def _delivered(documents: Path) -> list[Path]:
    return sorted(documents.rglob(f"{SLUG}-v*.pdf"))


def _assert_warned_and_delivered(code: int, err: list[str], out: str, documents: Path, line: str) -> None:
    assert code == 0
    assert line in err
    assert not any(entry.startswith("DELIVERY REFUSED") for entry in err)
    assert "CON ADVERTENCIAS" in out
    assert len(_delivered(documents)) == 1


# -- downgraded refusals -----------------------------------------------------------


def test_missing_receipt_warns_and_delivers(tmp_path: Path, capsys) -> None:
    folder, _ = _ready(tmp_path)
    (folder / "validation.yml").unlink()
    documents = tmp_path / "docs"
    code, err, out = _deliver(folder, documents, capsys)
    _assert_warned_and_delivered(
        code, err, out, documents,
        f"warning: falta validation.yml en {folder}. Ejecutá primero la fase validate.",
    )


def test_failed_receipt_warns_and_delivers(tmp_path: Path, capsys) -> None:
    folder, pdf = _ready(tmp_path)
    _validation(folder, pdf=pdf, result="fail")
    documents = tmp_path / "docs"
    code, err, out = _deliver(folder, documents, capsys)
    _assert_warned_and_delivered(
        code, err, out, documents, "warning: validation.yml no registra result: pass (registró: fail)."
    )
    assert "gates otorgados: HUMAN_REVIEW;" in out  # a failed receipt grants no receipt gate


def test_stale_receipt_hash_warns_and_delivers(tmp_path: Path, capsys) -> None:
    folder, pdf = _ready(tmp_path)
    _validation(folder, pdf=pdf, artifact_sha256="0" * 64)
    documents = tmp_path / "docs"
    code, err, out = _deliver(folder, documents, capsys)
    _assert_warned_and_delivered(
        code, err, out, documents,
        f"warning: validation.yml artifact_sha256 no coincide con los bytes actuales de {pdf.name}; "
        "la evidencia está obsoleta. Volvé a validar.",
    )


def _pair(tmp_path: Path) -> tuple[Path, Path, Path]:
    folder = tmp_path / "wf"
    _report(folder)
    _approval(folder)
    pdf = _pdf(folder)
    bib = _bibliography(folder)
    _declare_bibliography_delivery(folder)
    _validation(folder, pdf=pdf, bibliography_sha256=_sha256(bib))
    _final_review(folder, pdf=pdf, bibliography=bib)
    return folder, pdf, bib


def test_receipt_without_bibliography_hash_warns_and_delivers(tmp_path: Path, capsys) -> None:
    folder, pdf, _ = _pair(tmp_path)
    _validation(folder, pdf=pdf, drop=("bibliography_sha256",))
    documents = tmp_path / "docs"
    code, err, out = _deliver(folder, documents, capsys)
    _assert_warned_and_delivered(
        code, err, out, documents,
        "warning: deliver_bibliography está activo pero validation.yml no registra bibliography_sha256; "
        "volvé a validar para vincular los bytes declarados.",
    )


def test_stale_bibliography_hash_warns_and_delivers(tmp_path: Path, capsys) -> None:
    folder, pdf, bib = _pair(tmp_path)
    _validation(folder, pdf=pdf, bibliography_sha256="0" * 64)
    documents = tmp_path / "docs"
    code, err, out = _deliver(folder, documents, capsys)
    _assert_warned_and_delivered(
        code, err, out, documents,
        f"warning: validation.yml bibliography_sha256 no coincide con los bytes actuales de {bib.name}; "
        "la evidencia está obsoleta. Volvé a validar.",
    )


def test_missing_final_review_warns_once_and_delivers(tmp_path: Path, capsys) -> None:
    folder, pdf = _ready(tmp_path)
    (folder / "final-review.yml").unlink()
    documents = tmp_path / "docs"
    code, err, out = _deliver(folder, documents, capsys)
    line = (
        f"warning: falta final-review.yml en {folder}: falta la revisión humana final "
        f"de {pdf.name}. Ejecutá primero la fase review; el PDF se entrega igual."
    )
    _assert_warned_and_delivered(code, err, out, documents, line)
    assert err == [line]  # the publisher's own final-review warning is not repeated
    assert "HUMAN_REVIEW" not in out.split("gates otorgados:")[1].split(";")[0]


def test_stale_final_review_warns_and_delivers(tmp_path: Path, capsys) -> None:
    folder, pdf = _ready(tmp_path)
    _final_review(folder, pdf=pdf, pdf_sha256="0" * 64)
    documents = tmp_path / "docs"
    code, err, out = _deliver(folder, documents, capsys)
    stale = [line for line in err if line.startswith("warning: final-review.yml no corresponde a los bytes actuales")]
    assert code == 0 and len(stale) == 1 and len(err) == 1
    assert len(_delivered(documents)) == 1


def test_stale_generated_identity_warns_and_delivers(tmp_path: Path, capsys) -> None:
    """Next to a valid approval.yml a stale generated identity only warns (L3 case d)."""
    folder = tmp_path / "wf"
    _report(folder)
    _approval(folder)
    pdf = _pdf(folder)
    _validation(folder, pdf=pdf)
    _final_review(folder, pdf=pdf)
    (folder / "build").mkdir(exist_ok=True)
    (folder / "build" / "generation.yml").write_text("pdf_sha256: stale\n", encoding="utf-8")
    documents = tmp_path / "docs"
    code, err, out = _deliver(folder, documents, capsys)
    _assert_warned_and_delivered(
        code, err, out, documents,
        "warning: Falta o está obsoleta la identidad del PDF generado y sus entradas; "
        "volvé a generar y validar antes de publicar. El PDF se entrega igual.",
    )


def test_delivered_warnings_never_say_nothing_is_published(tmp_path: Path, capsys) -> None:
    """A warning is printed while the PDF IS delivered, so it cannot claim the opposite."""
    folder = tmp_path / "wf"
    _report(folder)
    (folder / "body.md").write_text("# Informe\n\nCuerpo generado.\n", encoding="utf-8")
    pdf = _pdf(folder)
    _current_generation(folder, pdf)
    documents = tmp_path / "docs"
    code, err, out = _deliver(folder, documents, capsys)
    assert code == 0 and len(_delivered(documents)) == 1
    assert len(err) >= 3
    assert all(line.startswith("warning: ") for line in err)
    assert not any("no se publica nada" in line.lower() for line in err), err


def test_unmapped_inventory_warns_and_delivers(tmp_path: Path, capsys) -> None:
    import publish_pdf
    from test_doc_status_inventory import CRITERIA, verified_with_guide

    folder = verified_with_guide(tmp_path / "unmapped", CRITERIA)
    pdf = _pdf(folder)
    _validation(folder, pdf=pdf)
    _final_review(folder, pdf=pdf)
    _current_generation(folder, pdf)
    documents = tmp_path / "docs"
    code, err, out = _deliver(folder, documents, capsys)
    refusal = publish_pdf._content_refusal(folder)
    assert refusal.startswith("La guía tiene ítems sin criterio")
    assert refusal.endswith(". No se publica nada.")
    assert code == 0
    assert f"warning: {refusal.removesuffix('No se publica nada.')}El PDF se entrega igual." in err
    assert len(_delivered(documents)) == 1


def test_carried_gate_over_an_unrebuilt_pdf_warns_and_delivers(tmp_path: Path, capsys) -> None:
    import final_review_marker

    folder = tmp_path / "wf"
    _report(folder)
    (folder / "body.md").write_text("# Informe\n\nPreparado por Juan Perez.\n", encoding="utf-8")
    approval_marker.record_approval(folder, "Alejandro")
    pdf = _pdf(folder)
    approval_marker.write_draft_record(pdf, folder / "body.md")
    _validation(folder, pdf=pdf)
    final_review_marker.record_final_review(folder, "Alejandro", pdf)
    (folder / "body.md").write_text("# Informe\n\nPreparado por Ana Perez.\n", encoding="utf-8")
    documents = tmp_path / "docs"
    code, err, out = _deliver(folder, documents, capsys)
    _assert_warned_and_delivered(
        code, err, out, documents,
        "warning: Hubo una edición acotada de body.md y el PDF no se generó desde el body.md actual. "
        "Volvé a generar y validar el PDF antes de publicar; el PDF se entrega igual.",
    )


# -- kept hard refusals --------------------------------------------------------------


def _refused(folder: Path, documents: Path, capsys) -> str:
    code, err, _ = _deliver(folder, documents, capsys)
    assert code == 1
    assert err[0].startswith("DELIVERY REFUSED: ")
    assert not documents.exists() or not _delivered(documents)
    return "\n".join(err)


def test_missing_pdf_still_refuses(tmp_path: Path, capsys) -> None:
    folder, pdf = _ready(tmp_path)
    pdf.unlink()
    assert "falta el PDF final" in _refused(folder, tmp_path / "docs", capsys)


def test_invalid_report_yml_still_refuses(tmp_path: Path, capsys) -> None:
    folder, _ = _ready(tmp_path)
    (folder / "report.yml").unlink()
    assert "report.yml inválido" in _refused(folder, tmp_path / "docs", capsys)


def test_unparseable_receipt_still_refuses(tmp_path: Path, capsys) -> None:
    folder, _ = _ready(tmp_path)
    (folder / "validation.yml").write_text("result: [unclosed\n", encoding="utf-8")
    assert "validation.yml no es YAML válido" in _refused(folder, tmp_path / "docs", capsys)


def test_malformed_final_review_still_refuses(tmp_path: Path, capsys) -> None:
    folder, _ = _ready(tmp_path)
    (folder / "final-review.yml").write_text("pdf_sha256: [unclosed\n", encoding="utf-8")
    assert "final-review.yml es inválido" in _refused(folder, tmp_path / "docs", capsys)


def test_missing_declared_bibliography_still_refuses(tmp_path: Path, capsys) -> None:
    folder, _, bib = _pair(tmp_path)
    bib.unlink()
    _refused(folder, tmp_path / "docs", capsys)


def test_no_approval_and_no_generated_identity_still_refuses(tmp_path: Path, capsys) -> None:
    """Nothing vouches for the PDF: neither the user's approve nor a generated v1 identity."""
    folder = tmp_path / "wf"
    _report(folder)
    pdf = _pdf(folder)
    _validation(folder, pdf=pdf)
    _final_review(folder, pdf=pdf)
    message = _refused(folder, tmp_path / "docs", capsys)
    assert message.splitlines()[0] == (
        f"DELIVERY REFUSED: no hay approval.yml ni build/generation.yml en {folder}: falta la "
        "aprobación humana del cuerpo y la identidad del PDF generado. Aprobá body.md o generá "
        "el PDF con build_report_auto.py."
    )
    assert not (tmp_path / "docs").exists()


def test_stale_approval_still_refuses(tmp_path: Path, capsys) -> None:
    folder, _ = _ready(tmp_path)
    (folder / "body.md").write_text("edited after approval\n", encoding="utf-8")
    assert "aprobación está obsoleta" in _refused(folder, tmp_path / "docs", capsys)
