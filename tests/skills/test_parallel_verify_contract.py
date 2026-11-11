"""Static contract: verification never waits for a draft preview (S7, report-v1 T2).

The verifier needs only ``body.md`` and the rubric; ``draft_pdf.py`` is an
optional preview. When the user asks for one, the skill starts both in the same
step. There is no approval gate any more, and no phase is added, removed or
renamed.
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


def test_production_starts_an_optional_preview_in_the_same_step_as_the_verifier() -> None:
    flat = _flat(REFS / "production.md")
    assert "No draft PDF has to exist first" in flat
    assert re.search(r"optional plain preview .{0,80}draft_pdf\.py", flat)
    assert "same step as the verifier" in flat


def test_approval_reference_makes_the_preview_optional() -> None:
    flat = _flat(REFS / "approval.md")
    assert "Neither is a prerequisite for typeset or generate" in flat
    assert "fresh draft" not in flat


def test_verify_guidance_reports_findings_and_keeps_the_phase_list() -> None:
    sys.path.insert(0, str(TOOLS_DIR))
    import doc_status

    assert doc_status.PHASES == (
        "intake", "research", "plan", "draft", "verify", "approval", "format",
        "typeset", "generate", "validate", "review", "deliver",
    )
    verify = doc_status._GUIDANCE["verify"]
    assert "approval gate stays closed" not in verify
    assert "report missing and partial findings honestly" in verify


def test_skill_mentions_timings_without_a_score_gate() -> None:
    flat = _flat(SKILL_ROOT / "SKILL.md")
    assert "timings.yml" in flat and "timings.py" in flat
    for name in ("SKILL.md", "references/approval.md", "references/production.md"):
        assert "percent" not in (SKILL_ROOT / name).read_text(encoding="utf-8").lower()


def test_portal_tool_table_lists_timings() -> None:
    table = (ROOT / "docs" / "portal" / "herramientas.qmd").read_text(encoding="utf-8")
    row = next((line for line in table.splitlines() if line.startswith("| `timings.py`")), "")
    assert "timings.yml" in row
