"""Static contract tests for the academic-report-flow skill.

These tests read the skill markdown as data. They do not run the report
pipeline. Their only job is to prove that the routing contract cannot
silently regress back to "every document is a UNL assignment".
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills" / "academic-report-flow"
REFERENCES = SKILL_ROOT / "references"

SKILL_MD = SKILL_ROOT / "SKILL.md"
INTAKE_MD = REFERENCES / "data.md"
ROUTING_MD = REFERENCES / "routing.md"
VISUAL_MD = REFERENCES / "visual-directions.md"
GATES_MD = REFERENCES / "production.md"
UNL_MD = REFERENCES / "unl-shell.md"
DELIVERY_MD = REFERENCES / "delivery.md"

RESEARCH_ROOT = Path(__file__).resolve().parents[2] / "skills" / "research-workflow"
RESEARCH_MD = RESEARCH_ROOT / "references" / "research-protocol.md"

# The one human confirmation gate lives in the orchestrator skill, not in intake.
APPROVAL_REFERENCE = "references/approval.md"

ROUTE_SCOPED_FILES = (SKILL_MD, ROUTING_MD)

# Files that must never mention the UNL shell, because they are loaded on
# every route. If unl-shell.md leaks into one of these, a project-doc run
# would pull the institutional cover.
ROUTE_AGNOSTIC_FILES = (INTAKE_MD, VISUAL_MD, GATES_MD)


def read(path: Path) -> str:
    assert path.is_file(), f"missing required skill file: {path}"
    return path.read_text(encoding="utf-8")


def plain(text: str) -> str:
    """Strip markdown emphasis so prose assertions match the rendered wording."""
    return re.sub(r"[*_`]", "", text)


def sections(text: str) -> dict[str, str]:
    """Split a reference file into {heading: body} using its markdown headings."""
    found: dict[str, str] = {}
    heading = "__preamble__"
    buffer: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^#{1,6}\s+(.*)$", line)
        if match:
            found[heading] = "\n".join(buffer)
            heading = match.group(1).strip()
            buffer = []
        else:
            buffer.append(line)
    found[heading] = "\n".join(buffer)
    return found


@pytest.fixture(scope="module")
def skill() -> str:
    return read(SKILL_MD)


@pytest.fixture(scope="module")
def intake() -> str:
    return read(INTAKE_MD)


@pytest.fixture(scope="module")
def routing() -> str:
    return read(ROUTING_MD)


# --------------------------------------------------------------------------
# Structure
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [SKILL_MD, INTAKE_MD, ROUTING_MD, VISUAL_MD, GATES_MD, UNL_MD, DELIVERY_MD],
    ids=lambda p: p.name,
)
def test_required_file_exists(path: Path) -> None:
    assert path.is_file(), f"{path.name} is required by the skill contract"


def test_skill_declares_version_two_or_later(skill: str) -> None:
    match = re.search(r'version:\s*"(\d+)\.(\d+)"', skill)
    assert match, "SKILL.md frontmatter must declare metadata.version"
    major = int(match.group(1))
    assert major >= 2, "multimodal routing landed in version 2.0"


def test_description_is_not_unl_only(skill: str) -> None:
    match = re.search(r'^description:\s*"(.+)"$', skill, re.MULTILINE)
    assert match, "SKILL.md must declare a description"
    description = match.group(1).lower()
    for expected in ("project documentation", "technical document"):
        assert expected in description, (
            f"description must trigger on {expected!r}, not only academic work"
        )


# --------------------------------------------------------------------------
# 8.1 — the document-type gate
# --------------------------------------------------------------------------


def test_document_type_gate_exists(skill: str) -> None:
    assert "references/data.md" in skill, "SKILL.md must route intake to its reference"
    assert "Prohibition On Inferring Document Type" in skill


DOCUMENT_TYPES = (
    "University academic work",
    "Project documentation",
    "Professional",
    "Technical document",
    "Other",
)


@pytest.mark.parametrize("document_type", DOCUMENT_TYPES)
def test_intake_lists_all_five_document_types(intake: str, document_type: str) -> None:
    assert document_type.lower() in intake.lower(), (
        f"intake must offer {document_type!r} as a document type"
    )


CONFIRMATIONS = (
    "audience",
    "purpose",
    "template",
    "identity",
    "pdf",
    "docx",
    "visual direction",
)


@pytest.mark.parametrize("token", CONFIRMATIONS)
def test_intake_covers_every_confirmation(intake: str, token: str) -> None:
    assert token in intake.lower(), f"intake is missing the {token!r} confirmation"


VISUAL_DIRECTIONS = ("Sober", "Institutional", "Technical", "Executive", "Custom")


@pytest.mark.parametrize("direction", VISUAL_DIRECTIONS)
def test_visual_directions_are_defined(direction: str) -> None:
    intake_text = read(INTAKE_MD)
    visual_text = read(VISUAL_MD)
    assert direction.lower() in intake_text.lower(), (
        f"{direction} must be offered in the intake"
    )
    assert direction.lower() in visual_text.lower(), (
        f"{direction} must have an operational definition"
    )


def test_confirmation_is_required_on_every_execution(skill: str, intake: str) -> None:
    combined = plain(skill + intake).lower()
    assert "every execution" in combined or "every run" in combined
    assert "even when the prompt appears to already contain" in combined, (
        "a prompt that looks complete must still be confirmed as intake data"
    )
    # The intake confirmation is a data record, never an approval to generate.
    assert "does not authorize generation" in combined, (
        "intake must state that recording the contract authorizes no generation"
    )
    assert "generation begins only after the user confirms this block" not in combined, (
        "the intake-time approval-to-generate sentence must be gone"
    )


def test_document_contract_block_is_specified(intake: str) -> None:
    assert "Document Contract" in intake
    for field in ("Type:", "Audience:", "Purpose:", "Outputs:", "Visual direction:"):
        assert field in intake, f"Document Contract block must render {field!r}"
    data_record = plain(intake).lower()
    assert "data record" in data_record, (
        "the Document Contract must be described as a data record, not an approval"
    )
    assert "report.yml" in plain(intake), (
        "the Document Contract record must be written to report.yml"
    )


def test_single_confirmation_is_the_approval_gate_and_traceable(intake: str) -> None:
    """Exactly one confirmation gate exists in the route, and intake defers to it.

    Intake records data only; the single gate is the human approval defined in
    references/approval.md.
    """
    data = plain(intake)
    lowered = data.lower()
    assert data.count(APPROVAL_REFERENCE) == 1, (
        "intake must forward-reference the approval gate exactly once"
    )
    assert "generation starts only after the one human approval" in lowered, (
        "intake must defer the single confirmation to the approval reference"
    )
    assert "never asks for approval" in lowered, (
        "intake must explicitly refuse to be the approval gate"
    )


@pytest.mark.parametrize("path", ROUTE_AGNOSTIC_FILES, ids=lambda p: p.name)
def test_no_route_agnostic_reference_authorizes_intake_time_generation(path: Path) -> None:
    """The removed sentence must not relocate into another always-loaded reference."""
    lowered = plain(read(path)).lower()
    assert "generation begins only after the user confirms this block" not in lowered
    assert "confirm this block to generate" not in lowered


def test_intake_may_ask_one_targeted_clarification_per_missing_field(intake: str) -> None:
    lowered = plain(intake).lower()
    assert "one targeted clarification" in lowered, (
        "adaptivity must be bounded to one clarification per missing field"
    )
    assert "route-mandatory" in lowered, (
        "the clarification must be scoped to missing route-mandatory fields"
    )


# --------------------------------------------------------------------------
# SKILL.md — intake records data; the single gate is post-preview approval
# --------------------------------------------------------------------------


def test_skill_keeps_intake_data_only_and_gates_the_build_on_approval(skill: str) -> None:
    """SKILL.md must never let intake authorize generation.

    The only confirmation gate is the approval owned by `references/approval.md`;
    the data-record wording itself lives once, in `references/data.md`.
    """
    lowered = re.sub(r"\s+", " ", plain(skill)).lower()
    assert "intake data (references/data.md) never authorizes generation" in lowered
    assert "a preapproval draft preview is permitted only for review" in lowered
    assert "never build the final artifact before approval is done and typeset passes" in lowered
    for stale in (
        "wait for explicit confirmation before generation",
        "generation begins only after the user confirms this block",
    ):
        assert stale not in lowered, (
            f"stale intake-time approval wording must be gone: {stale!r}"
        )


def test_skill_publication_requires_current_approval(skill: str) -> None:
    """Publication is gated on APPROVAL_CURRENT, not merely technical validation."""
    lowered = re.sub(r"\s+", " ", skill).lower()
    assert "approval_current" in lowered, (
        "SKILL.md must name APPROVAL_CURRENT as the publication precondition"
    )
    assert "automatically publish" not in lowered, (
        "technical validation alone must not read as automatic publication"
    )
    publication_lines = [line for line in skill.splitlines() if "deliver_report.py" in line]
    assert any("APPROVAL_CURRENT" in line for line in publication_lines), (
        "the publication rule must be conditioned on APPROVAL_CURRENT"
    )
    delivery = re.sub(r"\s+", " ", read(DELIVERY_MD))
    assert "~/Documents/<automatic-category>/<slug>/<slug>-vNNN.pdf" in delivery, (
        "delivery.md must keep the automatic versioned PDF delivery path"
    )


def test_skill_preserves_authority_and_visual_gates(skill: str) -> None:
    """The intake/publication rewrite must not weaken the other gates."""
    for token in (
        "VISUAL_PASS",
        "AUDITOR_PRECHECK",
        "READY_TO_SUBMIT",
        "REVIEW_REQUIRED",
        "VISUAL_FAIL",
    ):
        assert token in skill, f"SKILL.md must preserve the {token} gate"
    lowered = re.sub(r"\s+", " ", plain(skill)).lower()
    assert "visual direction changes hierarchy and composition" in lowered, (
        "visual semantics must survive the repurposed intake confirmation"
    )
    assert "never fall back to route a" in lowered or "no default document type" in lowered, (
        "the document-type gate must survive the repurposed intake confirmation"
    )


# --------------------------------------------------------------------------
# 8.1 — forbidden behavior
# --------------------------------------------------------------------------


def test_depth_or_length_is_not_a_mandatory_question(intake: str) -> None:
    lowered = intake.lower()
    assert "must not" in lowered
    assert re.search(r"(length|depth|extension)", lowered), (
        "intake must explicitly rule out a mandatory length/depth question"
    )


def test_no_sistemas_operativos_fallback() -> None:
    """The old rule 'Without one, use the Sistemas Operativos format.' is gone.

    The profile file itself may name the course; nothing else may.
    """
    for path in SKILL_ROOT.rglob("*.md"):
        if path.parent.name == "profiles":
            continue
        assert "Sistemas Operativos" not in path.read_text(encoding="utf-8"), (
            f"{path.name} still carries the Sistemas Operativos fallback"
        )


def test_unl_is_not_a_default_or_fallback(skill: str, routing: str) -> None:
    combined = (skill + routing).lower()
    assert "never a silent fallback" in combined or "never fall back" in combined, (
        "Route E must not degrade into the academic route"
    )
    assert "no default document type" in combined


def test_format_request_does_not_imply_academic(skill: str) -> None:
    assert re.search(
        r"pdf or docx is a format signal only", skill, re.IGNORECASE
    ), "asking for PDF/DOCX must never imply a university shell"


@pytest.mark.parametrize("path", ROUTE_AGNOSTIC_FILES, ids=lambda p: p.name)
def test_unl_shell_not_loaded_outside_academic_route(path: Path) -> None:
    text = read(path)
    assert "unl-shell" not in text, (
        f"{path.name} loads on every route and must not reference unl-shell.md"
    )


def test_routing_confines_unl_shell_to_the_academic_section() -> None:
    """In routing.md, unl-shell.md may only appear under Route A."""
    for heading, body in sections(read(ROUTING_MD)).items():
        if "unl-shell" not in body:
            continue
        assert re.search(r"route a|academic", heading, re.IGNORECASE), (
            f"unl-shell.md referenced under non-academic section {heading!r}"
        )


def test_skill_unl_references_are_route_qualified(skill: str) -> None:
    """In SKILL.md every unl-shell mention carries an explicit Route A qualifier.

    SKILL.md is a flat operational document with no academic-only section, so
    each individual line has to state the restriction itself.
    """
    for line in skill.splitlines():
        if "unl-shell" not in line:
            continue
        assert re.search(r"route a|academic|only", line, re.IGNORECASE), (
            f"unqualified unl-shell reference in SKILL.md: {line!r}"
        )


# --------------------------------------------------------------------------
# 8.1 — authority boundary
# --------------------------------------------------------------------------


def test_scripts_never_grant_visual_pass(skill: str) -> None:
    assert re.search(
        r"no script,? validator,? or auditor ever grants `?VISUAL_PASS`?",
        skill,
        re.IGNORECASE,
    ), "SKILL.md must state that no script grants VISUAL_PASS"


def test_visible_evidence_overrides_automation() -> None:
    gates = read(GATES_MD)
    assert "Visible evidence overrides automation" in gates


# --------------------------------------------------------------------------
# Hardened composition gates
# --------------------------------------------------------------------------


def test_orphan_heading_rule_is_quantified() -> None:
    gates = read(GATES_MD).lower()
    assert "orphan" in gates
    assert "two lines" in gates, "the orphan-heading rule must be measurable"


def test_whitespace_thresholds_are_quantified() -> None:
    gates = read(GATES_MD)
    assert "20%" in gates, "semi-empty page threshold must be explicit"
    assert "40%" in gates, "lower-page emptiness threshold must be explicit"


def test_wide_table_split_is_documented() -> None:
    gates = read(GATES_MD)
    assert "Acceptance criterion" in gates, (
        "the requirement-table split must be documented to avoid six columns"
    )


def test_diagrams_must_be_module_specific() -> None:
    gates = read(GATES_MD)
    assert "Validación correcta" in gates, (
        "the generic decision node must be named as a rejection criterion"
    )
    for role in ("external service", "retry", "final state"):
        assert role in gates.lower(), (
            f"diagrams must visually differentiate {role!r}"
        )


# --------------------------------------------------------------------------
# Clean-delivery contract
# --------------------------------------------------------------------------


def test_clean_delivery_keeps_evidence_out_of_delivery_folder() -> None:
    text = read(DELIVERY_MD)
    assert "pdfs only" in text.lower(), (
        "the delivery folder must be limited to clean PDFs"
    )
    for forbidden in ("manifest", "report.yml", "sources.bib", "audit"):
        assert forbidden in text.lower(), (
            f"delivery.md must forbid {forbidden!r} in the delivery folder"
        )


def test_clean_delivery_destination_is_automatic_and_versioned() -> None:
    text = read(DELIVERY_MD)
    assert "no `delivery_pdf:`" in text.lower()
    assert "~/documents/<automatic-category>/<slug>/" in text.lower()
    assert "~/documents/academicos/<subject-slug>/<slug>/" in text.lower()
    assert "v001" in text.lower()
    assert "sha-256" in text.lower()


def test_clean_delivery_scopes_academic_delivery_by_canonical_subject() -> None:
    """T1: every confirmed academic subject scopes delivery; no route falls back."""
    text = read(DELIVERY_MD)
    lowered = re.sub(r"\s+", " ", text.lower())
    assert "`output_router`" in text, (
        "the subject slug must name the shared output_router vocabulary"
    )
    assert "stable ascii slug" in lowered, (
        "a newly named course must get its own level without registration"
    )
    assert "never invent a fallback bucket" in lowered, (
        "a missing subject must not create a generic folder"
    )
    assert "Non-academic routes are unchanged" in text, (
        "the flat category layout must be stated as unchanged for other routes"
    )


def test_course_folder_git_ownership_is_documented() -> None:
    """T1: the delivery tree explains Git ownership and the PDF-only rule."""
    text = read(DELIVERY_MD)
    lowered = re.sub(r"\s+", " ", text.lower())
    assert "do not run any git command (`git init`" in lowered
    assert "`git push`" in lowered
    assert "the user owns every git operation" in lowered
    assert "at the course root" in lowered, "git metadata stays above per-document folders"
    assert "per-document folder stays pdfs-only" in lowered


def test_clean_delivery_bibliography_is_a_declared_opt_in() -> None:
    """T2: the .bib is opt-in, evidence-bound, set-exact, and never auto-copied."""
    text = read(DELIVERY_MD)
    lowered = re.sub(r"\s+", " ", text.lower())

    assert "deliver_bibliography: true" in lowered
    assert "never travels merely because it exists" in lowered, (
        "a sources.bib for citations alone never becomes a deliverable"
    )
    assert "bibliography_sha256" in text, "validation and final-review bind the declared bytes"
    assert "a partial pair is never a delivery" in lowered
    assert "<slug>-vnnn.bib" in lowered, "the pair is versioned like the PDF"
    assert "symlink escapes refuse" in lowered, "unsafe declared sources fail closed"


def test_skill_references_clean_delivery_contract(skill: str) -> None:
    assert "references/delivery.md" in skill, (
        "SKILL.md must reference the delivery contract"
    )


def test_automatic_documents_publication_requires_a_confirmed_pdf() -> None:
    combined = "\n".join(read(path) for path in (SKILL_MD, DELIVERY_MD))
    assert "confirmed PDF output" in combined
    assert "hash before validation" in combined
    assert "immediately before publication" in combined


def test_generation_does_not_publish_and_delivery_is_explicit() -> None:
    """#22: build_report_auto never publishes; deliver_report.py is the only route."""
    delivery = read(DELIVERY_MD)
    assert "automatically publishes" not in delivery, (
        "generation must not be described as publishing to ~/Documents"
    )
    assert "tools/deliver_report.py" in delivery, (
        "the deliver phase must name its executable entrypoint"
    )
    assert "Generation never publishes" in delivery
    assert "validation.yml" in delivery, (
        "delivery must require the validation receipt bound to the exact PDF bytes"
    )
    assert "does not publish" in read(GATES_MD)


def test_publication_gated_on_approval() -> None:
    gate_rows = [
        line
        for line in read(GATES_MD).splitlines()
        if "VERSIONED_PDF_PUBLISHED_OR_REUSED" in line
    ]
    assert gate_rows, (
        "the gate table must keep the VERSIONED_PDF_PUBLISHED_OR_REUSED gate"
    )
    assert any("APPROVAL_CURRENT" in row for row in gate_rows), (
        "VERSIONED_PDF_PUBLISHED_OR_REUSED must list APPROVAL_CURRENT as a precondition"
    )
    # Independent signal: the delivery prose must also name the approval marker gate.
    delivery = read(DELIVERY_MD)
    assert "approval.yml" in delivery, (
        "the delivery prose must name the approval marker"
    )


# --------------------------------------------------------------------------
# Cross-skill references
# --------------------------------------------------------------------------


def test_research_protocol_names_evidence_path() -> None:
    handoff = sections(read(RESEARCH_MD))["5. Package the handoff"]
    assert (
        "$REPORT_CONTENT_ROOT/reports/<work-folder>/research/evidence-matrix.md"
        in handoff
    ), "§5 must name the evidence-matrix artifact path"
    lowered = plain(handoff).lower()
    assert "pre-document evidence" in lowered, (
        "the research package must be labeled pre-document evidence"
    )
    assert "never confirmed intake" in lowered, (
        "the research package must never be described as confirmed intake"
    )
    assert "confirmed document intake" not in lowered, (
        "§5 must drop the old confirmed-intake phrasing"
    )


# --------------------------------------------------------------------------
# C1 #8 — identity contract
# --------------------------------------------------------------------------


def test_intake_requires_concrete_identity() -> None:
    """Intake must collect concrete identity for individual or group reports."""
    intake_text = plain(read(INTAKE_MD)).lower()
    assert "identity confirmation" in intake_text, (
        "intake must have an identity confirmation"
    )
    assert "placeholder" in intake_text, "intake must reject placeholder identity"
    assert "individual" in intake_text, "intake must cover individual reports"
    assert "group" in intake_text, "intake must cover group reports"
    assert "complete membership" in intake_text, (
        "group reports must carry the complete membership list"
    )


def test_intake_never_prompts_for_paralelo() -> None:
    """The intake must state that Paralelo is data, never a question."""
    intake_text = plain(read(INTAKE_MD)).lower()
    assert "paralelo" in intake_text, "the no-prompt paralelo rule must be documented"
    assert "never prompts" in intake_text, (
        "the intake must state that paralelo is never a question"
    )


def test_unl_shell_paralelo_defaults_to_a_with_data_override() -> None:
    """unl-shell.md: A is the default; explicit report.yml data overrides it."""
    unl = plain(read(UNL_MD)).lower()
    assert "paralelo" in unl
    assert "por defecto" in unl, "A must be documented as the default value"
    assert "metadata.parallel" in unl, (
        "the explicit assignment override must be documented"
    )
    assert "unless assignment says otherwise" not in unl, (
        "the old conditional fallback wording must be gone"
    )


# --------------------------------------------------------------------------
# T7 — the shipped instructions must stand without session context
# --------------------------------------------------------------------------


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
AUTOMATION_MD = ROUTING_MD  # roots and interpreter selection live in routing.md


def _tools_module(name: str):
    """Import a real ``tools/`` module so documented text is checked against code."""
    import sys

    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))
    import importlib

    return importlib.import_module(name)


def test_automation_contract_resolves_both_roots_without_a_hardcoded_home() -> None:
    """T7: the tool root and the content root are discovered, never assumed."""
    automation = read(AUTOMATION_MD)

    assert "REPORT_AUTOMATION_ROOT" in automation, "the tool/repository root must be named"
    assert "REPORT_CONTENT_ROOT" in automation, "the content root must be named"
    assert "report_config" in automation and "CONTENT_ROOT" in automation, (
        "the content root must be resolved through the loader the tools actually use"
    )
    assert not re.search(r"/home/[a-z0-9._-]+/", automation), (
        "no personal absolute path may be baked into the contract"
    )


def test_automation_contract_commands_are_absolute_and_cwd_independent() -> None:
    """T7: every canonical command names its interpreter, tool and folder absolutely."""
    automation = "\n".join(read(path) for path in (ROUTING_MD, GATES_MD, DELIVERY_MD))

    assert '"$REPORT_PYTHON"' in automation, (
        "commands must name the selected dependency-equipped interpreter"
    )
    for script in (
        "build_report_auto.py",
        "validate_report.py",
        "visual_pdf_auditor.py",
        "deliver_report.py",
    ):
        assert f'"$REPORT_AUTOMATION_ROOT/tools/{script}"' in automation, script
    assert '"$REPORT_CONTENT_ROOT/reports/<work-folder>/"' in automation, (
        "the report folder must be passed as an absolute content-root path"
    )
    assert 'cd "$REPORT_AUTOMATION_ROOT"' not in automation, (
        "no command may depend on a working directory"
    )


def test_clean_delivery_never_implies_automatic_publication() -> None:
    """T2/T7: generation never publishes; delivery is the explicit entrypoint."""
    text = read(DELIVERY_MD)
    flat = re.sub(r"\s+", " ", text).lower()

    assert "automatically published" not in flat, (
        "clean-delivery must not read as automatic publication after validation"
    )
    assert "generation never publishes" in flat
    assert "deliver_report.py" in text, "the explicit deliver entrypoint must be named"
    assert "approval.yml" in text, "delivery must restate the current-marker precondition"


def intake_record_block() -> str:
    """The one canonical ``report.yml`` record block documented in the intake."""
    blocks = re.findall(r"```yaml\n(.*?)```", read(INTAKE_MD), re.DOTALL)
    assert blocks, "data.md must show the report.yml record as a ```yaml block"
    assert len(blocks) == 1, "keep exactly one canonical record block so copies cannot drift"
    return blocks[0]


def test_documented_intake_record_loads_with_the_keys_the_pipeline_consumes(
    tmp_path: Path,
) -> None:
    """T7: the documented keys are the real ones -- proven by loading the record."""
    import yaml

    load_report_config = _tools_module("report_config").load_report_config
    record = yaml.safe_load(intake_record_block())

    folder = tmp_path / "informe-tecnico"
    folder.mkdir()
    (folder / "body.md").write_text("# Cuerpo\n", encoding="utf-8")
    (folder / "report.yml").write_text(intake_record_block(), encoding="utf-8")

    config = load_report_config(folder)

    assert config.route == record["route"] == "project"
    assert config.output_format == record["output"] == "pdf"
    for key in ("title", "student", "date", "audience", "purpose", "visual_direction"):
        assert str(config.metadata.get(key) or "").strip(), (
            f"metadata.{key} must survive the real loader"
        )
    for academic_only in ("subject", "teacher"):
        assert not record["metadata"].get(academic_only), (
            f"a non-academic record must not invent metadata.{academic_only}"
        )


def test_documented_intake_record_keeps_cover_at_top_level(tmp_path: Path) -> None:
    """T7: ``cover:`` is a top-level key; nesting it under ``metadata`` would be ignored."""
    import yaml

    template_key_for = _tools_module("build_latex_report").template_key_for
    load_report_config = _tools_module("report_config").load_report_config
    record = yaml.safe_load(intake_record_block())

    assert "cover" not in record["metadata"], "cover must not be nested under metadata"
    assert "cover" in record and record["cover"], "the record must show the top-level cover block"

    folder = tmp_path / "informe-tecnico"
    folder.mkdir()
    (folder / "body.md").write_text("# Cuerpo\n", encoding="utf-8")
    (folder / "report.yml").write_text(intake_record_block(), encoding="utf-8")
    config = load_report_config(folder)

    # Route "project" defaults to no cover; the explicit top-level block must win.
    assert config.cover_value("required") is True, (
        "an explicit top-level cover block must override the route default"
    )
    assert config.cover_value("body_starts_on_page") == 2
    assert config.cover_value("logo_required") is True
    assert template_key_for(config) == record["template"], (
        "an explicitly recorded template must be the one the renderer resolves"
    )


def test_workflow_intake_reference_names_the_record_keys() -> None:
    """The orchestrator reference must name the same keys the record contract defines."""
    import yaml

    record = yaml.safe_load(intake_record_block())
    workflow = read(INTAKE_MD)

    for key in record["metadata"]:
        assert f"metadata.{key}" in workflow, f"the workflow intake must name metadata.{key}"
    for top_level in ("route:", "output:", "template:", "cover:"):
        assert f"`{top_level}`" in workflow, f"the workflow intake must name the top-level {top_level}"
    assert "top-level" in workflow.lower(), "cover placement must be stated, not implied"


def test_skill_points_at_the_route_derived_rendering_defaults(skill: str) -> None:
    """T4/T7: the always-read skill must not let a fresh run assume the academic shell."""
    flat = re.sub(r"\s+", " ", plain(skill)).lower()

    assert "references/routing.md" in skill, "the routing reference must be linked"
    assert "route-derived" in flat or "derived from the confirmed route" in flat, (
        "the skill must state that rendering defaults come from the confirmed route"
    )
    assert "explicit" in flat, "an explicit report.yml option must still win"


def test_automation_contract_separates_the_source_checkout_from_the_interpreter() -> None:
    """T7 blocker 1: the tool checkout and the interpreter are chosen separately.

    `REPORT_AUTOMATION_ROOT` owns `tools/`; the dependency-equipped interpreter is
    `REPORT_PYTHON`, and it is never assumed to sit next to those tools (a feature
    worktree has tools but no `.venv`).
    """
    automation = read(AUTOMATION_MD)
    lowered = automation.lower()

    assert "REPORT_PYTHON" in automation
    assert re.search(r"REPORT_PYTHON=", automation), "REPORT_PYTHON must be assigned, not implied"
    assert '"$REPORT_AUTOMATION_ROOT/.venv/bin/python"' not in automation, (
        "the interpreter must not be hardwired to a .venv beside the tools"
    )
    assert "worktree" in lowered and ".venv" in lowered, (
        "the worktree/shared-interpreter case must be explained"
    )
    assert "REPORT_CONTENT_ROOT" in automation and "report_config" in automation


def bash_block(text: str, marker: str) -> str:
    """The fenced bash block containing ``marker``."""
    blocks = re.findall(r"```bash\n(.*?)```", text, re.DOTALL)
    matches = [block for block in blocks if marker in block]
    assert len(matches) == 1, f"expected exactly one bash block containing {marker!r}"
    return matches[0]


def test_documented_root_discovery_snippet_runs_from_an_unrelated_cwd(tmp_path: Path) -> None:
    """T7 blocker 1: execute the documented snippet exactly, no colocated `.venv` needed.

    The source root is this checkout (in the stabilization worktree it has `tools/`
    and no `.venv`), the interpreter is supplied explicitly through `REPORT_PYTHON`,
    and the run happens from an unrelated cwd. The snippet must print the loader's
    content root and must still honour an exported `REPORT_CONTENT_ROOT`.
    """
    snippet = bash_block(read(AUTOMATION_MD), "REPORT_CONTENT_ROOT=")
    assert "<absolute path of the checkout that owns tools/>" in snippet, (
        "the snippet must keep exactly one documented placeholder to fill in"
    )
    script = snippet.replace("<absolute path of the checkout that owns tools/>", str(REPO_ROOT))
    interpreter = REPO_ROOT / ".venv" / "bin" / "python"
    if not interpreter.is_file():  # the worktree case: no .venv beside tools/
        interpreter = Path(sys.executable)
    env = {"PATH": os.environ.get("PATH", ""), "REPORT_PYTHON": str(interpreter)}

    run = subprocess.run(
        ["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True
    )

    assert run.returncode == 0, run.stderr
    expected = _tools_module("report_config").resolve_content_root({})
    assert run.stdout.strip().splitlines()[-1] == f"REPORT_CONTENT_ROOT={expected}"

    override = tmp_path / "content override"
    overridden = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        env={**env, "REPORT_CONTENT_ROOT": str(override)},
        capture_output=True,
        text=True,
    )

    assert overridden.returncode == 0, overridden.stderr
    assert overridden.stdout.strip().splitlines()[-1] == f"REPORT_CONTENT_ROOT={override}"


# --------------------------------------------------------------------------
# C2 #12 — teacher-required structure contract
# --------------------------------------------------------------------------


def test_intake_documents_structure_confirmation() -> None:
    """Intake must cover combined sources, mandatory criteria, optional
    limits, proposal/confirmation, and blocked downstream phases."""
    intake_text = plain(read(INTAKE_MD))
    intake_flat = re.sub(r"\s+", " ", intake_text).lower()
    assert "structure confirmation" in intake_flat
    assert "combine requirements from every supplied source" in intake_flat
    assert "contradiction between" in intake_flat, (
        "conflicting requirements from different sources must block confirmation"
    )
    assert "stay entirely optional" in intake_flat, (
        "quantitative limits must be documented as optional, never inferred"
    )
    assert "provisional structure" in intake_flat
    assert "stay blocked" in intake_flat, (
        "downstream phases must be documented as blocked while unconfirmed"
    )
    assert "reconfirmation" in intake_flat
