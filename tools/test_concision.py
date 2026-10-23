"""Tests for tools/concision.py: prose word budgets and padding detection."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import concision  # noqa: E402


BODY = """# Objetivo

Medir el tiempo de respuesta del sistema.

# Resultados

| Parte | Tiempo |
|---|---|
| A | 3 ms |

```c
int main(void) { return 0; }
```

$$
t = \\frac{n}{f}
$$

![Figura 1](fig.png)

El sistema responde en tres milisegundos.

## Discusion

La diferencia se debe al reloj.
"""


def test_prose_words_skip_tables_code_math_images_and_headings() -> None:
    assert concision.prose_words("| a | b |\n|---|---|\n| uno | dos |") == 0
    assert concision.prose_words("```\nuno dos tres\n```") == 0
    assert concision.prose_words("$$\nx = y\n$$") == 0
    assert concision.prose_words("![uno dos](a.png)") == 0
    assert concision.prose_words("# Uno dos") == 0
    assert concision.prose_words("Uno dos tres [@key] y cuatro.") == 5


def test_section_text_includes_subsections_until_same_level() -> None:
    text = concision.section_text(BODY, "Resultados")
    assert "tres milisegundos" in text
    assert "reloj" in text
    assert "Medir" not in text
    assert concision.section_text(BODY, "No existe") is None


def test_effective_budgets_prefer_explicit_then_weight_share() -> None:
    criteria = [
        {"id": "a", "section": "Objetivo", "weight": 1, "max_words": 40},
        {"id": "b", "section": "Resultados", "weight": 3},
        {"id": "c", "section": "Resultados", "weight": 1},
    ]
    budgets = concision.section_budgets(criteria, total=200)
    # a explicit 40; b and c share 200 by weight over all weights (5): 120 + 40.
    assert budgets == {"Objetivo": 40, "Resultados": 160}


def test_no_weight_share_without_total_or_complete_weights() -> None:
    criteria = [{"id": "a", "section": "Objetivo"}, {"id": "b", "section": "Resultados", "weight": 2}]
    assert concision.section_budgets(criteria, total=200) == {}
    assert concision.section_budgets([{"id": "a", "section": "Objetivo", "weight": 1}], total=None) == {}


def test_budget_problems_report_section_and_total_overruns() -> None:
    criteria = [{"id": "a", "section": "Objetivo", "max_words": 3}]
    problems = concision.budget_problems(BODY, criteria, total=10)
    assert any("Objetivo" in p and "7 > 3" in p for p in problems)
    assert any("total" in p and "> 10" in p for p in problems)
    assert concision.budget_problems(BODY, criteria=[], total=None) == []


def test_budget_problems_flag_a_budgeted_section_missing_from_body() -> None:
    problems = concision.budget_problems(BODY, [{"id": "a", "section": "Nada", "max_words": 5}], total=None)
    assert problems == []  # a missing section is the rubric checks' job, not the budget's


def test_filler_phrases_are_found_case_and_accent_insensitive() -> None:
    body = "# A\n\nCabe destacar que el valor es 3.\n\nEs IMPORTANTE MENCIONAR el reloj.\n\nTexto limpio."
    found = concision.filler_problems(body)
    assert len(found) == 2
    assert any("cabe destacar" in item for item in found)
    assert concision.filler_problems("```\ncabe destacar\n```") == []


def test_long_paragraphs_over_limit_are_flagged_with_their_start() -> None:
    long_para = " ".join(["palabra"] * 81)
    body = f"# A\n\n{long_para}\n\n{' '.join(['corta'] * 80)}\n\n- {long_para}\n"
    problems = concision.long_paragraph_problems(body)
    assert len(problems) == 2
    assert all("81 words" in p for p in problems)
    table = "| " + " | ".join(["celda"] * 90) + " |"
    assert concision.long_paragraph_problems(table) == []


def test_concision_results_pass_on_a_clean_body() -> None:
    results = concision.concision_results(BODY, [], total=None)
    assert [r["check"] for r in results] == ["word_budget", "filler_phrases", "long_paragraphs"]
    assert all(r["ok"] for r in results)


def test_concision_results_fail_with_details() -> None:
    body = "# A\n\nEn resumen, todo funciona.\n"
    results = {r["check"]: r for r in concision.concision_results(body, [], total=2)}
    assert results["word_budget"]["ok"] is False
    assert results["filler_phrases"]["ok"] is False
    assert "en resumen" in results["filler_phrases"]["detail"]
    assert results["long_paragraphs"]["ok"] is True


def test_inline_math_is_not_counted_as_prose() -> None:
    assert concision.prose_words(r"Con $V_f \approx 2\ \text{V}$ enciende.") == 2


def test_unclosed_display_math_does_not_hide_the_rest_of_the_body() -> None:
    body = "Antes.\n\n$$ x = y\n\nCabe destacar que esto sigue siendo prosa.\n"
    assert concision.filler_problems(body)
    assert concision.prose_words(body) >= 8


def test_single_line_display_math_keeps_trailing_prose() -> None:
    assert concision.prose_words("$$ x = y $$ y luego texto") == 3


def test_unclosed_code_fence_does_not_hide_the_rest_of_the_body() -> None:
    body = "Antes.\n\n```c\n\nEn resumen, sigue.\n"
    assert concision.filler_problems(body)


def test_closed_blocks_still_hide_their_content() -> None:
    assert concision.prose_words("$$\ncabe destacar\n$$\n\n```\nen resumen\n```") == 0


def test_plain_text_table_caption_and_data_lines_are_not_prose() -> None:
    body = (
        "Antes de la tabla.\n\n"
        "Tabla 1. Equipos (nombre; rol)\n\n"
        "- router; capa 3\n"
        "- switch; capa 2\n\n"
        "Despues de la tabla.\n\n"
        "- una lista normal\n"
    )
    assert concision.prose_words(body) == 4 + 4 + 3
