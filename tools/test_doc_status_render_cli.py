"""Renderer and ``--json`` tests for ``tools/doc_status.py`` (slice 2c-ii).

``render_human`` is the portable ASCII human block: an optional front-loaded
``**Gate**`` line, exactly one route line with the current token bracketed, a flat
``**Summary**`` list using only ``done|current|pending|blocked``, and a closing
``**Next**`` line -- no tables, no nested headers. ``render_machine`` mirrors the
``gentle-ai.sdd-status/v2`` shape (``## Document Workflow Status``,
``schema: academic.doc-status/v1``, ``next:``, ``### Summary``,
``### Blocked Reasons``, ``### JSON``) with the fenced payload
``schemaName/schemaVersion/workFolder/phases/current/next/gate/blockedReasons``.
``main`` renders both blocks every time: human then machine on stdout by default,
machine on stdout and human on stderr under ``--json``. Shapes come from ``conftest``.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import doc_status
from conftest import (
    _approval,
    _body,
    _bibliography,
    _cited_body,
    _choose_format,
    _content_check,
    _declare_bibliography_delivery,
    _final_review,
    _marker_text,
    _mtime,
    _pdf,
    _published,
    _report,
    _rubric,
    _sha256,
    _sources_bib,
    _validation,
)

CATEGORY = "Academicos"
SLUG = "informe-de-laboratorio"
PAYLOAD_KEYS = {
    "schemaName",
    "schemaVersion",
    "workFolder",
    "phases",
    "current",
    "next",
    "gate",
    "blockedReasons",
}


def _golden_folder(folder: Path) -> Path:
    """The design's documented state: intake+research done, the plan waits, no rubric."""
    _report(folder)
    _sources_bib(folder)
    return folder


def _reviewed_build(folder: Path) -> Path:
    """Build a folder whose every phase through ``review`` is ``done``.

    The chain: identified report, five sources, a valid plan, an approved and
    checked draft, a chosen format with complete metadata, a PDF newer than
    both approval.yml and report.yml, a validation receipt and a final review
    bound to the PDF bytes.
    """
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    _cited_body(folder)
    marker = _approval(folder)
    _content_check(folder)
    _choose_format(folder, "aa")
    pdf = _pdf(folder)
    _mtime(folder / "report.yml", 1_000_000)
    _mtime(marker, 1_000_000)
    _mtime(pdf, 2_000_000)
    _validation(folder, pdf=pdf)
    _final_review(folder, pdf=pdf)
    return folder


def _build_ready(folder: Path) -> Path:
    """Build a folder whose next phase is ``generate`` (approved, checked, formatted)."""
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    _cited_body(folder)
    _approval(folder)
    _content_check(folder)
    _choose_format(folder, "aa")
    return folder


def _deliver_pending(tmp_path: Path, *, name: str = "wf") -> Path:
    """A folder whose only remaining phase is ``deliver`` (no published copy yet)."""
    return _reviewed_build(tmp_path / name)


def _all_done(tmp_path: Path) -> tuple[Path, Path]:
    """A folder whose every phase is ``done``; returns (folder, Documents root)."""
    folder = _reviewed_build(tmp_path / "wf")
    pdf = folder / "final" / "report.pdf"
    root = tmp_path / "Documents"
    # The default confirmed subject "Fisica" scopes its own ASCII course level.
    _published(root, category=f"{CATEGORY}/fisica", slug=SLUG, source=pdf)
    return folder, root


def _human_gate(text: str) -> str:
    """The human ``**Gate**:`` payload, or ``""`` when no gate line renders."""
    match = re.search(r"^\*\*Gate\*\*: (.*)$", text, re.M)
    return match.group(1) if match else ""


def _assert_human_contract(text: str) -> None:
    """Any human block satisfies the portable output contract."""
    assert all(ord(char) < 128 for char in text)
    assert "|" not in text
    assert not any(line.lstrip().startswith("#") for line in text.splitlines())
    routes = [line for line in text.splitlines() if line.startswith("Route:")]
    assert len(routes) == 1
    bracket = re.findall(r"\[([^\]]+)\]", routes[0])
    assert len(bracket) == 1 and (bracket[0] in doc_status.PHASES or bracket[0] == doc_status.DONE)
    summary = re.findall(r"^- ([a-z]+): (\w+)", text, re.M)
    assert [name for name, _ in summary] == list(doc_status.PHASES)
    assert all(state in doc_status.STATE_TOKENS for _, state in summary)


def _payload_block(text: str) -> dict:
    match = re.search(r"```json\n(.*?)\n```", text, re.S)
    assert match is not None
    return json.loads(match.group(1))


# 2.18 render_human golden + portable contract


def test_render_human_golden(tmp_path: Path) -> None:
    """Acceptance for 2.18: the design's exact block for its documented state."""
    status = doc_status.derive(_golden_folder(tmp_path / "wf"))

    text = doc_status.render_human(status)

    rubric = status.work_folder / "rubric.yml"
    guidance = f"record the teacher's rubric in {rubric}, then re-run doc_status"
    assert text == "\n".join(
        [
            f"**Gate**: plan pending - {guidance}",
            "Route: intake > research > [plan] > draft > verify > approval > format"
            " > typeset > generate > validate > review > deliver",
            "",
            "**Summary**",
            "- intake: done - route=academic, title and student recorded",
            "- research: done - sources.bib has 5/5 book or paper sources",
            "- plan: current - rubric.yml missing",
            "- draft: pending",
            "- verify: pending",
            "- approval: pending",
            "- format: pending",
            "- typeset: pending",
            "- generate: pending",
            "- validate: pending",
            "- review: pending",
            "- deliver: pending",
            "",
            f"**Next**: plan - {guidance}",
        ]
    ) + "\n"
    _assert_human_contract(text)


# T7: guidance a fresh session reads must be actionable as printed.


def test_gate_names_the_runnable_deliver_entrypoint(tmp_path: Path) -> None:
    """The deliver gate names tools/deliver_report.py, not only the artifact."""
    folder = _deliver_pending(tmp_path)
    status = doc_status.derive(folder)
    entrypoint = doc_status.ROOT / "tools" / "deliver_report.py"

    text = doc_status.render_human(status)

    assert status.current == "deliver"
    assert entrypoint.is_file(), "the printed entrypoint must exist"
    assert _human_gate(text) == (
        f"deliver pending - publish with "
        f"{shlex.join([sys.executable, str(entrypoint), str(status.work_folder)])}, "
        "then re-run doc_status"
    )
    _assert_human_contract(text)


def test_gate_names_the_runnable_generate_entrypoint_without_publication(tmp_path: Path) -> None:
    """Generate names the build entrypoint and still promises no publication."""
    folder = _build_ready(tmp_path / "wf")
    status = doc_status.derive(folder)
    entrypoint = doc_status.ROOT / "tools" / "build_report_auto.py"

    gate = _human_gate(doc_status.render_human(status))

    assert status.current == "generate"
    assert entrypoint.is_file(), "the printed entrypoint must exist"
    assert (
        f"build with {shlex.join([sys.executable, str(entrypoint), str(status.work_folder)])}"
        in gate
    )
    assert "deliver_report.py" not in gate
    assert "publish" not in gate.lower()


def test_every_phase_guidance_prints_absolute_paths(tmp_path: Path) -> None:
    """TRIANGULATE: no guidance sentence leaves the reader guessing a relative path."""
    status = doc_status.derive(_golden_folder(tmp_path / "wf"))
    folder = status.work_folder

    for phase in doc_status.PHASES:
        sentence = doc_status._guidance(phase, folder)
        assert str(folder) in sentence, phase
        for token in re.findall(r"\S+/(?:[\w.-]+\.(?:yml|md|py))", sentence):
            assert Path(token).is_absolute(), (phase, token)


def test_guidance_is_ascii_for_the_documented_work_folder(tmp_path: Path) -> None:
    """The human block stays ASCII for the documented (ASCII) work folder."""
    status = doc_status.derive(_golden_folder(tmp_path / "wf"))

    for phase in doc_status.PHASES:
        assert doc_status._guidance(phase, status.work_folder).isascii(), phase


# T3: one authoritative gate derivation shared by the human and JSON projections


def test_gate_names_the_actual_focus_before_approval_is_reachable(tmp_path: Path) -> None:
    """A folder that has not reached approval is gated by its real focus, not approval."""
    status = doc_status.derive(tmp_path / "fresh")
    text = doc_status.render_human(status)
    payload = _payload_block(doc_status.render_machine(status))

    assert _human_gate(text).startswith("intake ")
    assert "approval" not in _human_gate(text)
    assert _human_gate(text) == payload["gate"]
    _assert_human_contract(text)


def test_human_and_json_gate_agree_across_the_state_matrix(tmp_path: Path) -> None:
    """The gate text is derived once: human block and JSON payload never disagree."""
    waiting_plan = _golden_folder(tmp_path / "waiting")
    stale_approval = tmp_path / "stale"
    _report(stale_approval)
    _sources_bib(stale_approval)
    _rubric(stale_approval)
    _body(stale_approval)
    _content_check(stale_approval)
    _approval(stale_approval, body_sha256="0" * 64)
    mismatched = tmp_path / "mismatched"
    _reviewed_build(mismatched)
    pdf = mismatched / "final" / "report.pdf"
    _validation(mismatched, pdf=pdf, artifact_sha256="0" * 64)
    done, root = _all_done(tmp_path)

    for folder, documents_root in (
        (waiting_plan, None),
        (stale_approval, None),
        (mismatched, None),
        (done, root),
    ):
        status = doc_status.derive(folder, documents_root=documents_root)
        human = doc_status.render_human(status)
        payload = _payload_block(doc_status.render_machine(status))

        assert _human_gate(human) == payload["gate"]
        _assert_human_contract(human)

    assert _human_gate(doc_status.render_human(doc_status.derive(waiting_plan))).startswith(
        "plan pending - "
    )
    assert _human_gate(doc_status.render_human(doc_status.derive(stale_approval))).startswith(
        "approval pending - "
    )
    assert _human_gate(doc_status.render_human(doc_status.derive(mismatched))).startswith(
        "validate pending - "
    )
    assert _human_gate(doc_status.render_human(doc_status.derive(done, documents_root=root))) == ""


def test_render_human_omits_gate_when_route_complete(tmp_path: Path) -> None:
    """TRIANGULATE: an all-done route starts directly with the route line."""
    folder, root = _all_done(tmp_path)
    status = doc_status.derive(folder, documents_root=root)

    text = doc_status.render_human(status)

    assert status.current == doc_status.DONE
    assert "**Gate**" not in text and text.startswith("Route:")
    assert text.rstrip().endswith("**Next**: done")
    _assert_human_contract(text)


def test_render_human_gate_falls_to_focus_after_verify(tmp_path: Path) -> None:
    """TRIANGULATE: once the check passes and the format is complete the gate
    names the waiting build."""
    folder = _build_ready(tmp_path / "wf")

    status = doc_status.derive(folder)

    states = {phase.name: phase.state for phase in status.phases}
    assert states["approval"] == doc_status.DONE
    assert states["verify"] == doc_status.DONE
    assert states["format"] == doc_status.DONE
    assert status.current == "generate"
    assert "**Gate**: generate " in doc_status.render_human(status)
    _assert_human_contract(doc_status.render_human(status))


def test_render_human_gate_names_a_stale_check(tmp_path: Path) -> None:
    """TRIANGULATE: a body edited after the check routes back to verify, waiting.

    The user re-approved the edited body (the normal review loop), so approval
    is current again and the only stale artifact is the content check.
    """
    folder = _build_ready(tmp_path / "wf")
    _body(folder, "# Informe\n\nCuerpo editado despues del chequeo.\n")
    _approval(folder)

    status = doc_status.derive(folder)
    text = doc_status.render_human(status)

    assert status.current == "verify"
    assert "**Gate**: verify pending - " in text
    _assert_human_contract(text)


def test_render_human_gate_reports_waiting_stale_approval(tmp_path: Path) -> None:
    """TRIANGULATE: a stale marker keeps the focus on approval, waiting not blocked."""
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    _body(folder)
    _content_check(folder)
    _approval(folder, body_sha256="0" * 64)

    status = doc_status.derive(folder)
    text = doc_status.render_human(status)

    assert status.current == "approval"
    assert "**Gate**: approval pending - " in text
    _assert_human_contract(text)


def test_gate_names_body_md_when_draft_is_current(tmp_path: Path) -> None:
    """Acceptance: plan done, body.md missing gates on draft naming body.md."""
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)

    status = doc_status.derive(folder)
    text = doc_status.render_human(status)

    body = status.work_folder / "body.md"
    assert status.current == "draft"
    assert _human_gate(text) == f"draft pending - draft {body}, then re-run doc_status"
    _assert_human_contract(text)


def test_gate_and_guidance_helpers_are_ascii_and_folder_bound(tmp_path: Path) -> None:
    """``_gate`` projects the authoritative gate; ``_guidance`` binds the folder."""
    folder = _golden_folder(tmp_path / "wf")
    status = doc_status.derive(folder)

    gate = doc_status._gate(status)
    work = status.work_folder

    assert gate.startswith("plan pending - ") and str(work / "rubric.yml") in gate
    assert doc_status._guidance("plan", work) == (
        f"record the teacher's rubric in {work}/rubric.yml, then re-run doc_status"
    )
    assert doc_status._guidance("draft", work) == (
        f"draft {work}/body.md, then re-run doc_status"
    )
    assert f"generation runs only after you approve {work}/body.md" in doc_status._guidance("approval", work)
    assert all(ord(char) < 128 for char in gate + doc_status._guidance("intake", work))


# 2.19 render_machine schema + --json routing


def test_render_machine_schema_and_payload(tmp_path: Path) -> None:
    """Acceptance for 2.19: machine shape and the exact JSON payload keys."""
    status = doc_status.derive(_golden_folder(tmp_path / "wf"))

    text = doc_status.render_machine(status)
    payload = _payload_block(text)

    assert text.startswith("## Document Workflow Status\n")
    assert "schema: academic.doc-status/v1" in text
    assert f"next: {status.next_token}" in text
    assert "### Summary" in text and "### Blocked Reasons" in text and "### JSON" in text
    assert set(payload) == PAYLOAD_KEYS
    assert payload["schemaName"] == "academic.doc-status" and payload["schemaVersion"] == 1
    assert payload["workFolder"] == str(status.work_folder)
    assert [phase["name"] for phase in payload["phases"]] == list(doc_status.PHASES)
    assert payload["current"] == status.current and payload["next"] == status.next_token
    assert payload["gate"] == status.gate
    assert payload["blockedReasons"] == list(status.blocked_reasons)
    assert doc_status._payload(status) == payload


def test_render_machine_lists_blocked_reasons(tmp_path: Path) -> None:
    """TRIANGULATE: a blocked route surfaces its bounded reason token."""
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    _body(folder)
    _content_check(folder)
    _marker_text(folder, "body_sha256: [unclosed\n")

    text = doc_status.render_machine(doc_status.derive(folder))

    assert "approval_marker_malformed" in text
    assert _payload_block(text)["blockedReasons"] == ["approval_marker_malformed"]


def test_main_json_routes_machine_to_stdout_and_human_to_stderr(tmp_path: Path, capsys) -> None:
    """Acceptance for 2.19: ``--json`` still renders both blocks."""
    folder = _golden_folder(tmp_path / "wf")

    rc = doc_status.main([str(folder), "--json"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "## Document Workflow Status" in captured.out and "### JSON" in captured.out
    assert "**Summary**" not in captured.out
    assert "**Summary**" in captured.err and "Route:" in captured.err and "**Gate**" in captured.err


def test_main_default_renders_both_blocks_on_stdout(tmp_path: Path, capsys) -> None:
    """TRIANGULATE: without ``--json`` both blocks stay on stdout; stderr is empty."""
    folder = _golden_folder(tmp_path / "wf")

    rc = doc_status.main([str(folder)])

    captured = capsys.readouterr()
    assert rc == 0 and captured.err == ""
    assert captured.out.index("Route:") < captured.out.index("## Document Workflow Status")
    assert "**Summary**" in captured.out and "### Summary" in captured.out


# T7 blocker 2: the printed guidance must be an executable, correctly quoted command.


_PRINTED_COMMAND = re.compile(r"(?:publish|build) with (?P<command>.+), then re-run doc_status$")


def _printed_command(gate: str) -> list[str]:
    """Parse the command a gate sentence prints, as argv, the way a shell would."""
    match = _PRINTED_COMMAND.search(gate)
    assert match, f"gate does not print a runnable command: {gate!r}"
    return shlex.split(match.group("command"))


def _run_printed(argv: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run the parsed command exactly as printed, from an unrelated directory."""
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True)


def test_printed_deliver_command_names_the_interpreter_and_quotes_the_paths(tmp_path: Path) -> None:
    """RED: guidance must carry the interpreter and shell-quote a folder with spaces."""
    folder = _deliver_pending(tmp_path, name="wf con espacios")
    status = doc_status.derive(folder)
    gate = _human_gate(doc_status.render_human(status))

    argv = _printed_command(gate)

    assert argv[0] == sys.executable, "the printed command must name its interpreter"
    assert Path(argv[0]).is_file() and os.access(argv[0], os.X_OK)
    assert argv[1] == str(doc_status.ROOT / "tools" / "deliver_report.py")
    assert argv[2] == str(status.work_folder)
    assert len(argv) == 3, "the only published command is interpreter + tool + work folder"
    assert "'" in gate, "paths with spaces must be shell-quoted"


def test_printed_deliver_command_refuses_without_approval_and_writes_nothing(
    tmp_path: Path, monkeypatch
) -> None:
    """The printed command runs as-is and refuses a missing approval without writes."""
    folder = _deliver_pending(tmp_path, name="wf sin aprobacion")
    status = doc_status.derive(folder)
    home = tmp_path / "fake home"
    home.mkdir()
    unrelated = tmp_path / "unrelated cwd"
    unrelated.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(unrelated)
    argv = _printed_command(_human_gate(doc_status.render_human(status)))
    # The route printed the deliver command; the human marker disappears before it runs.
    (status.work_folder / "approval.yml").unlink()

    completed = _run_printed(argv, unrelated)

    assert completed.returncode != 0, "a missing approval must refuse delivery"
    combined = completed.stdout + completed.stderr
    assert "approval" in combined.lower(), combined
    assert not (home / "Documents").exists(), "a refusal must create nothing"


def test_printed_deliver_command_publishes_with_only_the_documents_root_override(
    tmp_path: Path, monkeypatch
) -> None:
    """The printed command publishes when the documented override is appended."""
    folder = _deliver_pending(tmp_path, name="wf con espacios")
    status = doc_status.derive(folder)
    home = tmp_path / "fake home"
    home.mkdir()
    unrelated = tmp_path / "unrelated cwd"
    unrelated.mkdir()
    documents = tmp_path / "Documents override"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(unrelated)
    argv = _printed_command(_human_gate(doc_status.render_human(status)))
    assert len(argv) == 3, "no argument correction is needed to run the printed command"

    completed = subprocess.run(
        [*argv, "--documents-root", str(documents)],
        cwd=unrelated,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    published = sorted(documents.rglob("*-v001.pdf"))
    assert len(published) == 1 and published[0].read_bytes() == status.work_folder.joinpath(
        "final", "report.pdf"
    ).read_bytes()
    assert not (home / "Documents").exists(), "only the fixture Documents root is used"


def test_printed_generate_command_names_a_runnable_interpreter_and_tool(tmp_path: Path) -> None:
    """The generate command resolves to an executable interpreter + the current tool."""
    folder = _build_ready(tmp_path / "wf")
    status = doc_status.derive(folder)
    argv = _printed_command(_human_gate(doc_status.render_human(status)))

    assert argv[0] == sys.executable
    assert argv[1] == str(doc_status.ROOT / "tools" / "build_report_auto.py")
    assert argv[2] == str(status.work_folder)
    # The interpreter/tool pair is executed; the full build is not run here because
    # the deliver command above already exercises the folder argument end to end.
    probe = subprocess.run([argv[0], argv[1], "--help"], capture_output=True, text=True)
    assert probe.returncode == 0
    assert "folder" in probe.stdout
    assert "ModuleNotFoundError" not in probe.stderr


def test_printed_commands_round_trip_through_a_shell_parse(tmp_path: Path) -> None:
    """TRIANGULATE: the printed text is exactly ``shlex.join(argv)`` for a spaced folder."""
    folder = _deliver_pending(tmp_path, name="wf con espacios")
    status = doc_status.derive(folder)

    for phase in ("generate", "deliver"):
        sentence = doc_status._guidance(phase, status.work_folder)
        match = _PRINTED_COMMAND.search(sentence)
        assert match, phase
        argv = shlex.split(match.group("command"))
        assert argv[0] == sys.executable, phase
        assert argv[-1] == str(status.work_folder), phase
        assert match.group("command") == shlex.join(argv), (
            f"{phase} command must be shell-quoted, not raw-concatenated"
        )


def test_all_done_route_reads_the_subject_scoped_delivery_folder(tmp_path: Path, capsys) -> None:
    """Full sandbox route: a canonical-subject academic report is all done via the course level.

    Same chain as ``_reviewed_build`` but with the confirmed subject overridden,
    so the deliver phase must find the published copy at
    ``Academicos/<subject-slug>/<slug>/`` -- the exact folder the publisher
    writes -- for the whole route to report done, on ``derive`` and the CLI.
    """
    folder = tmp_path / "wf"
    _report(folder, subject="Sistemas Operativos")
    _sources_bib(folder)
    _rubric(folder)
    _cited_body(folder)
    marker = _approval(folder)
    _content_check(folder)
    _choose_format(folder, "aa")
    pdf = _pdf(folder)
    _mtime(folder / "report.yml", 1_000_000)
    _mtime(marker, 1_000_000)
    _mtime(pdf, 2_000_000)
    _validation(folder, pdf=pdf)
    _final_review(folder, pdf=pdf)
    root = tmp_path / "Documents"
    published = _published(
        root, category="Academicos/sistemas-operativos", slug=SLUG, source=pdf
    )

    status = doc_status.derive(folder, documents_root=root)

    assert status.current == "done"
    deliver = status.phases[-1]
    assert deliver.state == doc_status.DONE
    assert published.name in deliver.detail

    # The machine JSON projection main() writes carries the same route;
    # doc_status's CLI has no root override, so the sandbox check projects directly.
    payload = doc_status._payload(status)
    assert payload["current"] == "done"
    assert payload["phases"][-1] == {
        "name": "deliver",
        "state": "done",
        "detail": f"{published.name} published and hash-matched",
        "blockedReason": "",
    }


def test_all_done_route_with_requested_bibliography(tmp_path: Path) -> None:
    """Full sandbox route with `deliver_bibliography: true` ends done on the pair.

    Same chain as ``_reviewed_build`` plus the opt-in: validation and final
    review must bind the declared .bib bytes, and the deliver phase must find
    the complete versioned pair before the route reports done.
    """
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    _cited_body(folder)
    marker = _approval(folder)
    _content_check(folder)
    _choose_format(folder, "aa")
    pdf = _pdf(folder)
    _mtime(folder / "report.yml", 1_000_000)
    _mtime(marker, 1_000_000)
    _mtime(pdf, 2_000_000)
    bib = folder / "sources.bib"
    _declare_bibliography_delivery(folder)
    _validation(folder, pdf=pdf, bibliography_sha256=_sha256(bib))
    _final_review(folder, pdf=pdf, bibliography=bib)
    _mtime(folder / "report.yml", 1_500_000)  # the append must stay older than the PDF
    root = tmp_path / "Documents"
    published = _published(
        root, category="Academicos/fisica", slug=SLUG, source=pdf,
    )
    (root / "Academicos" / "fisica" / SLUG / f"{SLUG}-v001.bib").write_bytes(
        bib.read_bytes()
    )

    status = doc_status.derive(folder, documents_root=root)

    assert status.current == "done"
    assert status.phases[-1].state == doc_status.DONE
    assert published.name in status.phases[-1].detail
