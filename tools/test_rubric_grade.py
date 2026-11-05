"""rubric_grade.py: the mechanical final grade table (skill-rubric-improvements T3, S2)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

import rubric_grade
import rubric_trace
from conftest import _body, _pdf
from test_rubric_trace import BODY, CRITERIA, REQUIREMENTS, listing, planned_folder, verified_folder

PAGES = [
    "Portada del informe",
    "Objetivos\nAnalizar el protocolo de red con claridad [1] y [2].",
    "Metodologia\nSe configuro la\ntopologia con tres routers [3] y [4].\n\nConclusiones\nEl enlace opera correctamente [5].",
]


def graded(folder: Path) -> dict:
    return yaml.safe_load((folder / "rubric-grade.yml").read_text(encoding="utf-8"))


def row(grade: dict, cid: str) -> dict:
    return next(c for c in grade["criteria"] if c["id"] == cid)


def test_grade_computes_weight_times_found_over_total_and_the_total(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = verified_folder(tmp_path)
    assert rubric_grade.main([str(folder)]) == 0
    grade = graded(folder)
    assert [row(grade, c)["score"] for c in ("objetivo", "metodologia", "conclusiones")] == [40.0, 15.0, 20.0]
    assert grade["score"] == 75.0 and grade["total"] == 100.0 and grade["percentage"] == 75.0
    assert grade["weights"] == "rubric"
    out = capsys.readouterr().out
    assert "75.00 / 100.00" in out and "75.0%" in out
    assert "mechanical estimate, not the teacher's grade" in out
    assert "| Objetivo claro (objetivo) | 40 |" in out


def test_grade_writes_the_table_in_the_working_folder_only(tmp_path: Path) -> None:
    folder = verified_folder(tmp_path)
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    (folder / "report.yml").write_text(
        (folder / "report.yml").read_text(encoding="utf-8") + f"delivery_dir: {delivery}\n", encoding="utf-8")
    before = listing(folder)
    assert rubric_grade.main([str(folder)]) == 0
    written = set(listing(folder)) - set(before)
    assert written == {"rubric-grade.yml", "rubric-grade.md"}
    assert list(delivery.iterdir()) == []
    md = (folder / "rubric-grade.md").read_text(encoding="utf-8")
    assert md.startswith("# Rubric grade") and "| Criterion | Weight | Evidence | Estimated score | Gap |" in md


def test_grade_never_touches_the_verification_inputs(tmp_path: Path) -> None:
    folder = verified_folder(tmp_path)
    before = listing(folder)
    rubric_grade.main([str(folder)])
    after = listing(folder)
    assert {k: v for k, v in after.items() if not k.startswith("rubric-grade")} == before


def test_equal_weights_when_the_rubric_has_none(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    unweighted = tuple({k: v for k, v in c.items() if k != "weight"} for c in CRITERIA)
    folder = verified_folder(tmp_path, unweighted)
    assert rubric_grade.main([str(folder)]) == 0
    grade = graded(folder)
    assert grade["weights"] == "equal"
    assert [row(grade, c)["weight"] for c in ("objetivo", "metodologia", "conclusiones")] == [1, 1, 1]
    # 1 + 1/2 + 2/3 = 2.1666..., over 3 -> 72.2%
    assert grade["score"] == 2.17 and grade["total"] == 3 and grade["percentage"] == 72.2
    assert "equal weights" in capsys.readouterr().out


def test_rounding_is_half_up_on_exact_fractions(tmp_path: Path) -> None:
    one = ({"id": "objetivo", "title": "Objetivo", "section": "Objetivos", "weight": 1},)
    requirements = [{"criterion": "objetivo", "requirement": f"Req {n}", "status": "found" if n == 0 else "missing",
                     "location": "Objetivos", "evidence": "Analizar el protocolo" if n == 0 else ""}
                    for n in range(8)]
    folder = verified_folder(tmp_path, one, requirements)
    assert rubric_grade.main([str(folder)]) == 0
    grade = graded(folder)
    assert row(grade, "objetivo")["score"] == 0.13  # 1/8 = 0.125 -> half up, not banker's
    assert grade["percentage"] == 12.5


def test_a_partial_requirement_counts_half(tmp_path: Path) -> None:
    folder = verified_folder(tmp_path)
    marker = folder / "content-check.yml"
    data = yaml.safe_load(marker.read_text(encoding="utf-8"))
    for req in data["requirements"]:
        if req["requirement"] == "Includes a network diagram":
            req["status"] = "partial"
    marker.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert rubric_grade.main([str(folder)]) == 0
    grade = graded(folder)
    assert row(grade, "metodologia")["score"] == 22.5  # 30 * (1 + 0.5) / 2
    assert "partial" in row(grade, "metodologia")["gap"].lower()


def test_a_red_deterministic_check_zeroes_the_criterion(tmp_path: Path) -> None:
    folder = verified_folder(tmp_path)
    (folder / "body.typeset.md").write_text(BODY.replace("protocolo", "esquema"), encoding="utf-8")
    assert rubric_grade.main([str(folder), "--body", "body.typeset.md"]) == 0
    grade = graded(folder)
    assert row(grade, "objetivo")["score"] == 0.0
    assert "protocolo" in row(grade, "objetivo")["gap"]
    assert grade["score"] == 35.0


def test_gap_names_the_missing_requirements(tmp_path: Path) -> None:
    folder = verified_folder(tmp_path)
    rubric_grade.main([str(folder)])
    grade = graded(folder)
    assert "Includes a network diagram" in row(grade, "metodologia")["gap"]
    assert row(grade, "objetivo")["gap"] == ""


def test_evidence_location_is_the_section_holding_the_quote_and_the_pdf_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = verified_folder(tmp_path)
    pdf = _pdf(folder)
    monkeypatch.setattr(rubric_trace, "pdf_pages", lambda path: PAGES)
    assert rubric_grade.main([str(folder)]) == 0
    grade = graded(folder)
    assert row(grade, "objetivo")["evidence"] == [{"section": "Objetivos", "page": 2}]
    # the quote wraps across a line break in the PDF text; both conclusions quotes sit on page 3
    assert row(grade, "metodologia")["evidence"] == [{"section": "Metodologia", "page": 3}]
    assert row(grade, "conclusiones")["evidence"] == [{"section": "Conclusiones", "page": 3}]
    assert grade["pdf"] == pdf.name
    out = capsys.readouterr().out
    assert "Objetivos, p. 2" in out


def test_without_a_final_pdf_the_location_degrades_to_the_section(tmp_path: Path) -> None:
    folder = verified_folder(tmp_path)
    assert rubric_grade.main([str(folder)]) == 0
    grade = graded(folder)
    assert row(grade, "objetivo")["evidence"] == [{"section": "Objetivos", "page": None}]
    assert grade["pdf"] is None


def test_a_quote_missing_from_the_pdf_text_keeps_the_section_without_a_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = verified_folder(tmp_path)
    _pdf(folder)
    monkeypatch.setattr(rubric_trace, "pdf_pages", lambda path: ["otra cosa", ""])
    assert rubric_grade.main([str(folder)]) == 0
    assert row(graded(folder), "objetivo")["evidence"] == [{"section": "Objetivos", "page": None}]


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="needs pdftotext")
def test_page_lookup_reads_a_real_generated_pdf(tmp_path: Path) -> None:
    folder = verified_folder(tmp_path)
    pdf = folder / "final" / "report.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(tiny_pdf(["Portada", "Objetivos Analizar el protocolo de red con claridad",
                              "Metodologia Se configuro la topologia con tres routers El enlace opera correctamente"]))
    assert subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True).returncode == 0
    assert rubric_grade.main([str(folder)]) == 0
    grade = graded(folder)
    assert row(grade, "objetivo")["evidence"] == [{"section": "Objetivos", "page": 2}]
    assert row(grade, "conclusiones")["evidence"] == [{"section": "Conclusiones", "page": 3}]


def test_grade_requires_a_current_verification(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = planned_folder(tmp_path)
    assert rubric_grade.main([str(folder)]) == 2
    assert "verification" in capsys.readouterr().err
    assert not (folder / "rubric-grade.yml").exists()
    folder = verified_folder(tmp_path / "other")
    _body(folder, BODY + "\nCambio.\n")
    assert rubric_grade.main([str(folder)]) == 2
    assert "stale" in capsys.readouterr().err
    assert not (folder / "rubric-grade.md").exists()


def test_a_report_without_a_rubric_has_nothing_to_grade(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "wf"
    folder.mkdir()
    (folder / "report.yml").write_text("type: ensayo\n", encoding="utf-8")
    assert rubric_grade.main([str(folder)]) == 0
    assert "no rubric.yml" in capsys.readouterr().out
    assert not (folder / "rubric-grade.yml").exists()


def test_a_malformed_rubric_is_an_input_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = planned_folder(tmp_path)
    (folder / "rubric.yml").write_text("schema: nope\n", encoding="utf-8")
    assert rubric_grade.main([str(folder)]) == 2
    assert "rubric.yml" in capsys.readouterr().err


def test_grade_refuses_to_write_inside_the_delivery_folder(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = verified_folder(tmp_path)
    (folder / "report.yml").write_text(
        (folder / "report.yml").read_text(encoding="utf-8") + f"delivery_dir: {folder}\n", encoding="utf-8")
    assert rubric_grade.main([str(folder)]) == 2
    assert "delivery" in capsys.readouterr().err
    assert not (folder / "rubric-grade.yml").exists()


def tiny_pdf(pages: list[str]) -> bytes:
    """A minimal uncompressed PDF with one line of text per page."""
    objects: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for index, text in enumerate(pages):
        page_id, content_id = 4 + index * 2, 5 + index * 2
        kids.append(f"{page_id} 0 R")
        stream = f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode("latin-1")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R "
            f"/Resources << /Font << /F1 3 0 R >> >> >>".encode())
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>".encode()
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
