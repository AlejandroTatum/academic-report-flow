"""Guide requirement inventory: mandate verbs, questions and deliverables (skill-rubric-improvements T4, S5)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

from guide_facts import extract_guide_facts, extract_guide_inventory, load_guide_inventory

GUIDE = """Guía de Actividades de Aprendizaje Autónomo

1. Datos generales
Tiempo planificado: 4 horas

2. Actividades
a) Elabore un diagrama de la topología de red con tres
   routers.
b) Configure el enrutamiento OSPF y adjunte las capturas de pantalla.
- Compare RIP y OSPF.
¿Qué ventajas tiene OSPF frente a RIP?
El estudiante debe justificar la elección de las direcciones IP.
Se debe entregar el enlace al proyecto en Wokwi.

3. Bibliografía
Las fuentes deben citarse en formato IEEE.
"""


def kinds(inventory: list[dict]) -> list[tuple[str, str]]:
    return [(item["id"], item["kind"]) for item in inventory]


def test_inventory_numbers_mandates_questions_and_deliverables_in_guide_order() -> None:
    inventory = extract_guide_inventory(GUIDE)
    assert kinds(inventory) == [
        ("G1", "mandate"), ("G2", "deliverable"), ("G3", "mandate"), ("G4", "question"),
        ("G5", "mandate"), ("G6", "deliverable"), ("G7", "mandate"),
    ]
    assert inventory[0]["text"] == "Elabore un diagrama de la topología de red con tres routers."
    assert inventory[3]["text"] == "¿Qué ventajas tiene OSPF frente a RIP?"
    assert "enlace" in inventory[5]["text"]


def test_inventory_ignores_headings_and_labeled_facts() -> None:
    texts = " ".join(item["text"] for item in extract_guide_inventory(GUIDE))
    assert "Datos generales" not in texts and "Tiempo planificado" not in texts


def test_inventory_is_empty_without_demands_and_never_raises() -> None:
    assert extract_guide_inventory("Datos generales\nAsignatura: Redes\n") == []
    assert extract_guide_inventory("") == []
    assert extract_guide_inventory(None) == []  # type: ignore[arg-type]


def test_inventory_deduplicates_repeated_demands() -> None:
    inventory = extract_guide_inventory("Elabore un informe técnico.\nElabore un informe técnico.\n")
    assert [item["id"] for item in inventory] == ["G1"]


def test_facts_dict_is_unchanged_by_the_inventory() -> None:
    assert "inventory" not in extract_guide_facts(GUIDE)


def test_loader_confines_the_guide_to_the_folder(tmp_path: Path) -> None:
    folder = tmp_path / "report"
    folder.mkdir()
    (folder / "guide.txt").write_text(GUIDE, encoding="utf-8")
    assert len(load_guide_inventory(folder, {"guide": "guide.txt"})) == 7
    assert load_guide_inventory(folder, {"guide": "../guide.txt"}) == []
    assert load_guide_inventory(folder, {}) == []


def test_cli_inventory_flag_prints_yaml_and_default_output_is_unchanged(tmp_path: Path) -> None:
    folder = tmp_path / "report"
    folder.mkdir()
    (folder / "report.yml").write_text("guide: guide.txt\n", encoding="utf-8")
    (folder / "guide.txt").write_text(GUIDE, encoding="utf-8")
    script = str(Path(__file__).with_name("guide_facts.py"))
    result = subprocess.run([sys.executable, script, str(folder), "--inventory"], capture_output=True, text=True)
    assert result.returncode == 0
    printed = yaml.safe_load(result.stdout)
    assert [item["id"] for item in printed["inventory"]][:2] == ["G1", "G2"]
    plain = subprocess.run([sys.executable, script, str(folder)], capture_output=True, text=True)
    assert "inventory" not in plain.stdout
