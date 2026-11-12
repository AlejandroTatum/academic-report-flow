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

import pytest

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


# faster-verify-loop S1: a preview build runs while the verifier works, and its
# visual findings join the verifier's in ONE edit round; v1 is the build after it.
PREVIEW_SENTENCE = (
    "right after launching the verifier, while it works, decide the format, typeset and run "
    "{build} as a preview build and inspect every page; the preview is not v1: fix its visual "
    "findings together with the verifier's in ONE edit round, and v1 is the build made after that "
    "round, presented only once verify is done"
)


def test_verify_guidance_runs_a_preview_build_while_the_verifier_works(tmp_path: Path) -> None:
    sys.path.insert(0, str(TOOLS_DIR))
    import doc_status

    folder = tmp_path / "wf"
    folder.mkdir()
    (folder / "report.yml").write_text("type: ensayo\nroute: academic\n", encoding="utf-8")
    guidance = doc_status._guidance("verify", folder)
    build = doc_status._tool_command("build.py", folder)
    assert PREVIEW_SENTENCE.format(build=build) in guidance
    assert "--verify-brief --since verification.yml when it exists" in guidance
    assert "report missing and partial findings honestly" in guidance


def test_the_preview_build_removes_no_gate() -> None:
    sys.path.insert(0, str(TOOLS_DIR))
    import doc_status

    assert doc_status.PHASES.index("verify") < doc_status.PHASES.index("format") < doc_status.PHASES.index(
        "typeset") < doc_status.PHASES.index("generate")
    production = _flat(REFS / "production.md")
    assert "Runs once `verify`, `format` and `typeset` are `done`" in production


@pytest.mark.parametrize("name", ["SKILL.md", "references/production.md", "references/approval.md"])
def test_skill_docs_run_the_preview_build_in_parallel_with_the_verifier(name: str) -> None:
    flat = _flat(SKILL_ROOT / name)
    assert "while the verifier works" in flat
    assert "ONE edit round" in flat
    assert "v1 is the build made after that round" in flat


def test_production_generate_step_names_the_preview_build() -> None:
    generate = _flat(REFS / "production.md").split("## Generate", 1)[1].split("## Validate", 1)[0]
    assert "preview build" in generate and "while the verifier works" in generate
    assert "v1 is the build made after that round" in generate
