"""Static contract tests for the academic-report-flow skill.

These tests read the skill markdown as data. They never run the pipeline: they
prove the orchestrator keeps a single route loop, one routing table that maps
every phase to one of six stage references, a portable ASCII status template,
and the content-first prose rules (research gate, verbatim review loop,
report-only content check, single format question).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "skills" / "academic-report-flow"
SKILL_MD = SKILL_ROOT / "SKILL.md"
REFS = SKILL_ROOT / "references"
ROUTING_MD = REFS / "routing.md"
DATA_MD = REFS / "data.md"
CONTENT_MD = REFS / "content.md"
APPROVAL_MD = REFS / "approval.md"
PRODUCTION_MD = REFS / "production.md"
DELIVERY_MD = REFS / "delivery.md"
TOOLS_DIR = ROOT / "tools"


def tool_doc_status():
    """Import the real ``tools/doc_status.py`` so documented text cannot drift."""
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))
    import doc_status

    return doc_status

PHASES = (
    "intake",
    "research",
    "plan",
    "draft",
    "verify",
    "approval",
    "format",
    "typeset",
    "generate",
    "validate",
    "review",
    "deliver",
)
STATE_TOKENS = ("done", "current", "pending", "blocked")
EXECUTORS = ("academic-report-flow", "research-workflow")

# Stage reference each phase loads, the executor and the single artifact it
# produces, exactly as the routing table declares them.
PHASE_REFERENCE = {
    "intake": "data.md",
    "research": "content.md",
    "plan": "content.md",
    "draft": "content.md",
    "approval": "approval.md",
    "verify": "production.md",
    "format": "approval.md",
    "typeset": "production.md",
    "generate": "production.md",
    "validate": "production.md",
    "review": "delivery.md",
    "deliver": "delivery.md",
}
PHASE_EXECUTOR = {
    "research": "research-workflow",
    "approval": "human gate",
    "review": "human gate",
}
PHASE_ARTIFACT = {
    "intake": "reports/<wf>/report.yml",
    "research": "reports/<wf>/sources.bib",
    "plan": "reports/<wf>/rubric.yml",
    "draft": "reports/<wf>/body.md",
    "approval": "reports/<wf>/approval.yml",
    "verify": "reports/<wf>/content-check.yml",
    "format": "reports/<wf>/report.yml",
    "typeset": "reports/<wf>/body.typeset.md",
    "generate": "outputs/<materia>/<final>.pdf",
    "validate": "reports/<wf>/validation.yml",
    "review": "reports/<wf>/final-review.yml",
    "deliver": "~/Documents/<category>/[<subject-slug>/]<slug>/<slug>-vNNN.pdf",
}
REMOVED_REFERENCES = (
    "automation-contract", "quality-gates", "clean-delivery", "document-routing",
    "routing-loop", "intake", "research", "plan", "draft", "verify", "format",
    "generate", "validate", "review", "deliver", "document-intake", "preview",
)


def read(path: Path) -> str:
    assert path.is_file(), f"missing required contract file: {path}"
    return path.read_text(encoding="utf-8")


def frontmatter(text: str) -> str:
    parts = text.split("---", 2)
    assert len(parts) == 3, "SKILL.md must open with a frontmatter block"
    return parts[1]


def fenced_blocks(text: str) -> list[str]:
    return re.findall(r"```[^\n]*\n(.*?)```", text, re.DOTALL)


def human_template(text: str) -> str:
    for block in fenced_blocks(text):
        if "**Summary**" in block and "**Next**:" in block:
            return block
    raise AssertionError("SKILL.md must embed the fenced human status block template")


def test_verify_uses_one_independent_verifier_without_drafting_conversation() -> None:
    text = read(PRODUCTION_MD)
    assert "--verify-brief" in text
    assert "independent read-only verifier" in text
    assert "Do not pass the drafting conversation" in text
    assert "--judge-brief" not in text and "two independent" not in text.lower()


def test_verify_requires_one_verifier_matrix_and_quoted_evidence() -> None:
    flat = re.sub(r"\s+", " ", read(PRODUCTION_MD))
    assert "ONE independent read-only verifier" in flat
    assert "verification.yml" in flat
    assert "--verification verification.yml" in flat
    assert "requirement" in flat and "evidence" in flat and "found|missing" in flat
    assert "exact quote" in flat and "downgraded to `missing`" in flat
    assert "links_resolve" in flat and "unmapped_paragraphs" in flat
    assert "never scores" in flat
    assert "--judgments" not in flat and "judgments-a.yml" not in flat


def test_required_files_and_frontmatter() -> None:
    text = read(SKILL_MD)
    meta = frontmatter(text)
    assert re.search(r"^name:\s*academic-report-flow\s*$", meta, re.MULTILINE)
    assert re.search(r'^description:\s*".*Trigger:', meta, re.MULTILINE)
    assert re.search(r"^license:\s*Apache-2\.0\s*$", meta, re.MULTILINE)
    for key in ("author", "version", "scope"):
        assert re.search(rf"^\s+{key}:\s*\S", meta, re.MULTILINE), f"metadata.{key} missing"
    for name in sorted(set(PHASE_REFERENCE.values()) | {"routing.md"}):
        assert f"references/{name}" in text, f"SKILL.md must index references/{name}"


def test_routing_loop_and_table_contract() -> None:
    assert "doc_status -> next -> reference -> delegate -> re-run" in re.sub(
        r"\s+", " ", read(SKILL_MD)
    )
    text = read(ROUTING_MD)
    for phase in PHASES:
        row = re.search(rf"^\|\s*{phase}\s*\|(.*)$", text, re.MULTILINE)
        assert row, f"routing row {phase} missing"
        assert f"`{PHASE_REFERENCE[phase]}`" in row.group(1), f"{phase} must route to {PHASE_REFERENCE[phase]}"
    for executor in EXECUTORS:
        assert executor in text, f"routing table must name {executor}"
    assert "human gate" in text.lower(), "the approval row must identify the human gate"


def test_status_template_contract() -> None:
    block = human_template(read(ROUTING_MD))
    assert all(ord(char) < 128 for char in block), "template must be ASCII only"
    assert "|" not in block, "template must not use markdown tables"
    assert not re.search(r"^#{3,}", block, re.MULTILINE), "template must not nest headers"

    route_lines = [line for line in block.splitlines() if line.startswith("Route: ")]
    assert len(route_lines) == 1, "exactly one route line"
    assert route_lines[0] == (
        "Route: intake > research > [plan] > draft > verify > approval > format"
        " > typeset > generate > validate > review > deliver"
    )
    brackets = re.findall(r"\[([a-z]+)\]", route_lines[0])
    assert len(brackets) == 1 and brackets[0] in PHASES, "exactly one bracketed phase"
    route_body = route_lines[0].split("Route: ", 1)[1].replace("[", "").replace("]", "")
    assert route_body.split(" > ") == list(PHASES), "route must list every phase in order"

    assert block.splitlines()[0].startswith("**Gate**: ")
    assert block.index("**Gate**:") < block.index("**Summary**"), "gate line must be front-loaded"

    summary = block.split("**Summary**", 1)[1].split("**Next**:", 1)[0]
    bullets = re.findall(r"^- ([a-z]+): ([a-z]+)", summary, re.MULTILINE)
    assert [name for name, _ in bullets] == list(PHASES)
    assert {state for _, state in bullets} <= set(STATE_TOKENS)

    assert re.search(r"^\*\*Next\*\*: [a-z]+", block, re.MULTILINE), "closing Next line missing"


def test_status_template_gate_is_phase_projected_not_approval_frontloaded() -> None:
    """T3/T7: the documented gate is the focus phase's own gate, never approval.

    The embedded block claims to be the exact human output for its state, so it is
    compared against the real derivation instead of a hand-written string.
    """
    doc_status = tool_doc_status()
    block = human_template(read(ROUTING_MD))
    gate_line = next(line for line in block.splitlines() if line.startswith("**Gate**: "))

    expected = "plan pending - " + doc_status._guidance("plan", Path("<report-folder>"))

    assert gate_line == f"**Gate**: {expected}"
    assert "approval pending" not in gate_line, "the approval front-load must stay gone"


def test_status_template_next_line_matches_the_tool_guidance() -> None:
    """The documented ``**Next**`` line is the tool's own guidance sentence."""
    doc_status = tool_doc_status()
    block = human_template(read(ROUTING_MD))
    next_line = next(line for line in block.splitlines() if line.startswith("**Next**: "))

    assert next_line == (
        "**Next**: plan - " + doc_status._guidance("plan", Path("<report-folder>"))
    )


def test_status_template_gate_guidance_is_ascii_and_absolute() -> None:
    """The documented human block stays ASCII and names real, absolute entrypoints."""
    doc_status = tool_doc_status()
    block = human_template(read(ROUTING_MD))

    assert all(ord(char) < 128 for char in block)
    for phase, script in (("generate", "build_report_auto.py"), ("deliver", "deliver_report.py")):
        entrypoint = doc_status.ROOT / "tools" / script
        assert entrypoint.is_file(), "documented entrypoints must exist"
        assert str(entrypoint) in doc_status._guidance(phase, Path("/wf"))


def test_referenced_paths_resolve_and_removed_files_stay_gone() -> None:
    """Every stage reference exists; the pre-consolidation files do not."""
    unresolved = [
        name for name in sorted(set(PHASE_REFERENCE.values()) | {"routing.md"})
        if not (REFS / name).is_file()
    ]
    assert not unresolved, f"unresolved stage references: {', '.join(unresolved)}"
    leftovers = [name for name in REMOVED_REFERENCES if (REFS / f"{name}.md").exists()]
    assert not leftovers, f"removed references are back: {leftovers}"


def test_approval_reference_contract() -> None:
    """Slice 3b-i owns `approval.md`: the human gate, its marker schema, and its refusal to infer consent.

    The reference must exist on disk, name the three marker keys, and state that
    silence or an agent-side inference never produces `approval.yml`.
    """
    text = read(APPROVAL_MD)
    for key in ("body_sha256", "approved_at", "approved_by"):
        assert key in text, f"approval.md must name the marker key {key}"
    assert "preview_sha256" not in text, (
        "approval.md must not bind preview.md any more: the marker binds body.md only"
    )
    assert "approval.yml" in text, "approval.md must name the marker file"
    flat = re.sub(r"\s+", " ", text).lower()
    assert re.search(r"binds?[^.]*body\.md", flat), (
        "approval.md must state that the marker binds body.md"
    )
    for phrase in ("silence", "inferred yes", "agent decision"):
        assert phrase in flat, f"approval.md must name `{phrase}` as a non-consent signal"
    assert re.search(r"never (?:produce|produces|writes|creates)[^.]*approval\.yml", flat), (
        "approval.md must state that a non-explicit answer never produces approval.yml"
    )
    assert "human gate" in flat, "approval.md must identify the human gate"
    assert "lossless" in flat, "approval.md must name the lossless prompt contract"
    assert not re.search(r"^Executor:", text, re.MULTILINE), (
        "approval.md is the human gate: it must declare no executor"
    )


def test_generate_reference_forbids_unapproved_build() -> None:
    """Slice 3b-i extends `production.md` with the approval-done precondition.

    Generation is the first phase that spends build effort on approved bytes, so the
    reference must state the precondition and forbid acting before it holds. T1 cut
    the preview binding: the approval marker binds `body.md` only.
    """
    text = read(PRODUCTION_MD)
    flat = re.sub(r"\s+", " ", text).lower()
    assert "approval: done" in flat, "production.md must name the `approval: done` precondition"
    assert "body_sha256" in flat, "production.md must name the hash the approval binds to"
    assert "body.md" in flat, "production.md must name body.md as the approved input"
    assert "preview" not in flat, "the preview binding is gone: approval binds body.md only"
    assert re.search(r"(?:never|must not|do not|does not) build (?:before|until)", flat), (
        "production.md must forbid building before approval is done"
    )


def test_validate_reference_runs_only_the_fallback_chain() -> None:
    """`production.md` validates documents with the fallback chain only (#79).

    Document creation never uses RDD: the content root is outside the session's
    repository, so an RDD branch always stopped to ask. Validate never probes
    `gentle-ai review mode status`, never asks, and always records
    `mode: fallback`, whatever the global review switch says.
    """
    text = read(PRODUCTION_MD)
    flat = re.sub(r"\s+", " ", text).lower()

    assert "reports/<wf>/validation.yml" in flat, "validate must declare its artifact"
    assert "gentle-ai review mode status" not in flat, (
        "validate must not probe the RDD switch: documents never use RDD"
    )
    assert "mode: rdd|" not in flat and "|rdd" not in flat, (
        "the receipt schema must not offer `mode: rdd`"
    )
    assert "mode: fallback" in flat, (
        "production.md must label the validation chain `mode: fallback`"
    )
    assert re.search(r"never uses? rdd", flat), (
        "production.md must state that document validation never uses RDD"
    )
    assert re.search(r"regardless of [^.]*review switch", flat), (
        "production.md must state the chain runs regardless of the global review switch"
    )
    for step in ("validate_report.py", "visual_pdf_auditor.py", "semantic"):
        assert step in flat, f"production.md must name the fallback step `{step}`"
    gates = ("BUILD_PASS", "VALIDATION_PASS", "VISUAL_PASS", "HUMAN_REVIEW", "READY_TO_SUBMIT")
    for gate in gates:
        assert gate in text, f"production.md must name the gate {gate}"
    assert "backups/quality_report.md" in flat, (
        "production.md must name the fallback evidence path"
    )
    assert "next: validate" in flat, "production.md must state the phase it owns"
    assert re.search(r"mode: fallback[^.]*backups/quality_report\.md", flat), (
        "production.md must couple the fallback receipt mode to its evidence path"
    )


def test_routing_table_names_executor_and_single_artifact_per_phase() -> None:
    """Each phase row declares one executor and exactly one artifact.

    `doc_status` derivation keeps reading exactly the path each phase promises;
    self-run phases name this skill, the human gates declare no executor.
    """
    text = read(ROUTING_MD)
    for phase in PHASES:
        row = re.search(rf"^\|\s*{phase}\s*\|(.*)\|\s*$", text, re.MULTILINE).group(1)
        cells = [cell.strip() for cell in row.split("|")]
        _reference, executor, artifact = cells
        assert PHASE_EXECUTOR.get(phase, "academic-report-flow") in executor, phase
        assert artifact == f"`{PHASE_ARTIFACT[phase]}`", phase


def test_preview_reference_is_gone() -> None:
    """new-report-flow T5: the preview phase no longer exists in the route."""
    assert not (REFS / "preview.md").exists(), (
        "preview.md must be deleted: the draft is the only thing the user reviews"
    )
    assert "references/preview.md" not in read(SKILL_MD), (
        "SKILL.md must not route to the removed preview reference"
    )


def test_new_phase_references_state_their_intent() -> None:
    """T5: plan/verify/format/review are minimal self-executed phase references.

    Each names its marker contract and the one tool that derives its state; the
    full prose rewrite is T6.
    """
    expected_tokens = {
        "plan": ("rubric.yml", "rubric_plan.py"),
        "verify": ("content-check.yml", "content_check.py"),
        "format": ("format:", "APE"),
        "review": ("final-review.yml", "pdf_sha256"),
    }
    for phase, tokens in expected_tokens.items():
        text = read(REFS / PHASE_REFERENCE[phase])
        flat = re.sub(r"\s+", " ", text)
        for token in tokens:
            assert token in flat, f"references/{phase}.md must name `{token}`"


def test_draft_reference_names_authoring_format_and_single_artifact() -> None:
    """`content.md` names the body authoring format and produces exactly one artifact.

    The body is Markdown with Pandoc-style `[@key]` citations resolved against
    `sources.bib` and `![caption](path)` figures; the phase never writes the
    approval marker.
    """
    text = read(CONTENT_MD)
    for token in ("[@", "![", "sources.bib"):
        assert token in text, f"content.md must name the authoring format token {token}"
    flat = re.sub(r"\s+", " ", text).lower()
    assert "exactly one artifact" in flat, "content.md must state it produces exactly one artifact"
    assert re.search(r"never[^.]*writes?[^.]*approval\.yml", flat), (
        "content.md must state it never writes approval.yml"
    )


# --------------------------------------------------------------------------
# T7 — instructions sufficient without session context
# --------------------------------------------------------------------------


def test_research_reference_names_the_five_source_gate() -> None:
    """new-report-flow T2: research is a hard gate, never a skippable phase.

    The reference must name the per-document BibTeX artifact, the five-source
    minimum, and the forbidden web-only types -- and the recorded skip path
    must be gone.
    """
    text = read(CONTENT_MD)
    flat = re.sub(r"\s+", " ", text).lower()

    assert "sources.bib" in flat, "the phase must name the per-document BibTeX file"
    assert re.search(r"at least 5\b", flat), "the reference must state the five-source minimum"
    assert "@misc" in flat and "@online" in flat, (
        "the reference must name the web-only types that never count"
    )
    assert "research: skipped" not in flat, "the recorded skip decision must be gone"
    assert "source_library.py" in flat, (
        "the reference must still name the local source inventory tool"
    )
    assert "inspected" in flat, "only inspected local sources are bibliography-eligible"


def test_intake_reference_states_the_record_keys_without_inventing_a_schema() -> None:
    """The workflow intake must name the existing keys, not a parallel vocabulary."""
    text = read(DATA_MD)
    flat = re.sub(r"\s+", " ", text)

    for key in ("metadata.audience", "metadata.purpose", "metadata.visual_direction"):
        assert key in flat, f"the intake record must place {key} in the consumed metadata map"
    assert "`cover:`" in flat, "cover is a top-level key"
    assert "```yaml" in text, "the report.yml record lives in the same unified intake file"


def test_generate_and_deliver_references_print_runnable_absolute_commands() -> None:
    """Both phase references must show a command that runs from any working directory."""
    for name, path, script in (
        ("generate", PRODUCTION_MD, "build_report_auto.py"),
        ("deliver", DELIVERY_MD, "deliver_report.py"),
    ):
        text = read(path)
        flat = re.sub(r"\s+", " ", text)

        assert '"$REPORT_PYTHON"' in flat, (
            f"{name}.md must run under the selected interpreter, not one colocated with tools/"
        )
        assert f'"$REPORT_AUTOMATION_ROOT/tools/{script}"' in flat, name
        assert '"$REPORT_CONTENT_ROOT/reports/<work-folder>/"' in flat, name
        assert '"$REPORT_AUTOMATION_ROOT/.venv/bin/python"' not in flat, (
            f"{name}.md must not assume a .venv beside the tools"
        )
        assert not re.search(r"python tools/", flat), (
            f"{name}.md must not leave the tool path relative to an assumed cwd"
        )


def test_deliver_reference_names_the_executable_and_the_receipt_precondition() -> None:
    """T2/T7: deliver names the entrypoint, its receipt gate, and never auto-publishes."""
    flat = re.sub(r"\s+", " ", read(DELIVERY_MD))

    assert '"$REPORT_AUTOMATION_ROOT/tools/deliver_report.py"' in flat
    assert "validation.yml" in flat
    assert "approval.yml" in flat
    assert "never publishes" in flat


def test_deliver_reference_declares_the_subject_scoped_academic_layout() -> None:
    """T1: the academic route scopes delivery by the confirmed subject slug."""
    flat = re.sub(r"\s+", " ", read(DELIVERY_MD))

    assert "~/Documents/Academicos/<subject-slug>/<slug>/" in flat
    assert "`output_router`" in flat, "the subject slug names the shared vocabulary"
    assert "stable ASCII slug" in flat, "a newly named course gets its own level"
    assert "only a missing subject has no level" in flat, "no generic fallback bucket"


def test_deliver_reference_never_touches_git_or_non_pdf_files() -> None:
    """T1: delivery writes only the versioned PDF and never runs Git itself."""
    flat = re.sub(r"\s+", " ", read(DELIVERY_MD))

    assert "Do not write any file other than the versioned PDF" in flat
    assert "Do not run any Git command" in flat
    assert "`git push`" in flat
    assert "Git metadata stays at the course root" in flat


def test_deliver_reference_treats_the_bib_as_a_declared_opt_in() -> None:
    """T2: the .bib ships only when declared, bound to evidence, never auto-copied."""
    flat = re.sub(r"\s+", " ", read(DELIVERY_MD))

    assert "deliver_bibliography: true" in flat
    assert "<slug>-vNNN.bib" in flat, "the pair is versioned like the PDF"
    assert "bibliography_sha256" in flat, "both evidence markers bind the declared bytes"
    assert "a partial pair is never a delivery" in flat
    assert "never travels" in flat, "an undeclared sources.bib is never copied"


def test_validate_reference_binds_the_declared_bibliography_bytes() -> None:
    """T2: validate records the exact declared .bib hash after applicable checks."""
    flat = re.sub(r"\s+", " ", read(PRODUCTION_MD))

    assert "bibliography_sha256" in flat
    assert "deliver_bibliography: true" in flat
    assert "written only" in flat and "after the applicable checks pass" in flat
    assert "no" in flat and "production writer" in flat


def test_review_reference_shows_the_declared_bibliography_before_the_ok() -> None:
    """T2: the human reviews the declared .bib alongside the PDF; never auto-granted."""
    flat = re.sub(r"\s+", " ", read(DELIVERY_MD))

    assert "alongside the PDF" in flat
    assert "bibliography_sha256" in flat
    assert "only after that explicit OK" in flat
    assert "never granted automatically" in flat


def test_intake_reference_records_the_bib_request_without_asking() -> None:
    """T2: a supplied .bib requirement is recorded, never asked or gated."""
    flat = re.sub(r"\s+", " ", read(DATA_MD))

    assert "deliver_bibliography: true" in flat
    assert "never asks" in flat, "intake records the supplied request without a new question"
    assert "never adds an approval gate" in flat


# --------------------------------------------------------------------------
# T6 — report-flow-hardening prose contracts
# --------------------------------------------------------------------------


def test_research_verifies_every_bibliography_entry() -> None:
    text = read(CONTENT_MD)
    for phrase in ("verify_sources.py", "VERIFIED", "VERIFIED_WITH_WARNINGS", "MISMATCH", "NOT_FOUND", "NO_IDENTIFIER", "DOI", "ISBN"):
        assert phrase in text
    assert re.search(r"after writing.*sources\.bib.*verify_sources\.py", re.sub(r"\s+", " ", text), re.I)


def test_plan_defines_rubric_tdd_before_drafting() -> None:
    text = re.sub(r"\s+", " ", read(CONTENT_MD))
    for kind in ("heading_present", "contains", "matches", "verbatim_from_guide", "ordered_list", "min_citations", "figure_referenced", "link_present", "keywords_from_section"):
        assert kind in text
    for phrase in ("checks:", "before the draft", "red", "green", "semantic", "format_hint: ape", "fixed"):
        assert phrase in text


def test_draft_runs_mechanical_checks_before_presentation() -> None:
    text = read(CONTENT_MD)
    for phrase in ("every rubric check", "green", "content_check.py", "mechanical", "before presenting"):
        assert phrase in text


def test_approval_batches_literal_orders_and_rechecks() -> None:
    text = re.sub(r"\s+", " ", read(APPROVAL_MD))
    for phrase in ("Batch", "all literal edit orders", "one reading", "verbatim", "only then", "re-approval", "verify", "generate", "validate"):
        assert phrase in text


def test_verify_refuses_drafter_verification_and_stale_marker() -> None:
    text = read(PRODUCTION_MD)
    assert "drafting agent never writes verification.yml" in text
    assert "stale marker" in text and "re-run the verifier" in text


def test_pdf_handoff_opens_the_pdf_automatically() -> None:
    """The handoff is stated once, in the final-review stage that presents the PDF: the PDF opens itself."""
    text = read(DELIVERY_MD)
    for phrase in ("doc_status", "pdf_viewer.py", "exact", "zathura", "internal links", "file://", "never send screenshots"):
        assert phrase.lower() in text.lower(), phrase
    assert "*.pdf" not in text and "set d" not in text
    assert "pdf_viewer.py" not in read(PRODUCTION_MD), "the handoff must not be restated in production.md"


def test_approval_packet_opens_the_fresh_preview() -> None:
    assert "approval_packet.py\" <folder> --open`" in read(APPROVAL_MD)


def test_skill_hard_rules_summarize_four_guards() -> None:
    hard = read(SKILL_MD).split("## Hard Rules", 1)[1].split("## Decision Gates", 1)[0]
    for phrase in ("rubric TDD", "independent verifier", "verified sources", "batched edit orders"):
        assert len([line for line in hard.splitlines() if phrase.lower() in line.lower()]) == 1


# --------------------------------------------------------------------------
# T6 — content-first prose rules
# --------------------------------------------------------------------------


def all_skill_files() -> list[Path]:
    """Every markdown file the academic-report-flow skill loads: SKILL.md plus references."""
    return [SKILL_MD] + sorted(REFS.glob("*.md"))


def test_no_flow_file_mentions_the_removed_preview() -> None:
    """T6: the preview phase and its artifact are gone from every skill file.

    Task 11(a) adds a preview PDF at Decision 2, owned by approval.md alone: it is
    neither a phase nor an artifact, so the guard exempts that one file.
    """
    offenders = [
        str(path.relative_to(SKILL_ROOT))
        for path in all_skill_files()
        if path != APPROVAL_MD and re.search(r"(?<!post-)\bpreview", read(path), re.IGNORECASE)
    ]
    assert offenders == [], f"stale preview mentions remain: {offenders}"


def test_skill_tree_adds_no_detector_or_percentage_gate() -> None:
    """T6 rule 6: the flow has no AI-detector or percentage gate, and never will."""
    offenders = [
        str(path.relative_to(SKILL_ROOT))
        for path in all_skill_files()
        if re.search(r"detector|percent", read(path), re.IGNORECASE)
    ]
    assert offenders == [], f"detector/percentage gate wording in: {offenders}"


def test_intake_reference_asks_only_the_content_first_minimum() -> None:
    """T6 rule 1: intake collects identity plus guide material, never formatting."""
    flat = re.sub(r"[*_`]", "", read(DATA_MD)).lower()
    flat = re.sub(r"\s+", " ", flat)
    for token in ("title", "student", "guide", "rubric"):
        assert token in flat, f"data.md must name the minimum input `{token}`"
    assert "formatting questions" in flat, "data.md must refuse formatting questions"
    assert "format phase" in flat, "data.md must defer formatting to the format phase"


def test_intake_is_one_reference_with_route_in_the_content_first_minimum() -> None:
    """Task 3: one intake file; its content-first minimum names the route too."""
    assert not (REFS / "document-intake.md").exists(), (
        "document-intake.md must be gone: references/data.md is the single intake source"
    )
    text = read(DATA_MD)
    flat = re.sub(r"\s+", " ", re.sub(r"[*_`]", "", text)).lower()
    assert "content-first" in flat, "data.md must name the content-first route"
    assert re.search(
        r"minimum[^.]*: route, title, student, [^.]*guide[^.]*rubric[^.]*, (?:and )?teacher explanation",
        flat,
    ), "the content-first minimum must list route, title, student, guide/rubric, teacher explanation"
    assert "format phase" in flat, "data.md must defer formatting to the format phase"
    assert "document-intake" not in read(SKILL_MD), "SKILL.md must not load the removed file"


def test_research_reference_demands_verifiable_ieee_sources() -> None:
    """T6 rule 2: sources are real, verifiable, and cited IEEE."""
    flat = re.sub(r"\s+", " ", read(CONTENT_MD)).lower()
    assert "ieee" in flat, "content.md must name the IEEE citation style"
    assert re.search(r"(?:never|do not) invent", flat), "content.md must forbid invented sources"
    assert "verifiable" in flat, "content.md must require every entry to be verifiable"


def test_plan_reference_mirrors_the_teachers_rubric() -> None:
    """T6 rule 3: one criterion per rubric item, mapped to the section that satisfies it."""
    flat = re.sub(r"\s+", " ", read(CONTENT_MD)).lower()
    assert "one criterion per rubric item" in flat
    assert "mapped to the body section" in flat, (
        "content.md must map every criterion to the body section that satisfies it"
    )


def test_draft_reference_states_the_writing_style_contract() -> None:
    """T6 rule 4: the draft covers the rubric and reads like the user, not like a bot."""
    flat = re.sub(r"\s+", " ", read(CONTENT_MD)).lower()
    assert "every rubric criterion" in flat
    assert "proposed figures" in flat
    assert "natural" in flat, "content.md must ask for human, natural prose"
    assert re.search(r"flattering|obsequious", flat), "content.md must forbid flattering prose"
    assert "how the user writes" in flat, "content.md must model the tone on the user's writing"
    assert "stock ai phrasing" in flat, "content.md must forbid stock AI phrasing"
    assert "starting point" in flat, "content.md must call the draft a starting point for review"


def test_approval_reference_applies_user_text_verbatim() -> None:
    """T6 rule 5: edit orders are applied verbatim and editing re-opens approval."""
    flat = re.sub(r"\s+", " ", read(APPROVAL_MD)).lower()
    assert "edit orders" in flat, "approval.md must describe the literal edit-order loop"
    assert "verbatim" in flat, "approval.md must apply the user's text verbatim"
    assert "polish" in flat and "rephrase" in flat, (
        "approval.md must forbid polishing or rephrasing user-authored text"
    )
    assert "stale" in flat and "pending" in flat, (
        "approval.md must return an edited-after-approval route to approval as pending"
    )


def test_verify_reference_reports_findings_and_never_rewrites() -> None:
    """T6 rule 6: the content check reports findings; the user fixes them."""
    flat = re.sub(r"\s+", " ", read(PRODUCTION_MD)).lower()
    assert re.search(r"never rewrites? `?body\.md", flat), "production.md must forbid rewriting body.md"
    for status in ("cumple", "falta", "found", "missing"):
        assert status in flat, f"production.md must name the `{status}` status"
    assert "flojo" not in flat, "the verify has no `flojo` status"
    assert "edit orders" in flat, "production.md must route fixes through the user's edit orders"
    assert "unmapped paragraphs" in flat and "deletion candidates" in flat, (
        "production.md must report unmapped paragraphs as deletion candidates"
    )


def test_format_reference_is_one_question_with_the_ape_sections() -> None:
    """T6 rule 7: one question, per-format metadata, and the fixed APE sections."""
    flat = re.sub(r"\s+", " ", read(APPROVAL_MD)).lower()
    assert "one question for format selection" in flat
    assert "ask_user_choice" in flat
    for token in ("ape", "aa", "libre", "ieee", "format_spec"):
        assert token in flat, f"approval.md must name `{token}`"
    for section in (
        "objetivo",
        "materiales",
        "procedimiento",
        "resultados",
        "preguntas de control",
        "conclusiones",
        "recomendaciones",
        "anexos",
    ):
        assert section in flat, f"approval.md must name the fixed APE section `{section}`"
    assert "bibliografía" in flat or "referencias" in flat
    assert "identification" in flat, "approval.md must name the APE identification fields"
    assert "teacher's guide" in flat, "approval.md must extract identification fields from the guide"


def test_format_reference_describes_aa_and_acd_with_their_sections() -> None:
    """aa-acd-templates S5/S7: the format question offers APE, AA, ACD or libre and
    approval.md documents each new format's template, metadata and fixed sections."""
    approval = re.sub(r"\s+", " ", read(APPROVAL_MD))
    flat = approval.lower()
    assert "APE, AA, ACD or libre" in approval, "the format question must offer APE, AA, ACD or libre"
    assert "APE, AA, libre" not in approval and "AA, APE or libre" not in approval
    for template in ("aa-report.tex", "acd-report.tex"):
        assert template in approval, f"approval.md must name the template `{template}`"
    assert "`unl-report.tex`), look unchanged" not in approval, "AA no longer uses unl-report.tex"
    for section in (
        "Objetivo(s)",
        "Introducción",
        "Desarrollo",
        "Declaración de uso de IA",
        "Síntesis de contenidos abordados",
        "Actividades desarrolladas en clase",
        "Análisis / reflexión",
    ):
        assert section in approval, f"approval.md must name the AA/ACD section `{section}`"
    for token in ("session topic", "session date", "no cover"):
        assert token in flat, f"approval.md must describe `{token}`"
    intake = re.sub(r"\s+", " ", read(DATA_MD))
    assert "APE, AA, ACD or libre" in intake, "intake must leave APE, AA, ACD or libre to the format phase"


def test_guide_driven_intake_and_pdf_handoff() -> None:
    intake = read(DATA_MD).lower()
    review = read(DELIVERY_MD).lower()
    assert "alejandro padilla" in intake and "ask_user_choice" in intake
    assert "format_hint:" in intake and "guide_facts.py" in intake
    assert "pdf_viewer.py" in review and "never send screenshots" in review


def test_review_reference_gates_delivery_on_an_explicit_pdf_ok() -> None:
    """T6 rule 8: the final human review binds the exact PDF; delivery waits for it."""
    flat = re.sub(r"\s+", " ", read(DELIVERY_MD)).lower()
    assert "final-review.yml" in flat
    assert "pdf_sha256" in flat
    assert "explicit" in flat, "delivery.md must require an explicit OK"
    assert "silence" in flat, "delivery.md must refuse silence as consent"
    assert re.search(r"deliver\w*[^.]{0,60}only after", flat), (
        "delivery.md must gate delivery on the review"
    )


# --- Task 4: hardened content-first intake (exercise 1.5 incident) ----------


def _intake_flat() -> str:
    text = read(DATA_MD)
    return re.sub(r"\s+", " ", re.sub(r"[*_`]", "", text)).lower()


def _content_first_section() -> str:
    flat = _intake_flat()
    start = flat.index("## content-first intake")
    return flat[start : flat.index("## full-route confirmations")]


def test_intake_derives_the_academic_route_from_assignment_signals() -> None:
    """Rule (a): an academic assignment signal records route academic without asking."""
    section = _content_first_section()
    for signal in ("subject", "teacher", "ape", "aa", "exercise", "ejercicio", "homework", "tarea",
                   "práctica", "rubric"):
        assert signal in section, f"content-first intake must list the assignment signal `{signal}`"
    assert "route: academic" in section
    assert "without asking" in section
    assert "intake summary" in section, "the derived route must be stated in the intake summary"
    assert re.search(r"ask the route only when[^.]*(absent|conflicting)", section), (
        "the route is asked only when signals are absent or conflicting"
    )
    assert "resolved with the user, never inferred" not in section, (
        "content-first no longer forbids deriving the route"
    )


def test_standalone_full_route_still_never_infers_the_document_type() -> None:
    flat = _intake_flat()
    full = flat[flat.index("## full-route confirmations") :]
    assert "must never auto-select" in full
    assert "there is no default type" in full
    skill = re.sub(r"\s+", " ", read(SKILL_MD)).lower()
    assert "prohibition on inferring document type" in skill
    assert "never infer it from format, prompt, files, or history" in skill


def test_intake_accepts_a_permanently_saved_student_without_asking() -> None:
    """Rule (b): saved permanent identity is confirmed; otherwise a suggestion; never invented."""
    section = _content_first_section()
    assert re.search(r"saved as permanent[^.]*(memory|preference)", section)
    assert "all future sessions" in section
    assert "records it without asking" in section or "recorded without asking" in section
    assert "single-choice" in section and "never auto-fill" in section
    assert "never invent" in section


def test_intake_always_requests_the_teacher_guide_in_the_single_batch() -> None:
    """Rule (c): guide, rubric and teacher explanation are always requested, one batch."""
    section = _content_first_section()
    assert re.search(r"always requests the teacher'?s? guide, rubric", section)
    assert "teacher explanation" in section
    assert "not already supplied" in section
    assert "single compact question" in section
    assert "never a second round" in section
    assert "unusable" in section


def test_delivery_format_belongs_to_the_format_phase_and_scope_is_explicit() -> None:
    """Rule (d): approval.md owns PDF/DOCX; intake lists which full-route confirmations do not apply."""
    section = _content_first_section()
    assert "never asks the delivery format" in section or "intake never asks the delivery format" in section
    assert "pdf or docx" in section
    assert "do not apply in content-first" in section
    for item in ("audience and purpose", "template and identity", "delivery format", "visual direction"):
        assert item in section, f"scope note must name `{item}`"
    assert "confirmations 3 and 5 below apply only" not in section, "stale partial scope note"
    fmt = re.sub(r"\s+", " ", read(APPROVAL_MD)).lower()
    assert "pdf or docx" in fmt and "same format step" in fmt
    assert "never inferred" in fmt and "no default" in fmt


def test_intake_rejects_commentary_in_free_text_answers() -> None:
    """Rule (e): a complaint or question typed into a free-text field is not a title."""
    section = _content_first_section()
    assert re.search(r"(commentary|complaint)[^.]*(question|complaint)", section)
    assert "not accepted" in section
    assert "cleaned candidate" in section
    assert "one-line confirmation" in section


def test_description_triggers_cover_assignment_requests() -> None:
    """Rule (f): trigger-first single line, <=250 chars, assignment words included."""
    meta = frontmatter(read(SKILL_MD))
    match = re.search(r'^description:\s*"(.*)"\s*$', meta, re.MULTILINE)
    assert match, "description must be one quoted physical line"
    description = match.group(1)
    assert description.startswith("Trigger:") and len(description) <= 250
    lowered = description.lower()
    for word in ("academic report", "university report", "pdf", "docx", "doc status",
                 "exercise", "ejercicio", "homework", "tarea", "ape", "aa",
                 "resume", "approve"):
        assert re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", lowered), f"description must mention {word}"


def test_type_prohibition_names_the_content_first_route_exception() -> None:
    """The SKILL.md prohibition must not contradict the content-first route derivation."""
    text = read(SKILL_MD)
    section = text.split("### Prohibition On Inferring Document Type", 1)[1].split("\n## ", 1)[0]
    assert "content-first" in section and "references/data.md" in section


def _flat(path: Path) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[*`]", "", read(path))).lower()


def test_new_request_creates_the_work_folder_before_doc_status() -> None:
    """Task 7: a fresh request has no folder yet; the entry rule creates it first."""
    skill = _flat(SKILL_MD)
    entry = skill[skill.index("entry rule:") :].split(" loop:")[0]
    assert re.search(r"new request[^;]*creates? the work folder[^;]*before[^;]*doc_status", entry), (
        "SKILL.md entry rule must create the work folder for a new request before doc_status"
    )
    assert "reports/<slug>/" in entry
    assert "existing" in entry and "resum" in entry, "an existing folder is resumed"
    assert "without a work folder" not in skill, (
        "SKILL.md must not route a missing work folder to the standalone full route"
    )


def test_standalone_full_route_is_limited_to_an_unavailable_work_folder_flow() -> None:
    skill = _flat(SKILL_MD)
    entry = skill[skill.index("entry rule:") :].split(" loop:")[0]
    assert re.search(r"standalone full route.{0,60}applies only when the work-folder flow is (unavailable|not available)", entry), (
        "the standalone full route applies only when the work-folder flow is unavailable"
    )


def test_routing_and_skill_agree_on_the_new_request_entry_and_intake_reports_the_folder() -> None:
    """The entry rule lives in SKILL.md and routing.md; intake only states the folder."""
    routing = _flat(ROUTING_MD)
    intake = _flat(DATA_MD)
    skill = _flat(SKILL_MD)
    for name, text in (("routing.md", routing), ("SKILL.md", skill)):
        assert re.search(r"new request[^.]*creates? [^.]*reports/<slug>/", text), (
            f"{name} must state that a new request creates reports/<slug>/ first"
        )
        assert "without a work folder" not in text and "no work folder" not in text, (
            f"{name} must not route a missing work folder to the standalone full route"
        )
        assert re.search(r"unavailable|not available", text), (
            f"{name} must limit the standalone route to an unavailable work-folder flow"
        )
    assert "never ask" in routing and "slug" in routing, "the slug is derived, never asked"
    assert "numeric suffix" in routing
    assert "folder in the intake summary" in intake


def test_existing_slug_folder_match_is_defined_and_asked_once() -> None:
    """A matching folder is never silently resumed or overwritten when it may be a finished document."""
    routing = _flat(ROUTING_MD)
    assert "same document" in routing and "metadata.title" in routing
    assert re.search(r"delivered[^.]*(ask|single-choice)", routing), (
        "a delivered folder must trigger one single-choice question: new version or resume"
    )
    assert re.search(r"never overwrit", routing)


def test_skill_body_stays_within_the_token_budget() -> None:
    body = read(SKILL_MD).split("---", 2)[2]
    assert len(body.split()) <= 1000


def test_draft_requires_h1_sections_math_scripts_and_names_a_real_cli_mode() -> None:
    flat = re.sub(r"\s+", " ", read(CONTENT_MD))
    # issue #96: the draft is plain text; math notation moved to typeset.
    for phrase in ("start at `# `", "Unicode sub/superscripts allowed", "`$...$`", "body.typeset.md", "content_check.py", "--body-check"):
        assert phrase in flat, f"content.md must say `{phrase}`"
    assert "--body-check" in content_check_cli_help()


def content_check_cli_help() -> str:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "content_check.py"), "--help"],
        capture_output=True, text=True, check=False,
    )
    return result.stdout


def test_verify_defines_the_orchestrator_verifier_handoff() -> None:
    flat = re.sub(r"\s+", " ", read(PRODUCTION_MD))
    for phrase in (
        "cannot launch subagents",
        "stops at verify",
        "orchestrator runs the verifier",
        "brief verbatim",
        "one independent read-only subagent",
        "saved unchanged",
        "drafting agent never writes verification.yml",
    ):
        assert phrase in flat, f"production.md must say `{phrase}`"


def test_visual_pass_ownership_is_explicit_across_references() -> None:
    validate = re.sub(r"\s+", " ", read(PRODUCTION_MD))
    for phrase in (
        "executor that performed the direct page-by-page inspection",
        "records `VISUAL_PASS` in `validation.yml`",
        "without an inspection never records `VISUAL_PASS`",
        "`READY_TO_SUBMIT` follows once `HUMAN_REVIEW`",
    ):
        assert phrase in validate, f"production.md must say `{phrase}`"
    assert "validate phase executor" in validate
    for name in ("delivery.md", "routing.md", "approval.md"):
        text = read(REFS / name)
        assert "records `VISUAL_PASS`" not in text, f"{name} must not restate VISUAL_PASS ownership"


def test_approval_batches_the_format_questions_and_format_asks_only_missing() -> None:
    """Task 9.1: one human stop; approval.md is a completeness check plus fallback."""
    approval = re.sub(r"\s+", " ", read(APPROVAL_MD)).lower()
    for token in ("same batch", "ape", "aa", "libre", "pdf", "docx", "report.yml", "never infer"):
        assert token in approval, f"approval.md must describe the single batch: {token}"
    assert "only `body.md`" in approval or "binds only body.md" in approval

    fmt = re.sub(r"\s+", " ", read(APPROVAL_MD)).lower()
    assert "only the missing" in fmt and "never re-ask" in fmt


def test_format_answers_are_recorded_apart_from_the_approval() -> None:
    """#80: a request for changes keeps the format answers and reopens only approval."""
    approval = re.sub(r"\s+", " ", read(APPROVAL_MD)).lower()
    assert "as soon as it is given, even when the user requests changes" in approval
    assert "reopens only the body approval" in approval
    assert "records nothing" not in approval


def test_source_minimum_is_always_stated_as_the_effective_one() -> None:
    """Task 8(c): a bare "at least 5" would contradict a report's min_sources override."""
    for name in ("routing.md", "content.md", "production.md"):
        text = _flat(REFS / name)
        for match in re.finditer(r"at least (5|five)\b", text):
            assert "min_sources" in text[match.start() : match.start() + 160], name


def test_uncited_bibliography_opt_in_is_documented_in_every_reference() -> None:
    """The opt-in is academic-only, prints the whole .bib and excludes min_sources."""
    for name in ("content.md", "production.md", "routing.md", "data.md"):
        text = _flat(REFS / name)
        assert "uncited_bibliography" in text, name
    content = _flat(REFS / "content.md")
    window = content[content.index("uncited_bibliography") :][:500]
    for token in ("academic", "every entry", "min_sources"):
        assert token in window


def test_folder_without_report_yml_is_an_unfinished_intake() -> None:
    """Task 8(j): doc_status answers next: intake and the routing loop says so."""
    routing = _flat(ROUTING_MD)
    assert "without a report.yml" in routing and "unfinished intake" in routing


def test_delivered_definition_names_both_conditions() -> None:
    routing = _flat(ROUTING_MD)
    assert "delivered means a current final-review.yml plus a published version" in routing


def test_plan_without_a_teacher_rubric_uses_only_the_guides_explicit_demands() -> None:
    """Task 8(f): no rubric means criteria come from what the guide explicitly demands."""
    flat = re.sub(r"\s+", " ", read(CONTENT_MD)).lower()
    assert "no teacher rubric" in flat
    assert "only from the guide's explicit demands" in flat
    assert "never from the agent's idea" in flat


def test_every_reference_the_skill_names_exists() -> None:
    """The stage index in SKILL.md, the routing table and the files agree."""
    text = read(SKILL_MD)
    named = set(re.findall(r"references/([a-z-]+\.md)", text))
    assert named >= set(PHASE_REFERENCE.values()) | {"routing.md"}
    for name in named:
        assert (REFS / name).is_file(), name
    on_disk = {path.name for path in REFS.glob("*.md")}
    assert on_disk == set(PHASE_REFERENCE.values()) | {"routing.md", "unl-shell.md", "visual-directions.md"}


def test_stage_references_have_no_duplicate_step_numbers() -> None:
    """Task 8(i): numbered lists run 1..n without repeats in every reference."""
    for path in sorted(REFS.glob("*.md")):
        runs: list[int] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^(\d+)\. ", line)
            if match:
                runs.append(int(match.group(1)))
            elif runs and line.strip() == "":
                continue
            elif runs and not line.startswith((" ", "\t")):
                assert runs == list(range(1, len(runs) + 1)), f"{path.name}: {runs}"
                runs = []
        assert not runs or runs == list(range(1, len(runs) + 1)), f"{path.name}: {runs}"


def test_approval_previews_the_pdf_and_asks_format_spec_for_libre() -> None:
    """Task 11(a)(b): preview + inspection before the batch; libre adds format_spec as a choice."""
    approval = _flat(APPROVAL_MD)
    # issue #96: the preview is for content review; layout is audited after typeset/generate.
    for token in ("--no-approval-check", "preview", "preview findings", "body.typeset.md", "before asking", "never the final", "format_spec", "sin portada", "con portada"):
        assert token in approval, f"approval.md must describe the preview and libre format_spec: {token}"


def test_rubric_checks_default_to_document_wide() -> None:
    """Task 11(e): section-scoped checks only when the property must live in that section."""
    content = _flat(CONTENT_MD)
    assert "document-wide" in content and "only when the property must live in that section" in content


def test_approval_gate_requires_fresh_preview_and_clickable_links() -> None:
    """#59/#60: the gate needs a rebuilt preview and absolute file:// links to it and body.md."""
    approval = _flat(APPROVAL_MD)
    for token in ("records the sha256", "rebuild the draft pdf", "clickable markdown links", "absolute file:// urls", "never present the gate without them", "rebuild the preview pdf"):
        assert token in approval, f"approval.md must require a fresh preview and links: {token}"


def test_draft_phase_documents_the_docx_round_trip() -> None:
    """Task 6: paraphrasing in DOCX goes through draft_docx export/import, never a regenerated open draft."""
    content = _flat(CONTENT_MD)
    for token in ("draft_docx.py", "export", "import", "show the diff", "--apply", "never regenerate a draft that is open"):
        assert token in content, f"content.md must document the DOCX round-trip: {token}"


def test_citation_style_opt_in_is_documented_in_every_reference() -> None:
    """IEEE is the default; `citation_style: apa` is the opt-in the guide must demand."""
    for name in ("content.md", "approval.md", "production.md", "routing.md", "data.md"):
        text = _flat(REFS / name)
        assert "citation_style" in text, name
    content = _flat(REFS / "content.md")
    window = content[content.index("citation_style") :][:400]
    for token in ("apa", "ieee", "default"):
        assert token in window.lower()
    assert "no other style exists" not in content


def test_draft_states_concision_rules() -> None:
    # verify-concise-drafts S4/S5: no padding, no basic concepts, fix by cutting.
    text = re.sub(r"\s+", " ", read(CONTENT_MD))
    for phrase in (
        "never a minimum length",
        "answers a guide or rubric requirement",
        "first sentence",
        "at most 2-3 sentences",
        "typeset turns them into tables and display equations",
        "only the concepts the report's own decisions use",
        "never define basic course concepts",
        "by cutting or shrinking, never by adding prose",
    ):
        assert phrase in text, phrase


def test_skill_hard_rules_state_quality_over_quantity() -> None:
    text = re.sub(r"\s+", " ", read(SKILL_MD))
    assert "Quality over quantity" in text
    assert "no minimum length" in text


def test_plan_and_body_check_state_word_ceiling_and_padding_checks() -> None:
    text = re.sub(r"\s+", " ", read(CONTENT_MD))
    for phrase in ("never a minimum", "max_words:", "weight share", "the word budget", "no stock filler phrases", "no paragraph over 80 words"):
        assert phrase in text, phrase


def test_plan_turns_every_guide_deliverable_into_a_check() -> None:
    text = re.sub(r"\s+", " ", read(CONTENT_MD))
    for phrase in ("deliverables:", "one non-heading check per deliverable", "rubric_plan.py"):
        assert phrase in text, phrase


def test_content_check_cli_offers_one_verification_and_no_judge_flags() -> None:
    help_text = content_check_cli_help()
    assert "--verification" in help_text and "--verify-brief" in help_text
    assert "--judgments" not in help_text and "--judge-brief" not in help_text


def test_verify_runs_before_approval_and_the_gate_shows_one_packet() -> None:
    """verify-concise-drafts T8 (S2), #64: one compact approval packet; the matrix stays for agents."""
    approval = read(APPROVAL_MD)
    production = read(PRODUCTION_MD)
    assert "tools/approval_packet.py" in approval
    assert "one summary row per criterion (cumple/falta, found/total), the missing items" in approval
    assert "per-requirement evidence matrix is for agents" in approval
    assert "before `approval`" in production
    assert "approval_packet.py <folder>" in production


def test_edit_rounds_recheck_only_what_changed() -> None:
    """A small edit never re-reviews the whole document: scoped verify and only what the edit touched."""
    flat = re.sub(r"\s+", " ", read(APPROVAL_MD))
    assert "fresh independent verifier" not in flat
    assert "--since verification.yml" in flat
    assert "visual_pdf_auditor.py" in flat
    assert "re-read only what the edit touched" in flat
    assert "every page on the first preview" not in flat  # issue #96: no layout audit before approval
    assert "Changed pages" in re.sub(r"\s+", " ", read(PRODUCTION_MD))
