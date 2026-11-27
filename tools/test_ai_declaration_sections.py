"""The skill documents phase-grouped, formal ``Se solicitó`` instructions as the default."""
from __future__ import annotations

from pathlib import Path

APPROVAL = Path(__file__).resolve().parent.parent / "skills/academic-report-flow/references/approval.md"
PHASES = ("Comprensión de la guía", "Implementación", "Resultados y gráficas", "Redacción del informe", "Revisión")


def test_approval_documents_sectioned_formal_instructions_as_default() -> None:
    approval = " ".join(APPROVAL.read_text(encoding="utf-8").split())
    assert "{section: <phase>, items: [...]}" in approval
    assert "Se solicitó" in approval
    positions = [approval.index(f"{n}. {phase}") for n, phase in enumerate(PHASES, 1)]
    assert positions == sorted(positions)
    assert "omit phases that did not happen" in approval
