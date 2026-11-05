"""Static contract: verification runs in parallel with the draft preview build (S7).

The verifier needs only ``body.md`` and the rubric; ``draft_pdf.py`` needs only
``body.md``. The skill tells the orchestrator to start both in the same step, and
the approval gate still requires a fresh draft and a current verification for the
same ``body.md`` bytes. No phase is added, removed or renamed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "skills" / "academic-report-flow"
REFS = SKILL_ROOT / "references"
TOOLS_DIR = ROOT / "tools"


def _flat(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_production_runs_verify_in_parallel_with_the_preview_build() -> None:
    flat = _flat(REFS / "production.md")
    assert re.search(r"in parallel with .{0,80}draft_pdf\.py", flat)
    assert "same step" in flat


def test_approval_starts_the_preview_build_with_the_verifier() -> None:
    flat = _flat(REFS / "approval.md")
    assert re.search(r"parallel.{0,200}verif", flat)
    assert re.search(r"fresh draft.{0,80}current verification|current verification.{0,80}fresh draft", flat)
    assert "same `body.md` bytes" in flat


def test_parallel_verify_keeps_the_gate_and_the_phase_list() -> None:
    sys.path.insert(0, str(TOOLS_DIR))
    import doc_status

    assert doc_status.PHASES == (
        "intake", "research", "plan", "draft", "verify", "approval", "format",
        "typeset", "generate", "validate", "review", "deliver",
    )
    assert "approval gate stays closed" in doc_status._GUIDANCE["verify"]


def test_skill_mentions_timings_without_a_score_gate() -> None:
    flat = _flat(SKILL_ROOT / "SKILL.md")
    assert "timings.yml" in flat and "timings.py" in flat
    for name in ("SKILL.md", "references/approval.md", "references/production.md"):
        assert "percent" not in (SKILL_ROOT / name).read_text(encoding="utf-8").lower()


def test_portal_tool_table_lists_timings() -> None:
    table = (ROOT / "docs" / "portal" / "herramientas.qmd").read_text(encoding="utf-8")
    row = next((line for line in table.splitlines() if line.startswith("| `timings.py`")), "")
    assert "timings.yml" in row
