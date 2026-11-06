"""Banned conclusion openers are checked only inside the conclusions section (ape6-flow-defects T3, S2)."""
from __future__ import annotations

import pytest

import validate_report

BANNED = ["Se concluye", "En conclusión", "En conclusion"]


def found(text: str) -> list[str]:
    return validate_report.banned_conclusion_openers(text, BANNED)


def test_phrase_in_a_control_question_answer_is_not_an_error() -> None:
    text = (
        "Preguntas de control\nY se concluye que el generador no produce valores uniformes.\n\n"
        "Conclusiones\nEl generador pasa la prueba al 5 %.\n\nBibliografía\nDiapositivas.\n"
    )
    assert found(text) == []


def test_opener_inside_conclusions_is_an_error() -> None:
    text = "Resultados\nTabla.\n\nConclusiones\nSe concluye que el generador es uniforme.\n\nReferencias\nX.\n"
    assert found(text) == ["Se concluye"]


@pytest.mark.parametrize("next_heading", ["Recomendaciones", "Anexos", "Bibliografía", "Referencias"])
def test_section_ends_at_the_next_top_level_heading(next_heading: str) -> None:
    text = f"Conclusiones\nEl generador es uniforme.\n\n{next_heading}\nEn conclusión, ver la tabla.\n"
    assert found(text) == []


def test_numbered_heading_and_section_running_to_the_end() -> None:
    text = "Intro\nse concluye aquí.\n\n5. Conclusiones\nEn conclusion, todo cuadra.\n"
    assert found(text) == ["En conclusion"]


def test_without_a_conclusions_heading_the_whole_text_is_checked() -> None:
    # When the section cannot be located the check stays as strict as before: the whole text.
    assert found("Resultados\nSe concluye que todo cuadra.\n") == ["Se concluye"]
