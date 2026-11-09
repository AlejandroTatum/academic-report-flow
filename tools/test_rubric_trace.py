"""rubric_trace.py: which body.md sections cover each rubric criterion (skill-rubric-improvements T3, S1)."""
from __future__ import annotations

from pathlib import Path

import pytest

import content_check
import rubric_trace
from conftest import _body, _report, _rubric, _sources_bib, _verification

BODY = """# Objetivos

Analizar el protocolo de red con claridad [@key1] y [@key2].

# Metodologia

Se configuro la topologia con tres routers [@key3] y [@key4].

# Conclusiones

El enlace opera correctamente [@key5].
"""

CRITERIA = (
    {"id": "objetivo", "title": "Objetivo claro", "section": "Objetivos", "weight": 40,
     "checks": [{"type": "contains", "section": "Objetivos", "text": "protocolo"}]},
    {"id": "metodologia", "title": "Metodologia descrita", "section": "Metodologia", "weight": 30,
     "checks": [{"type": "contains", "section": "Metodologia", "text": "topologia"}]},
    {"id": "conclusiones", "title": "Conclusiones", "section": "Conclusiones", "weight": 30,
     "checks": [{"type": "contains", "section": "Conclusiones", "text": "enlace"}]},
)

REQUIREMENTS = [
    {"criterion": "objetivo", "requirement": "States the goal", "status": "found",
     "location": "Objetivos", "evidence": "Analizar el protocolo de red"},
    {"criterion": "metodologia", "requirement": "Describes the topology", "status": "found",
     "location": "Metodologia", "evidence": "Se configuro la topologia"},
    {"criterion": "metodologia", "requirement": "Includes a network diagram", "status": "missing",
     "location": "", "evidence": ""},
    {"criterion": "conclusiones", "requirement": "Says the link works", "status": "found",
     "location": "Conclusiones", "evidence": "El enlace opera"},
    {"criterion": "conclusiones", "requirement": "Names the outcome", "status": "found",
     "location": "Conclusiones", "evidence": "opera correctamente"},
    {"criterion": "conclusiones", "requirement": "Lists recommendations", "status": "missing",
     "location": "", "evidence": ""},
]


def planned_folder(tmp_path: Path, criteria: tuple[dict, ...] = CRITERIA, body: str | None = BODY) -> Path:
    """A report folder with a rubric (and optionally a body); no verification yet."""
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _rubric(folder, criteria=criteria)
    if body is not None:
        _body(folder, body)
    return folder


def verified_folder(tmp_path: Path, criteria: tuple[dict, ...] = CRITERIA,
                    requirements: list[dict] | None = None) -> Path:
    """A planned folder with a body and a recorded (failing) verification matrix."""
    folder = planned_folder(tmp_path, criteria)
    path = _verification(folder, requirements=REQUIREMENTS if requirements is None else requirements)
    content_check.main([str(folder), "--verification", str(path)])
    return folder


def listing(folder: Path) -> dict[str, bytes]:
    return {str(p.relative_to(folder)): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def test_plan_without_a_body_is_all_red_and_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = planned_folder(tmp_path, body=None)
    assert rubric_trace.main([str(folder)]) == 1
    out = capsys.readouterr().out
    for cid in ("objetivo", "metodologia", "conclusiones"):
        assert cid in out
    assert "uncovered: 3/3" in out
    assert "body.md missing" in out


def test_a_covered_rubric_exits_0_and_shows_weight_and_section_per_criterion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = planned_folder(tmp_path)
    assert rubric_trace.main([str(folder)]) == 0
    out = capsys.readouterr().out
    assert "uncovered: 0/3" in out
    row = next(line for line in out.splitlines() if line.startswith("| objetivo "))
    assert "| 40 |" in row and "Objetivos" in row and "1/1" in row


def test_an_uncovered_criterion_is_named_with_its_reason(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = planned_folder(tmp_path, body=BODY.replace("topologia", "red"))
    assert rubric_trace.main([str(folder)]) == 1
    out = capsys.readouterr().out
    assert "uncovered: 1/3" in out
    assert "metodologia" in out.split("Uncovered:", 1)[1]
    assert "topologia" in out.split("Uncovered:", 1)[1]
    assert "objetivo" not in out.split("Uncovered:", 1)[1]


def test_a_missing_section_is_uncovered(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    body = BODY.split("# Conclusiones")[0]
    folder = planned_folder(tmp_path, body=body)
    assert rubric_trace.main([str(folder)]) == 1
    tail = capsys.readouterr().out.split("Uncovered:", 1)[1]
    assert "conclusiones" in tail and "section 'Conclusiones' missing" in tail


def test_trace_is_read_only(tmp_path: Path) -> None:
    folder = verified_folder(tmp_path)
    before = listing(folder)
    rubric_trace.main([str(folder)])
    assert listing(folder) == before


def test_section_flag_limits_the_trace_to_the_criteria_that_section_serves(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = planned_folder(tmp_path)
    assert rubric_trace.main([str(folder), "--section", "metodologia"]) == 0
    out = capsys.readouterr().out
    assert "| metodologia " in out
    assert "| objetivo " not in out and "| conclusiones " not in out


def test_section_flag_with_no_mapped_criterion_is_an_input_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = planned_folder(tmp_path)
    assert rubric_trace.main([str(folder), "--section", "Anexos"]) == 2
    assert "no criterion maps to section 'Anexos'" in capsys.readouterr().err


def test_a_folder_without_a_valid_rubric_is_an_input_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    assert rubric_trace.main([str(folder)]) == 2
    assert "rubric.yml" in capsys.readouterr().err
    (folder / "rubric.yml").write_text("schema: nope\n", encoding="utf-8")
    assert rubric_trace.main([str(folder)]) == 2


def test_a_rubric_without_weights_gets_equal_weights_and_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    unweighted = tuple({k: v for k, v in c.items() if k != "weight"} for c in CRITERIA)
    folder = planned_folder(tmp_path, unweighted)
    assert rubric_trace.main([str(folder)]) == 0
    out = capsys.readouterr().out
    assert "equal weights" in out
    assert next(line for line in out.splitlines() if line.startswith("| objetivo ")).count("| 1 |") == 1


def test_partial_weights_fall_back_to_equal_weights_for_every_criterion(tmp_path: Path) -> None:
    mixed = (CRITERIA[0], {k: v for k, v in CRITERIA[1].items() if k != "weight"}, CRITERIA[2])
    folder = planned_folder(tmp_path, mixed)
    weights, source = rubric_trace.effective_weights(rubric_trace.load_criteria(folder))
    assert source == "equal" and set(weights.values()) == {1}


def test_a_current_verification_adds_requirement_counts_and_sections_of_the_quotes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = verified_folder(tmp_path)
    assert rubric_trace.main([str(folder)]) == 1  # requirements are missing
    out = capsys.readouterr().out
    meto = next(line for line in out.splitlines() if line.startswith("| metodologia "))
    assert "1/2" in meto and "Metodologia" in meto
    concl = next(line for line in out.splitlines() if line.startswith("| conclusiones "))
    assert "2/3" in concl
    assert "Lists recommendations" in out.split("Uncovered:", 1)[1]


def test_a_stale_verification_is_ignored_and_said_so(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = verified_folder(tmp_path)
    _body(folder, BODY + "\n## Nueva\n\nUna frase nueva.\n")  # unbounded: a heading
    assert rubric_trace.main([str(folder)]) == 0  # checks are green; stale matrix is not used
    out = capsys.readouterr().out
    assert "verification stale" in out
    assert "1/2" not in out


def test_body_flag_traces_the_typeset_copy_and_reports_what_it_lost(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = planned_folder(tmp_path)
    (folder / "body.typeset.md").write_text(BODY.replace("topologia", "red"), encoding="utf-8")
    assert rubric_trace.main([str(folder), "--body", "body.typeset.md"]) == 1
    out = capsys.readouterr().out
    assert "body.typeset.md" in out
    assert "metodologia" in out.split("Uncovered:", 1)[1]


def test_pdf_flag_reports_checked_text_that_never_reached_the_pdf(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = planned_folder(tmp_path)
    pdf = folder / "final.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(rubric_trace, "pdf_pages", lambda path: [
        "Portada", "Objetivos\nAnalizar el protocolo", "Metodologia\nSe configuro la topo-\nlogia", ""])
    assert rubric_trace.main([str(folder), "--pdf", str(pdf)]) == 1
    out = capsys.readouterr().out
    assert "lost in the PDF" in out and "conclusiones" in out and "enlace" in out
    assert "metodologia" not in out.split("lost in the PDF", 1)[1]  # hyphenation does not count as a loss
