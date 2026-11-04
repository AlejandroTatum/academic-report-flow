"""Tests for the shared full-page cover (templates/cover-page.tex + build_cover.py).

The cover is one template for every assignment type (ABPR, AA, APE, ACD...).
These tests pin the YAML contract, placeholder filling, LaTeX escaping, the
identification-panel rows and the CLI failure mode. They only use the public
functions and ``--tex-only``: no LaTeX engine or Docker is needed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import build_cover  # noqa: E402

MINIMAL = {
    "activity": "ABPR",
    "subject": "Fundamentos de Redes",
    "heading": "Video integrador",
}

FULL = {
    **MINIMAL,
    "title": "Fundamentos de networking",
    "student": "Alejandro Padilla",
    "teacher": "Ing. Mario Cueva",
    "cycle": "Quinto",
    "unit": "Unidad 1",
    "date": "3 de noviembre de 2026",
}


def render(data: dict) -> str:
    return build_cover.render_tex(data)


def test_template_exists_and_declares_every_placeholder_the_builder_fills():
    template = (ROOT / "templates" / "cover-page.tex").read_text(encoding="utf-8")
    used = set(re.findall(r"\{\{([A-Z_]+)\}\}", template))
    assert used == set(build_cover.PLACEHOLDERS)


def test_every_placeholder_is_filled():
    tex = render(FULL)
    assert not re.search(r"\{\{[A-Z_]+\}\}", tex)
    assert "Video integrador" in tex
    assert "Fundamentos de networking" in tex
    assert "Universidad Nacional de Loja" in tex
    assert "Carrera de Computación" in tex
    assert "ape-faculty-logo.png" in tex


def test_defaults_for_city_and_year():
    tex = render(FULL)
    assert "Loja, Ecuador" in tex
    assert "2026" in tex  # year derived from the date


def test_year_falls_back_to_current_year_without_date():
    from datetime import date

    assert str(date.today().year) in render(MINIMAL)


def test_explicit_year_and_city_override_defaults():
    tex = render({**FULL, "city": "Quito, Ecuador", "year": 2030})
    assert "Quito, Ecuador" in tex
    assert "2030" in tex
    assert "Loja, Ecuador" not in tex


def test_kicker_is_activity_and_uppercased_subject():
    values = build_cover.build_values(FULL)
    assert values["KICKER"] == "ACTIVIDAD ABPR · FUNDAMENTOS DE REDES"
    accented = build_cover.build_values({**MINIMAL, "subject": "Análisis Numérico"})
    assert accented["KICKER"] == "ACTIVIDAD ABPR · ANÁLISIS NUMÉRICO"


def test_values_are_latex_escaped():
    tex = render({
        **FULL,
        "heading": "R&D 50% #1",
        "title": "snake_case y $costo",
        "student": "A & B_C",
    })
    assert r"R\&D 50\% \#1" in tex
    assert r"snake\_case y \$costo" in tex
    assert r"A \& B\_C" in tex
    assert "R&D" not in tex


def test_absent_optional_fields_are_omitted_from_the_panel():
    tex = render(MINIMAL)
    for label in ("Estudiante", "Docente", "Ciclo", "Unidad", "Fecha de entrega"):
        assert label not in tex
    # Required fields always show.
    assert r"\cell{Asignatura}{Fundamentos de Redes}" in tex
    assert r"\cell{Actividad}{ABPR}" in tex


def test_panel_rows_are_packed_two_per_row_in_order():
    rows = build_cover.ficha_rows(FULL)
    lines = [line for line in rows.splitlines() if line.strip()]
    assert lines[0].startswith(r"\cell{Estudiante}{Alejandro Padilla} & \cell{Docente}{Ing. Mario Cueva}")
    assert lines[1].startswith(r"\cell{Asignatura}{Fundamentos de Redes} & \cell{Ciclo}{Quinto}")
    assert lines[2].startswith(r"\cell{Unidad}{Unidad 1} & \cell{Actividad}{ABPR}")
    assert lines[3].startswith(r"\cell{Fecha de entrega}{3 de noviembre de 2026}")
    assert lines[0].rstrip().endswith(r"\\[14pt]")
    assert lines[2].rstrip().endswith(r"\\[14pt]")
    assert not lines[3].rstrip().endswith(r"\\[14pt]")


def test_remaining_fields_are_packed_when_some_are_absent():
    rows = build_cover.ficha_rows({**MINIMAL, "teacher": "Ing. Mario Cueva"})
    first = rows.splitlines()[0]
    # Without students, the teacher moves up and pairs with the subject.
    assert first.startswith(r"\cell{Docente}{Ing. Mario Cueva} & \cell{Asignatura}")


def test_parallel_is_never_printed_unless_given():
    assert "paralelo" not in render(FULL).lower()
    tex = render({**FULL, "parallel": "A"})
    assert r"\cell{Ciclo}{Quinto, paralelo A}" in tex


def test_parallel_without_cycle_is_still_shown():
    tex = render({**MINIMAL, "parallel": "B"})
    assert r"\cell{Ciclo}{Paralelo B}" in tex


def test_members_use_plural_label_and_one_name_per_line():
    tex = render({**FULL, "student": None, "members": ["Ana Pérez", "Luis Gómez & Co"]})
    assert r"\cell{Estudiantes}{Ana Pérez\\Luis Gómez \& Co}" in tex
    assert r"\cell{Estudiante}{" not in tex


def test_single_student_uses_singular_label():
    assert r"\cell{Estudiante}{Alejandro Padilla}" in render(FULL)


def test_title_block_is_dropped_without_title():
    without = render(MINIMAL)
    assert "coversubtitle{" not in without.split(r"\begin{document}")[1]
    assert r"\coversubtitle{Fundamentos de networking}" in render(FULL)


@pytest.mark.parametrize("missing", ["activity", "subject", "heading"])
def test_missing_required_key_exits_nonzero_with_clear_message(tmp_path, capsys, missing):
    data = {k: v for k, v in MINIMAL.items() if k != missing}
    yml = tmp_path / "cover.yml"
    yml.write_text("\n".join(f"{k}: {v}" for k, v in data.items()), encoding="utf-8")
    code = build_cover.main([str(yml), "--tex-only"])
    assert code != 0
    err = capsys.readouterr().err
    assert missing in err
    assert "obligatori" in err.lower()


def test_missing_yaml_file_exits_nonzero(tmp_path, capsys):
    assert build_cover.main([str(tmp_path / "nope.yml"), "--tex-only"]) != 0
    assert "nope.yml" in capsys.readouterr().err


def test_tex_only_writes_tex_next_to_yml_and_does_not_compile(tmp_path):
    yml = tmp_path / "cover.yml"
    yml.write_text(
        "activity: ABPR\nsubject: Redes\nheading: Video\nparallel: A\n", encoding="utf-8"
    )
    assert build_cover.main([str(yml), "--tex-only"]) == 0
    tex = (tmp_path / "portada.tex").read_text(encoding="utf-8")
    assert r"\cell{Ciclo}{Paralelo A}" in tex
    assert not (tmp_path / "portada.pdf").exists()


def test_tex_only_honours_output_path(tmp_path):
    yml = tmp_path / "cover.yml"
    yml.write_text("activity: AA\nsubject: Redes\nheading: Video\n", encoding="utf-8")
    out = tmp_path / "sub" / "cover.pdf"
    assert build_cover.main([str(yml), "--tex-only", "-o", str(out)]) == 0
    assert (tmp_path / "sub" / "cover.tex").exists()


def test_yaml_date_object_is_formatted_in_spanish(tmp_path):
    yml = tmp_path / "cover.yml"
    yml.write_text(
        "activity: AA\nsubject: Redes\nheading: Video\ndate: 2026-11-03\n", encoding="utf-8"
    )
    assert build_cover.main([str(yml), "--tex-only"]) == 0
    tex = (tmp_path / "portada.tex").read_text(encoding="utf-8")
    assert "3 de noviembre de 2026" in tex
