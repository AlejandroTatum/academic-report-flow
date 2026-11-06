"""Every LaTeX template loads Spanish so LuaLaTeX hyphenates and labels in Spanish.

Without a language package LuaLaTeX breaks Spanish words with English patterns
("it-eración") and names tables "Table". babel also resets the caption names at
``\\begin{document}``, so a template's own labels must go through its hook.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
BABEL = re.compile(r"\\usepackage\[([^\]]*)\]\{babel\}")


@pytest.mark.parametrize("name", [
    "unl-report.tex", "plain-report.tex", "chamba-overleaf.tex",
    "ape-report.tex", "aa-report.tex", "acd-report.tex", "ieee-report.tex",
])
def test_every_template_loads_spanish_babel(name: str) -> None:
    match = BABEL.search((TEMPLATES / name).read_text(encoding="utf-8"))
    assert match, f"{name} has no babel package"
    assert "spanish" in match.group(1).split(",")


@pytest.mark.parametrize(("name", "labels"), [
    ("unl-report.tex", {"figurename": "Figura", "listfigurename": "Índice de Figuras"}),
    ("plain-report.tex", {"figurename": "Figura", "listfigurename": "Índice de Figuras"}),
    ("chamba-overleaf.tex", {
        "figurename": "Figura", "contentsname": "Índice General",
        "listfigurename": "Índice de Figuras", "refname": "Referencias bibliográficas",
    }),
])
def test_template_labels_survive_babel(name: str, labels: dict[str, str]) -> None:
    text = (TEMPLATES / name).read_text(encoding="utf-8")
    hook = re.search(r"\\addto\\captionsspanish\{(.*)\}\s*$", text, re.M)
    assert hook, f"{name} sets its labels outside babel's caption hook"
    for command, label in labels.items():
        assert f"\\renewcommand{{\\{command}}}{{{label}}}" in hook.group(1)
    match = BABEL.search(text)
    assert match and "es-tabla" in match.group(1), "tables read 'Tabla', not babel's 'Cuadro'"
