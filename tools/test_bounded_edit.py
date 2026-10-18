"""Tests for the pure bounded-edit predicate in ``tools/bounded_edit.py``.

An edit made after a human gate is bounded when at most ``limit`` words change
(inserted plus deleted) and no Markdown heading line is added, removed or
edited. The predicate is deterministic: same two texts, same answer.
"""
from __future__ import annotations

from bounded_edit import bounded, headings_changed, word_diff

BASE = "# Informe\n\nPreparado por Juan Perez para la catedra.\n\n## Resultados\n\nTexto del resultado.\n"


def test_identical_text_has_zero_words_and_is_bounded() -> None:
    assert word_diff(BASE, BASE) == 0
    assert bounded(BASE, BASE) == (True, 0)


def test_a_one_word_name_change_counts_two_words_and_is_bounded() -> None:
    new = BASE.replace("Juan", "Ana")
    assert word_diff(BASE, new) == 2
    assert bounded(BASE, new) == (True, 2)


def test_whitespace_only_changes_cost_nothing() -> None:
    assert word_diff("uno dos\ntres", "uno   dos tres\n\n") == 0


def test_pure_insertion_and_pure_deletion_count_their_words() -> None:
    assert word_diff("a b", "a x y b") == 2
    assert word_diff("a x y b", "a b") == 2


def test_forty_changed_words_are_bounded_and_forty_one_are_not() -> None:
    old = "inicio fin"
    assert bounded(old, "inicio " + " ".join(["w"] * 40) + " fin") == (True, 40)
    ok, words = bounded(old, "inicio " + " ".join(["w"] * 41) + " fin")
    assert (ok, words) == (False, 41)


def test_forty_one_replaced_words_are_not_bounded() -> None:
    old = " ".join(f"a{i}" for i in range(21))
    new = " ".join(f"b{i}" for i in range(21))
    ok, words = bounded(old, new)
    assert not ok and words == 42


def test_a_heading_edit_is_not_bounded_even_at_one_word() -> None:
    new = BASE.replace("## Resultados", "## Hallazgos")
    ok, words = bounded(BASE, new)
    assert not ok and words == 2
    assert headings_changed(BASE, new)


def test_adding_or_removing_a_heading_is_a_heading_change() -> None:
    assert headings_changed(BASE, BASE + "\n## Anexos\n")
    assert headings_changed(BASE, BASE.replace("## Resultados\n", ""))
    assert not bounded(BASE, BASE + "\n## Anexos\n")[0]


def test_body_edits_leave_headings_unchanged() -> None:
    assert not headings_changed(BASE, BASE.replace("Texto", "Contenido"))


def test_custom_limit_applies() -> None:
    assert bounded("a b c", "a x c", limit=1)[0] is False
    assert bounded("a b c", "a x c", limit=2)[0] is True


def test_a_setext_heading_edit_is_not_bounded() -> None:
    old = "Resultados\n==========\n\nTexto del resultado.\n"
    new = "Hallazgos\n=========\n\nTexto del resultado.\n"
    assert headings_changed(old, new)
    assert not bounded(old, new)[0]


def test_a_setext_level_change_is_a_heading_change() -> None:
    assert headings_changed("Resultados\n==========\n", "Resultados\n----------\n")


def test_adding_a_setext_heading_is_a_heading_change() -> None:
    assert headings_changed("Texto.\n", "Texto.\n\nAnexos\n------\n")


def test_body_edits_around_a_setext_heading_stay_bounded() -> None:
    old = "Resultados\n==========\n\nPreparado por Juan.\n"
    assert bounded(old, old.replace("Juan", "Ana")) == (True, 2)
