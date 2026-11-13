"""warn-only-gates L3: build/generation.yml never bypasses the approval check.

(a) A present but stale or malformed approval.yml always refuses, whatever
    build/generation.yml holds.
(b) Without approval.yml, a missing or not current generation record refuses
    with GENERATION_REFUSAL: it is then the integrity anchor, not a quality check.
(c) Without approval.yml, a current generation record delivers (the v1 path).
(d) A valid approval.yml next to a stale generation identity only warns.

Every case asserts the exit code, the stderr/stdout lines and the files written.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import approval_marker
import publish_pdf
from conftest import _approval, _final_review, _pdf, _report, _validation
from deliver_report import main

SLUG = "informe-de-laboratorio"
BODY = "# Informe\n\nCuerpo generado.\n"


def _folder(tmp_path: Path) -> tuple[Path, Path]:
    folder = tmp_path / "wf"
    _report(folder)
    (folder / "body.md").write_text(BODY, encoding="utf-8")
    pdf = _pdf(folder)
    _validation(folder, pdf=pdf)
    _final_review(folder, pdf=pdf)
    return folder, pdf


def _bogus_generation(folder: Path, text: str = "pdf_sha256: bogus\n") -> None:
    (folder / "build").mkdir(exist_ok=True)
    (folder / "build" / "generation.yml").write_text(text, encoding="utf-8")


def _current_generation(folder: Path, pdf: Path) -> None:
    approval_marker.write_generation_record(
        folder, pdf, approval_marker.generation_inputs(folder), approval_marker.sha256_file(pdf)
    )


def _stale_approval(folder: Path) -> None:
    _approval(folder, body=BODY, body_sha256="0" * 64)


def _malformed_approval(folder: Path) -> None:
    (folder / "approval.yml").write_text("schema: [unclosed\n", encoding="utf-8")


def _deliver(folder: Path, documents: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str], str]:
    code = main([str(folder), "--documents-root", str(documents)])
    captured = capsys.readouterr()
    return code, captured.err.splitlines(), captured.out


def _written(documents: Path) -> list[Path]:
    return sorted(documents.rglob("*.pdf")) if documents.exists() else []


def _assert_refused(code: int, err: list[str], out: str, documents: Path, fragment: str) -> None:
    assert code == 1
    assert not any(line.startswith("warning:") for line in err), err  # refuses before any warning
    assert err[0].startswith("DELIVERY REFUSED: ")
    assert fragment in err[0]
    assert out == ""
    assert _written(documents) == []


GENERATION_LINE = f"DELIVERY REFUSED: {publish_pdf.GENERATION_REFUSAL}"


# -- the three reproduced bypasses -------------------------------------------------


def test_stale_approval_with_bogus_generation_refuses(tmp_path: Path, capsys) -> None:
    folder, _ = _folder(tmp_path)
    _stale_approval(folder)
    _bogus_generation(folder)
    documents = tmp_path / "docs"
    code, err, out = _deliver(folder, documents, capsys)
    _assert_refused(code, err, out, documents, "La aprobación está obsoleta")


def test_malformed_approval_with_empty_generation_refuses(tmp_path: Path, capsys) -> None:
    folder, _ = _folder(tmp_path)
    _malformed_approval(folder)
    _bogus_generation(folder, "")
    documents = tmp_path / "docs"
    code, err, out = _deliver(folder, documents, capsys)
    _assert_refused(code, err, out, documents, "approval.yml es inválido")


def test_no_approval_with_empty_generation_refuses(tmp_path: Path, capsys) -> None:
    folder, _ = _folder(tmp_path)
    _bogus_generation(folder, "")
    documents = tmp_path / "docs"
    code, err, out = _deliver(folder, documents, capsys)
    _assert_refused(code, err, out, documents, publish_pdf.GENERATION_REFUSAL)
    assert err[0] == GENERATION_LINE


# -- (a) stale or malformed approval refuses even over a CURRENT generation record ------


@pytest.mark.parametrize(
    ("spoil", "fragment"),
    [(_stale_approval, "La aprobación está obsoleta"), (_malformed_approval, "approval.yml es inválido")],
)
def test_bad_approval_refuses_whatever_generation_holds(tmp_path: Path, capsys, spoil, fragment) -> None:
    folder, pdf = _folder(tmp_path)
    _current_generation(folder, pdf)
    spoil(folder)
    assert approval_marker.generation_record_current(folder, pdf)
    documents = tmp_path / "docs"
    code, err, out = _deliver(folder, documents, capsys)
    _assert_refused(code, err, out, documents, fragment)


# -- (b) no approval and a stale generation record refuses ----------------------------


def test_no_approval_with_stale_generation_refuses(tmp_path: Path, capsys) -> None:
    folder, pdf = _folder(tmp_path)
    _current_generation(folder, pdf)
    (folder / "body.md").write_text(BODY + "\nEditado.\n", encoding="utf-8")
    documents = tmp_path / "docs"
    code, err, out = _deliver(folder, documents, capsys)
    _assert_refused(code, err, out, documents, publish_pdf.GENERATION_REFUSAL)
    assert err[0] == GENERATION_LINE


# -- (c) no approval and a current generation record delivers -----------------------


def test_no_approval_with_current_generation_delivers(tmp_path: Path, capsys) -> None:
    folder, pdf = _folder(tmp_path)
    _current_generation(folder, pdf)
    documents = tmp_path / "docs"
    code, err, out = _deliver(folder, documents, capsys)
    assert code == 0
    assert not any(line.startswith("DELIVERY REFUSED") for line in err)
    assert not any("identidad del PDF generado" in line for line in err)
    assert out.startswith("PDF ENTREGADO")
    written = _written(documents)
    assert len(written) == 1 and written[0].name == f"{SLUG}-v001.pdf"
    assert written[0].read_bytes() == pdf.read_bytes()


# -- (d) valid approval and a stale generation identity only warns -----------------------


def test_valid_approval_with_stale_generation_warns_and_delivers(tmp_path: Path, capsys) -> None:
    folder, pdf = _folder(tmp_path)
    _approval(folder, body=BODY)
    _bogus_generation(folder)
    documents = tmp_path / "docs"
    code, err, out = _deliver(folder, documents, capsys)
    assert code == 0
    assert err == [
        "warning: Falta o está obsoleta la identidad del PDF generado y sus entradas; "
        "volvé a generar y validar antes de publicar. El PDF se entrega igual."
    ]
    assert out.startswith("PDF ENTREGADO CON ADVERTENCIAS")
    assert len(_written(documents)) == 1


# -- the publisher itself, with warn= -----------------------------------------------------


def _publish(folder: Path, pdf: Path, documents: Path):
    warnings: list = []
    publication = publish_pdf.publish_validated_pdf(
        pdf, "Tecnicos", SLUG, documents, work_folder=folder,
        warn=lambda code, message: warnings.append((code, message)),
    )
    return publication, warnings


@pytest.mark.parametrize("generation", ["", "pdf_sha256: bogus\n", None])
@pytest.mark.parametrize("spoil", [_stale_approval, _malformed_approval])
def test_publisher_bad_approval_raises_even_with_warn(tmp_path: Path, spoil, generation) -> None:
    folder, pdf = _folder(tmp_path)
    if generation is None:
        _current_generation(folder, pdf)
    else:
        _bogus_generation(folder, generation)
    spoil(folder)
    documents = tmp_path / "docs"
    with pytest.raises(publish_pdf.PublicationError, match="aprobación está obsoleta|approval.yml es inválido"):
        _publish(folder, pdf, documents)
    assert _written(documents) == []


@pytest.mark.parametrize("generation", ["", "pdf_sha256: bogus\n", "missing"])
def test_publisher_no_approval_without_current_generation_raises_even_with_warn(tmp_path: Path, generation) -> None:
    folder, pdf = _folder(tmp_path)
    if generation != "missing":
        _bogus_generation(folder, generation)
    documents = tmp_path / "docs"
    with pytest.raises(publish_pdf.PublicationError) as raised:
        _publish(folder, pdf, documents)
    assert str(raised.value) == publish_pdf.GENERATION_REFUSAL
    assert _written(documents) == []


def test_publisher_valid_approval_with_stale_generation_warns(tmp_path: Path) -> None:
    folder, pdf = _folder(tmp_path)
    _approval(folder, body=BODY)
    _bogus_generation(folder)
    documents = tmp_path / "docs"
    publication, warnings = _publish(folder, pdf, documents)
    assert warnings == [("generation_identity", publish_pdf.GENERATION_REFUSAL)]
    assert publication.path.read_bytes() == pdf.read_bytes()
