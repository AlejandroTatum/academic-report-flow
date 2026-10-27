"""Unit and CLI tests for ``tools/content_check.py`` (new-report-flow T3/T5, verify-concise-drafts T6).

The verify phase: after the user approves the draft, ONE independent verifier
fills a requirement -> evidence matrix (``verification.yml``), and the tool
records it, downgrades any ``found`` requirement whose evidence quote is not in
``body.md``, adds the deterministic mechanical checks (citations, sources,
rubric checks, links) and derives the pass/fail verdict -- the agent can never
declare a pass by itself. These tests pin the matrix validation, the
downgrade rule, the per-criterion ``cumple|falta`` derivation, the CLI exit
codes (0 pass / 1 fail / 2 usage or input error), the ``content_check_state``
predicate (``absent|malformed|stale|fail|pass``) for new and legacy two-judge
markers, the bindings (body/rubric/bib/guide hashes), the atomic marker write,
and the guarantee that the check never touches ``body.md``. The network is never
reached: an autouse fixture refuses the production link fetcher.
Artifact shapes come from ``tools/conftest.py``.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

import content_check
import link_check
import rubric_checks
import source_count
from conftest import (
    CONTENT_CHECK_SCHEMA,
    DEFAULT_CITED_BODY,
    DEFAULT_RUBRIC_CRITERIA,
    _body,
    _cited_body,
    _content_check,
    _report,
    _rubric,
    _sources_bib,
    _verification,
)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(url: str, method: str) -> int:
        raise AssertionError(f"network access attempted: {method} {url}")

    monkeypatch.setattr(link_check, "default_fetcher", refuse)


def _verify_folder(folder: Path) -> Path:
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)
    _cited_body(folder)
    return folder


def _run(folder: Path, verification: Path | None = None, fetcher=None) -> int:
    """Run the check the way the CLI does and return its exit code."""
    path = verification if verification is not None else _verification(folder)
    return content_check.main([str(folder), "--verification", str(path)], fetcher=fetcher)


def _req(criterion: str, status: str = "found", evidence: str = "Cuerpo con fuentes", **extra: object) -> dict:
    return {"criterion": criterion, "requirement": f"Demand for {criterion}", "status": status,
            "location": "Cuerpo", "evidence": evidence, **extra}


def test_body_check_long_paragraph_warns_without_blocking_budget(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    body = "# A\n\n" + " ".join(["palabra"] * 81)
    monkeypatch.setattr(content_check, "body_check_results", lambda folder: content_check.concision.concision_results(body, [], None))
    assert content_check.run_body_check(Path("unused")) == 0
    assert "warning: review readability" in capsys.readouterr().out
    monkeypatch.setattr(content_check, "body_check_results", lambda folder: content_check.concision.concision_results(body, [], 80))
    assert content_check.run_body_check(Path("unused")) == 1
    assert "FAIL" in capsys.readouterr().out


def test_matrix_derives_cumple_falta_per_criterion_with_no_flojo(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    matrix = _verification(folder, findings=["shared"], requirements=[
        _req("objetivo"), _req("objetivo", "missing", evidence=""), _req("metodologia"), _req("metodologia"),
    ])
    assert _run(folder, matrix) == 1
    marker = _marker(folder)
    assert [(c["id"], c["status"]) for c in marker["criteria"]] == [("objetivo", "falta"), ("metodologia", "cumple")]
    assert marker["verifier"]["role"] == "independent"
    assert len(marker["requirements"]) == 4
    assert "judges" not in marker and "disagreements" not in marker
    assert "shared" in marker["findings"]


def test_found_requirement_with_a_quote_absent_from_body_is_downgraded_to_missing(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    matrix = _verification(folder, requirements=[
        _req("objetivo"),
        _req("metodologia", evidence="Wokwi links all present"),
    ])
    assert _run(folder, matrix) == 1
    marker = _marker(folder)
    downgraded = marker["requirements"][1]
    assert downgraded["status"] == "missing"
    assert [(c["id"], c["status"]) for c in marker["criteria"]] == [("objetivo", "cumple"), ("metodologia", "falta")]
    assert any("Wokwi links all present" in f and "metodologia" in f and "missing" in f for f in marker["findings"])
    assert marker["result"] == "fail" and content_check.content_check_state(folder) == "fail"


def test_whitespace_normalized_quote_is_found_and_comparison_is_case_sensitive(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    matrix = _verification(folder, requirements=[
        _req("objetivo", evidence="Cuerpo\n\tcon   fuentes"),
        _req("metodologia", evidence="CUERPO con fuentes"),
    ])
    assert _run(folder, matrix) == 1
    statuses = [r["status"] for r in _marker(folder)["requirements"]]
    assert statuses == ["found", "missing"]


def test_missing_requirement_keeps_its_status_and_needs_no_evidence(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    matrix = _verification(folder, requirements=[_req("objetivo"), _req("metodologia", "missing", evidence=None)])
    assert _run(folder, matrix) == 1
    assert [r["status"] for r in _marker(folder)["requirements"]] == ["found", "missing"]


def test_unmapped_paragraphs_are_recorded_and_never_block(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    matrix = _verification(folder, unmapped_paragraphs=["Como es sabido, la fisica", "Otro parrafo suelto"])
    assert _run(folder, matrix) == 0
    marker = _marker(folder)
    assert marker["unmapped_paragraphs"] == ["Como es sabido, la fisica", "Otro parrafo suelto"]
    assert marker["result"] == "pass" and content_check.content_check_state(folder) == "pass"


def test_exactly_one_verification_file_is_required(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _verify_folder(tmp_path / "wf")
    args = [str(folder)]
    for index in range(2):
        args.extend(["--verification", str(_verification(folder, name=f"{index}.yml"))])
    assert content_check.main(args) == 2
    assert "exactly one verification file" in capsys.readouterr().err


@pytest.mark.parametrize("flag", ["--judgments", "--judge-brief"])
def test_two_judge_cli_flags_are_removed(tmp_path: Path, flag: str) -> None:
    folder = _verify_folder(tmp_path / "wf")
    with pytest.raises(SystemExit) as exc:
        content_check.main([str(folder), flag] + ([str(folder / "x.yml")] if flag == "--judgments" else []))
    assert exc.value.code == 2


def test_single_judge_marker_is_stale(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    _content_check(folder, judges=[{"role": "independent", "inputs": ["rubric.yml", "body.md", "sources.bib"]}])
    assert content_check.content_check_state(folder) == "stale"


def _marker(folder: Path) -> dict:
    import yaml

    return yaml.safe_load((folder / "content-check.yml").read_text(encoding="utf-8"))


def _mechanical(marker: dict, check: str) -> dict:
    return next(entry for entry in marker["mechanical"] if entry["check"] == check)


# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------


def test_contract_constants_are_pinned() -> None:
    assert content_check.CONTENT_CHECK_NAME == "content-check.yml"
    assert content_check.CONTENT_CHECK_SCHEMA == "academic.content-check/v1"
    assert content_check.VERIFICATION_SCHEMA == "academic.verification/v1"
    assert CONTENT_CHECK_SCHEMA == content_check.CONTENT_CHECK_SCHEMA
    assert content_check.REQUIREMENT_STATUSES == ("found", "missing")
    assert content_check.JUDGMENT_STATUSES == ("cumple", "flojo", "falta")  # legacy markers
    assert content_check.MECHANICAL_NAMES == {
        "citations_resolve", "eligible_sources_cited", "verification_matches_rubric", "rubric_checks", "links_resolve",
    }
    assert content_check.MIN_ACADEMIC_SOURCES == source_count.MIN_ACADEMIC_SOURCES == 5


# ---------------------------------------------------------------------------
# End-to-end runs through main(): exit codes and the written marker
# ---------------------------------------------------------------------------


def test_rejects_unbound_or_nonindependent_verification(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import yaml

    folder = _verify_folder(tmp_path / "wf")
    path = _verification(folder)
    original = yaml.safe_load(path.read_text())
    for change, message in (
        ({"verifier": None}, "verifier"),
        ({"verifier": {"role": "drafter", "inputs": original["verifier"]["inputs"]}}, "independent"),
        ({"verifier": {"role": "independent", "inputs": original["verifier"]["inputs"] + ["conversation"]}}, "inputs"),
        ({"body_sha256": "0" * 64, "body_text_sha256": None}, "verification is for a different draft; re-run the verifier"),
        ({"rubric_sha256": "0" * 64}, "verification is for a different draft; re-run the verifier"),
        ({"schema": "academic.verification/v9"}, "schema"),
    ):
        path.write_text(yaml.safe_dump(dict(original, **change)))
        assert _run(folder, path) == 2
        assert message in capsys.readouterr().err
        assert not (folder / "content-check.yml").exists()


def test_verify_brief_is_bound_and_read_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _verify_folder(tmp_path / "wf")
    assert content_check.main([str(folder), "--verify-brief"]) == 0
    brief = capsys.readouterr().out
    for name in ("rubric.yml", "body.md", "sources.bib"):
        assert str(folder / name) in brief
    assert _sha(folder / "body.md") in brief
    assert _sha(folder / "rubric.yml") in brief
    assert "independent" in brief and "found|missing" in brief
    assert "Do not edit" in brief and "unmapped_paragraphs" in brief
    assert "never score" in brief.lower() and "exactly" in brief and "missing" in brief
    assert "objetivo" in brief and "metodologia" in brief
    assert "[@key]" in brief and "IEEE" in brief and "sources.bib" in brief
    # A plural demand ("Wokwi links") is one requirement per item, never one for all.
    assert "one requirement per item" in brief
    assert "semantic repetition" in brief and "circular explanations" in brief
    assert "whole draft" in brief and "incremental verification" in brief
    assert "findings are advisory" in brief
    assert "not a formatting defect" in brief
    assert "judge" not in brief.lower()


def test_pass_case_writes_marker_and_exits_zero(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")

    assert _run(folder) == 0

    marker = _marker(folder)
    assert marker["schema"] == CONTENT_CHECK_SCHEMA
    assert marker["result"] == "pass"
    assert marker["body_sha256"]
    assert marker["checked_at"]
    assert [c["id"] for c in marker["criteria"]] == ["objetivo", "metodologia"]
    assert all(c["status"] == "cumple" for c in marker["criteria"])
    assert all(entry["ok"] for entry in marker["mechanical"])
    assert marker["findings"] == []
    assert marker["unmapped_paragraphs"] == []


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_preplanned_checks_start_red_and_turn_green_without_editing_body_by_runner(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    criteria = [dict(DEFAULT_RUBRIC_CRITERIA[0], checks=[
        {"type": "contains", "section": "Objetivos", "text": "learning outcome"}
    ]), dict(DEFAULT_RUBRIC_CRITERIA[1])]
    _rubric(folder, criteria=criteria)
    assert not (folder / "body.md").exists()
    _cited_body(folder)
    before = (folder / "body.md").read_bytes()
    assert _run(folder) == 1
    marker = _marker(folder)
    assert _mechanical(marker, "rubric_checks")["ok"] is False
    assert "objetivo" in _mechanical(marker, "rubric_checks")["detail"]
    assert "cumple" in _mechanical(marker, "rubric_checks")["detail"]
    assert marker["rubric_check_results"][0]["ok"] is False
    assert (folder / "body.md").read_bytes() == before
    _body(folder, DEFAULT_CITED_BODY + "\n# Objetivos\n\nLearning outcome.\n")
    assert _run(folder) == 0
    assert _mechanical(_marker(folder), "rubric_checks")["ok"] is True
    assert _marker(folder)["rubric_check_results"][0]["ok"] is True


def test_pass_case_binds_the_current_rubric_and_bib(tmp_path: Path) -> None:
    """new-report-flow T5: the marker records rubric_sha256 and bib_sha256."""
    folder = _verify_folder(tmp_path / "wf")

    assert _run(folder) == 0

    marker = _marker(folder)
    assert marker["rubric_sha256"] == _sha(folder / "rubric.yml")
    assert marker["bib_sha256"] == _sha(folder / "sources.bib")
    assert not (folder / "content-check.yml.tmp").exists(), "the write must leave no temp file"


def test_marker_write_is_atomic_and_cleans_up_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed replace never leaves a half-written marker or a stray temp file."""
    folder = _verify_folder(tmp_path / "wf")

    def _boom(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(content_check.os, "replace", _boom)
    with pytest.raises(OSError):
        content_check.run_check(folder, _verification(folder))

    assert not (folder / "content-check.yml").exists()
    assert not (folder / "content-check.yml.tmp").exists()


def test_fail_case_exits_one_and_records_result(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    matrix = _verification(folder, requirements=[_req("objetivo")])

    assert _run(folder, matrix) == 1

    marker = _marker(folder)
    assert marker["result"] == "fail"


def test_flojo_status_is_a_usage_error(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    matrix = _verification(folder, requirements=[_req("objetivo", "flojo"), _req("metodologia")])

    assert _run(folder, matrix) == 2
    assert not (folder / "content-check.yml").exists()


def test_missing_requirement_fails(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    matrix = _verification(folder, requirements=[_req("objetivo"), _req("metodologia", "missing", evidence="")])

    assert _run(folder, matrix) == 1
    assert _marker(folder)["result"] == "fail"


def test_unresolved_citation_fails(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    _body(folder, DEFAULT_CITED_BODY + "\nReclamo sin fuente [@fantasma].\n")

    assert _run(folder) == 1

    marker = _marker(folder)
    assert _mechanical(marker, "citations_resolve")["ok"] is False
    assert "fantasma" in _mechanical(marker, "citations_resolve")["detail"]
    assert marker["result"] == "fail"


def test_only_four_eligible_cited_sources_fails(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    _body(folder, "# Informe\n\nCuerpo con [@key1], [@key2], [@key3] y [@key4].\n")

    assert _run(folder) == 1

    marker = _marker(folder)
    eligible = _mechanical(marker, "eligible_sources_cited")
    assert eligible["ok"] is False
    assert "4/5" in eligible["detail"]
    assert marker["result"] == "fail"


def test_web_only_cited_sources_do_not_count(tmp_path: Path) -> None:
    """Five cited keys that are all @misc still fail the eligible-source gate."""
    folder = _verify_folder(tmp_path / "wf")
    (folder / "sources.bib").write_text(
        "\n".join(f"@misc{{web{i}, howpublished={{url}}}}" for i in range(1, 6)) + "\n",
        encoding="utf-8",
    )
    _body(folder, "# Informe\n\n" + " ".join(f"[@web{i}]" for i in range(1, 6)) + "\n")

    assert _run(folder) == 1
    assert _mechanical(_marker(folder), "eligible_sources_cited")["ok"] is False


def test_unknown_criterion_id_fails(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    matrix = _verification(folder, requirements=[_req("objetivo"), _req("metodologia"), _req("inventado")])

    assert _run(folder, matrix) == 1

    marker = _marker(folder)
    check = _mechanical(marker, "verification_matches_rubric")
    assert check["ok"] is False
    assert "inventado" in check["detail"]
    assert marker["result"] == "fail"


def test_criterion_without_a_requirement_fails(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    matrix = _verification(folder, requirements=[_req("objetivo")])

    assert _run(folder, matrix) == 1
    check = _mechanical(_marker(folder), "verification_matches_rubric")
    assert check["ok"] is False and "metodologia" in check["detail"]
    assert [c["status"] for c in _marker(folder)["criteria"]] == ["cumple", "falta"]


def test_several_requirements_per_criterion_are_allowed(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    matrix = _verification(folder, requirements=[_req("objetivo"), _req("objetivo"), _req("metodologia")])

    assert _run(folder, matrix) == 0
    assert _mechanical(_marker(folder), "verification_matches_rubric")["ok"] is True


def test_agent_findings_are_recorded_verbatim(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    matrix = _verification(folder, findings=["El parrafo 2 es confuso"])

    assert _run(folder, matrix) == 0

    marker = _marker(folder)
    assert "El parrafo 2 es confuso" in marker["findings"]
    assert marker["result"] == "pass"


def test_mechanical_failures_become_findings(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    _body(folder, "# Informe\n\nCuerpo con [@key1] y una cita rota [@fantasma].\n")

    assert _run(folder) == 1

    findings = "\n".join(_marker(folder)["findings"])
    assert "citations_resolve" in findings or "fantasma" in findings


def test_body_md_bytes_are_never_modified(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    before = (folder / "body.md").read_bytes()

    assert _run(folder) == 0

    assert (folder / "body.md").read_bytes() == before


# ---------------------------------------------------------------------------
# Verify brief: already-run rubric checks, tolerance rules, no-re-verify rule
# ---------------------------------------------------------------------------


def _checked_folder(folder: Path, *, checks: list[dict], body: str, guide: str) -> Path:
    """A verify folder whose first criterion carries deterministic checks + guide."""
    _report(folder)
    _sources_bib(folder)
    criteria = [dict(DEFAULT_RUBRIC_CRITERIA[0], checks=checks), dict(DEFAULT_RUBRIC_CRITERIA[1])]
    _rubric(folder, criteria=criteria)
    _body(folder, body)
    (folder / "guia.txt").write_text(guide, encoding="utf-8")
    (folder / "report.yml").write_text((folder / "report.yml").read_text() + "guide: guia.txt\n")
    return folder


def test_verify_brief_lists_passing_rubric_check(tmp_path: Path) -> None:
    folder = _checked_folder(
        tmp_path / "wf",
        checks=[{"type": "verbatim_from_guide", "section": "Objetivos", "source": "guia.txt",
                 "text": "preparar un informe de laboratorio"}],
        body="# Informe\n\n## Objetivos\n\nPreparar un informe de laboratorio.\n\n## Metodologia\n\nMedimos dos veces.\n",
        guide="La catedra pide: preparar un informe de laboratorio con formato IEEE.\n",
    )
    brief = content_check.verify_brief(folder)
    assert "- objetivo check 1 (verbatim_from_guide): PASS - verbatim text in guide=True, section=True" in brief
    assert brief == content_check.verify_brief(folder)  # deterministic for identical inputs


def test_verify_brief_lists_failing_rubric_check(tmp_path: Path) -> None:
    folder = _checked_folder(
        tmp_path / "wf",
        checks=[{"type": "contains", "section": "Objetivos", "text": "quantum tunneling result"}],
        body="# Informe\n\n## Objetivos\n\nPreparar un informe de laboratorio.\n",
        guide="irrelevant",
    )
    brief = content_check.verify_brief(folder)
    assert "- objetivo check 1 (contains): FAIL - text 'quantum tunneling result' missing" in brief


def test_verify_brief_states_tolerances_and_no_reverify_rule(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    brief = content_check.verify_brief(folder)
    assert "normalizes whitespace" in brief
    assert "first letter" in brief and "sentence-initial" in brief
    assert "contains is case-insensitive" in brief
    assert "accent-insensitively" in brief
    assert "a PASSING check" in brief and "missing" in brief
    assert "only what the checks do not cover" in brief


def test_verify_brief_states_when_rubric_has_no_checks(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    assert "no deterministic checks" in content_check.verify_brief(folder)
    assert not (folder / "content-check.yml").exists()


# ---------------------------------------------------------------------------
# report-flow-hardening T11: one body.md read, shared tolerance text, and the
# guide bound into the marker
# ---------------------------------------------------------------------------


def _guide_folder(folder: Path) -> Path:
    """A verify folder whose report.yml declares an existing guide input."""
    _verify_folder(folder)
    (folder / "guia.txt").write_text("La catedra pide formato IEEE.\n", encoding="utf-8")
    (folder / "report.yml").write_text((folder / "report.yml").read_text() + "guide: guia.txt\n")
    return folder


def test_verify_brief_reads_body_md_exactly_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The recorded hash and the rubric checks see the same bytes: one read.

    ``read_bytes``/``read_text`` are the logical reads (``sha256_file`` opens
    its own stream), so the spy pins both: exactly one logical read of body.md,
    and no hash call ever touches it again.
    """
    folder = _verify_folder(tmp_path / "wf")
    expected_hash = _sha(folder / "body.md")
    reads: list[str] = []
    real_read_bytes, real_read_text = Path.read_bytes, Path.read_text

    def spy_read_bytes(self: Path, *args: object, **kwargs: object) -> bytes:
        if self.name == "body.md":
            reads.append(f"read_bytes:{self}")
        return real_read_bytes(self, *args, **kwargs)  # type: ignore[arg-type]

    def spy_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.name == "body.md":
            reads.append(f"read_text:{self}")
        return real_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

    hashed: list[str] = []
    real_sha = content_check.sha256_file

    def spy_sha256_file(path: Path) -> str:
        hashed.append(str(path))
        return real_sha(path)

    monkeypatch.setattr(Path, "read_bytes", spy_read_bytes)
    monkeypatch.setattr(Path, "read_text", spy_read_text)
    monkeypatch.setattr(content_check, "sha256_file", spy_sha256_file)

    brief = content_check.verify_brief(folder)

    assert reads == [f"read_bytes:{folder / 'body.md'}"]
    assert not any(path.endswith("body.md") for path in hashed)
    assert expected_hash in brief


def test_verify_brief_non_utf8_body_is_input_error(tmp_path: Path) -> None:
    """A decode failure is the same input-error shape as a missing body.md."""
    folder = _verify_folder(tmp_path / "wf")
    (folder / "body.md").write_bytes(b"\xff\xfe not utf-8\n")

    with pytest.raises(ValueError, match="body.md missing or unreadable"):
        content_check.verify_brief(folder)


def test_brief_tolerance_text_is_the_rubric_checks_constant(tmp_path: Path) -> None:
    """The brief quotes rubric_checks.TOLERANCE_RULES verbatim: no drift."""
    folder = _verify_folder(tmp_path / "wf")
    brief = content_check.verify_brief(folder)

    assert f"Tolerance rules these checks apply: {rubric_checks.TOLERANCE_RULES}" in brief


def test_marker_binds_guide_sha256_when_report_declares_one(tmp_path: Path) -> None:
    folder = _guide_folder(_verify_folder(tmp_path / "wf"))

    assert _run(folder) == 0

    assert _marker(folder)["guide_sha256"] == _sha(folder / "guia.txt")


def test_marker_has_no_guide_sha256_without_a_guide(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")

    assert _run(folder) == 0

    assert "guide_sha256" not in _marker(folder)


def test_guide_edit_stales_the_marker(tmp_path: Path) -> None:
    folder = _guide_folder(_verify_folder(tmp_path / "wf"))
    assert _run(folder) == 0

    (folder / "guia.txt").write_text("La catedra pide formato IEEE y APA.\n", encoding="utf-8")

    assert content_check.content_check_state(folder) == "stale"


def test_deleted_guide_stales_the_marker(tmp_path: Path) -> None:
    folder = _guide_folder(_verify_folder(tmp_path / "wf"))
    assert _run(folder) == 0

    (folder / "guia.txt").unlink()

    assert content_check.content_check_state(folder) == "stale"


def test_unbound_guide_stales_the_marker(tmp_path: Path) -> None:
    folder = _guide_folder(_verify_folder(tmp_path / "wf"))
    assert _run(folder) == 0

    (folder / "report.yml").write_text(
        (folder / "report.yml").read_text().replace("guide: guia.txt\n", "")
    )

    assert content_check.content_check_state(folder) == "stale"


def test_escaping_guide_binding_stales_the_marker(tmp_path: Path) -> None:
    folder = _guide_folder(_verify_folder(tmp_path / "wf"))
    assert _run(folder) == 0

    (folder / "report.yml").write_text(
        (folder / "report.yml").read_text().replace("guide: guia.txt", "guide: ../outside.md")
    )

    assert content_check.content_check_state(folder) == "stale"


def test_marker_without_guide_sha256_stays_valid_when_guide_appears_later(tmp_path: Path) -> None:
    """Backward compat: pre-guide markers must not change phase."""
    folder = _verify_folder(tmp_path / "wf")
    assert _run(folder) == 0

    (folder / "guia.txt").write_text("guide added after the check\n", encoding="utf-8")
    (folder / "report.yml").write_text((folder / "report.yml").read_text() + "guide: guia.txt\n")

    assert content_check.content_check_state(folder) == "pass"


# ---------------------------------------------------------------------------
# Usage / input errors: exit 2, nothing written
# ---------------------------------------------------------------------------


def test_missing_folder_is_usage_error(tmp_path: Path) -> None:
    folder = tmp_path / "nope"
    verification = tmp_path / "verification.yml"

    assert content_check.main([str(folder), "--verification", str(verification)]) == 2
    assert not folder.exists()


def test_missing_body_is_usage_error(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _rubric(folder)

    assert _run(folder) == 2
    assert not (folder / "content-check.yml").exists()


def test_missing_or_malformed_rubric_is_usage_error(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    _cited_body(folder)

    assert _run(folder) == 2

    _rubric(folder, criteria=())
    assert _run(folder) == 2
    assert not (folder / "content-check.yml").exists()


def test_missing_verification_file_is_usage_error(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")

    assert content_check.main([str(folder), "--verification", str(folder / "nope.yml")]) == 2


def test_verification_not_a_mapping_is_usage_error(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    path = folder / "verification.yml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")

    assert _run(folder, path) == 2


def test_invalid_status_is_usage_error(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    matrix = _verification(folder, requirements=[_req("objetivo", "maso"), _req("metodologia")])

    assert _run(folder, matrix) == 2


@pytest.mark.parametrize(
    "requirements",
    [
        [],
        ["just text"],
        [{"criterion": "objetivo", "requirement": "r"}],
        [{"requirement": "r", "status": "missing"}],
        [{"criterion": "objetivo", "status": "missing"}],
        [{"criterion": "objetivo", "requirement": "r", "status": "found"}],
        [{"criterion": "objetivo", "requirement": "r", "status": "found", "evidence": "   "}],
    ],
)
def test_malformed_or_unevidenced_requirement_is_usage_error(
    tmp_path: Path, requirements: list, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _verify_folder(tmp_path / "wf")
    matrix = _verification(folder, requirements=requirements)

    assert _run(folder, matrix) == 2
    assert "verification.yml" in capsys.readouterr().err
    assert not (folder / "content-check.yml").exists()


def test_non_utf8_verification_is_usage_error(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    path = folder / "verification.yml"
    path.write_bytes(b"requirements: \xff\xfe\n")

    assert _run(folder, path) == 2


def test_broken_yaml_verification_is_usage_error(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    path = folder / "verification.yml"
    path.write_text("requirements: [unclosed\n", encoding="utf-8")

    assert _run(folder, path) == 2


def test_invalid_verification_names_the_file_and_writes_nothing(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    bad = _verification(folder, name="bad.yml", requirements=[_req("objetivo", "maso")])

    outcome = content_check.run_check(folder, bad)

    assert outcome.result == "" and outcome.marker == {}
    assert len(outcome.errors) == 1 and outcome.errors[0].startswith("bad.yml")
    assert not (folder / "content-check.yml").exists()


def test_verifier_level_errors_name_the_offending_file(tmp_path: Path) -> None:
    import yaml

    folder = _verify_folder(tmp_path / "wf")
    bad = _verification(folder, name="bad.yml")
    original = yaml.safe_load(bad.read_text())
    inputs = original["verifier"]["inputs"]

    for change, message in (
        ({"verifier": {"role": "drafter", "inputs": inputs}},
         ("bad.yml: verifier.role must be independent",)),
        ({"verifier": {"role": "independent", "inputs": inputs + ["conversation"]}},
         ("bad.yml: verifier.inputs must list exactly: rubric.yml, body.md, sources.bib",)),
        ({"body_sha256": "0" * 64, "body_text_sha256": None},
         ("bad.yml: verification is for a different draft; re-run the verifier",)),
    ):
        bad.write_text(yaml.safe_dump(dict(original, **change)))
        outcome = content_check.run_check(folder, bad)
        assert outcome.errors == message, change
        assert not (folder / "content-check.yml").exists()


def test_real_cli_subprocess_exit_codes(tmp_path: Path) -> None:
    """The module entry point maps pass->0, fail->1, usage->2 for real."""
    folder = _verify_folder(tmp_path / "wf")
    runner = sys.executable
    script = Path(content_check.__file__)

    def cli(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([runner, str(script), *args], capture_output=True, text=True)

    passed = cli(str(folder), "--verification", str(_verification(folder)))
    assert passed.returncode == 0, passed.stderr

    failing = _verification(folder, name="bad.yml", requirements=[_req("objetivo"), _req("metodologia", "missing", evidence="")])
    assert cli(str(folder), "--verification", str(failing)).returncode == 1

    assert cli(str(tmp_path / "nope"), "--verification", str(failing)).returncode == 2


# ---------------------------------------------------------------------------
# content_check_state: the folder-level predicate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mechanical", [[], [{"check": "citations_resolve", "ok": True}]])
def test_marker_requires_complete_mechanical_set(tmp_path: Path, mechanical: list[dict]) -> None:
    folder = _verify_folder(tmp_path / "wf")
    _content_check(folder, mechanical=mechanical)
    assert content_check.content_check_state(folder) == "malformed"


@pytest.mark.parametrize("ok", [1, "true", None])
def test_marker_requires_boolean_mechanical_results(tmp_path: Path, ok: object) -> None:
    folder = _verify_folder(tmp_path / "wf")
    _content_check(folder)
    import yaml
    marker = _marker(folder)
    marker["mechanical"][0]["ok"] = ok
    (folder / "content-check.yml").write_text(yaml.safe_dump(marker))
    assert content_check.content_check_state(folder) == "malformed"


def test_no_criteria_cannot_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _verify_folder(tmp_path / "wf")
    matrix = _verification(folder)
    monkeypatch.setattr(content_check.rubric_plan, "load_rubric", lambda _: [])
    assert content_check.run_check(folder, matrix).errors


def test_pre_t1_marker_is_stale_before_mechanical_validation(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    _content_check(folder)
    marker = _marker(folder)
    legacy = {key: marker[key] for key in (
        "schema", "body_sha256", "checked_at", "criteria", "findings", "mechanical", "result"
    )}
    legacy["mechanical"] = [entry for entry in marker["mechanical"] if entry["check"] != "rubric_checks"]
    import yaml
    (folder / "content-check.yml").write_text(yaml.safe_dump(legacy))
    assert content_check.content_check_state(folder) == "stale"


def test_pre_judge_marker_with_current_hashes_is_stale(tmp_path: Path) -> None:
    # Shape written between the rubric/bib binding and the independent judge: current
    # rubric and bib hashes, no judge, and no rubric_checks entry (E2E 2026-09-29).
    folder = _verify_folder(tmp_path / "wf")
    _content_check(folder)
    marker = _marker(folder)
    legacy = {key: marker[key] for key in (
        "schema", "body_sha256", "rubric_sha256", "bib_sha256", "checked_at",
        "criteria", "findings", "mechanical", "result",
    )}
    legacy["mechanical"] = [entry for entry in marker["mechanical"] if entry["check"] != "rubric_checks"]
    import yaml
    (folder / "content-check.yml").write_text(yaml.safe_dump(legacy))
    assert content_check.content_check_state(folder) == "stale"


def test_legacy_marker_is_stale_not_malformed(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    _content_check(folder, drop=("judges", "rubric_sha256"))
    assert content_check.content_check_state(folder) == "stale"


@pytest.mark.parametrize("text", ["requirements: [broken", "- not a mapping"])
def test_parse_failure_has_no_binding_cascade(tmp_path: Path, text: str) -> None:
    folder = _verify_folder(tmp_path / "wf")
    path = folder / "verification.yml"
    path.write_text(text)
    outcome = content_check.run_check(folder, path)
    assert len(outcome.errors) == 1
    assert "verifier" not in outcome.errors[0]


def test_invalid_rubric_never_raises_in_state_or_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _verify_folder(tmp_path / "wf")
    _content_check(folder)
    matrix = _verification(folder)
    monkeypatch.setattr(content_check.rubric_plan, "load_rubric", lambda _: (_ for _ in ()).throw(OSError("denied")))
    assert content_check.content_check_state(folder) == "malformed"
    assert content_check.run_check(folder, matrix).errors


@pytest.mark.parametrize("guide", ["../outside.md", "/tmp/outside.md", "escape.md"])
def test_guide_cannot_escape_report(tmp_path: Path, guide: str) -> None:
    folder = _verify_folder(tmp_path / "wf")
    matrix = _verification(folder)
    if guide == "escape.md":
        outside = tmp_path / "outside.md"
        outside.write_text("secret")
        (folder / guide).symlink_to(outside)
    (folder / "report.yml").write_text((folder / "report.yml").read_text() + f"guide: {guide}\n")
    assert content_check.main([str(folder), "--verify-brief"]) == 2
    assert content_check.run_check(folder, matrix).errors


def test_missing_guide_is_omitted_from_verifier_inputs(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    (folder / "report.yml").write_text((folder / "report.yml").read_text() + "guide: missing.md\n")
    assert "missing.md" not in content_check.verify_brief(folder)
    assert content_check.run_check(folder, _verification(folder)).result == "pass"


def test_content_check_state_absent(tmp_path: Path) -> None:
    assert content_check.content_check_state(tmp_path / "wf") == "absent"


def test_content_check_state_pass_and_fail(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _body(folder)
    _content_check(folder, result="pass")

    assert content_check.content_check_state(folder) == "pass"

    # An honest fail shape: a recorded criterion below ``cumple``.
    _content_check(
        folder,
        result="fail",
        criteria=[
            {"id": "objetivo", "status": "cumple", "where": "Objetivos", "note": "ok"},
            {"id": "metodologia", "status": "flojo", "where": "Metodologia", "note": "vago"},
        ],
    )

    assert content_check.content_check_state(folder) == "fail"


def test_content_check_state_stale_after_body_edit(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _body(folder)
    _content_check(folder, result="pass")
    _body(folder, "# Informe\n\nCuerpo editado despues del chequeo.\n")

    assert content_check.content_check_state(folder) == "stale"


def test_content_check_state_stale_after_rubric_edit(tmp_path: Path) -> None:
    """new-report-flow T5: the check binds rubric.yml too."""
    folder = tmp_path / "wf"
    _body(folder)
    _rubric(folder)
    _content_check(folder, result="pass")
    _rubric(folder, source="rubrica editada por la catedra")

    assert content_check.content_check_state(folder) == "stale"


def test_content_check_state_stale_after_rubric_deleted(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _body(folder)
    _rubric(folder)
    _content_check(folder, result="pass")
    (folder / "rubric.yml").unlink()

    assert content_check.content_check_state(folder) == "stale"


def test_content_check_state_stale_after_bib_edit(tmp_path: Path) -> None:
    """new-report-flow T5: the check binds the document bib too."""
    folder = tmp_path / "wf"
    _body(folder)
    _sources_bib(folder)
    _content_check(folder, result="pass")
    _sources_bib(folder, count=6)

    assert content_check.content_check_state(folder) == "stale"


def test_content_check_state_ignores_recorded_pass_with_failing_criteria(
    tmp_path: Path,
) -> None:
    """T5: a forged ``result: pass`` is re-derived; a flojo criterion fails it."""
    folder = tmp_path / "wf"
    _body(folder)
    _content_check(
        folder,
        result="pass",
        criteria=[
            {"id": "objetivo", "status": "cumple", "where": "Objetivos", "note": "ok"},
            {"id": "metodologia", "status": "flojo", "where": "Metodologia", "note": "vago"},
        ],
    )

    assert content_check.content_check_state(folder) == "fail"


def test_content_check_state_ignores_recorded_pass_with_failing_mechanical(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "wf"
    _body(folder)
    _content_check(
        folder,
        result="pass",
        mechanical=[{"check": name, "ok": name != "citations_resolve", "detail": "fantasma"} for name in content_check.LEGACY_MECHANICAL_NAMES],
    )

    assert content_check.content_check_state(folder) == "fail"


def test_content_check_state_ignores_recorded_pass_with_unknown_criterion_ids(
    tmp_path: Path,
) -> None:
    """T5: recorded criterion ids must equal the current rubric ids."""
    folder = tmp_path / "wf"
    _body(folder)
    _rubric(folder)
    _content_check(
        folder,
        result="pass",
        criteria=[
            {"id": "objetivo", "status": "cumple", "where": "Objetivos", "note": "ok"},
            {"id": "inventado", "status": "cumple", "where": "X", "note": "ok"},
        ],
    )

    assert content_check.content_check_state(folder) == "fail"


def test_content_check_state_dedupes_id_comparison_not_sets(tmp_path: Path) -> None:
    """TRIANGULATE: duplicated recorded ids are not equal to the rubric ids."""
    folder = tmp_path / "wf"
    _body(folder)
    _rubric(folder)
    _content_check(
        folder,
        result="pass",
        criteria=[
            {"id": "objetivo", "status": "cumple", "where": "Objetivos", "note": "ok"},
            {"id": "objetivo", "status": "cumple", "where": "Otro", "note": "ok"},
        ],
    )

    assert content_check.content_check_state(folder) == "fail"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"drop": ("body_sha256",)},
        {"judges": [{"role": "drafter"}, {"role": "independent"}]},
        {"drop": ("bib_sha256",)},
        {"drop": ("result",)},
        {"drop": ("criteria",)},
        {"result": "tal vez"},
        {"schema": "academic.content-check/v2"},
    ],
)
def test_content_check_state_malformed_for_bad_marker_shapes(
    tmp_path: Path, kwargs: dict
) -> None:
    folder = tmp_path / "wf"
    _body(folder)
    _content_check(folder, **kwargs)

    assert content_check.content_check_state(folder) == "malformed"


def test_content_check_state_malformed_for_bad_files(tmp_path: Path) -> None:
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "content-check.yml").write_text("schema: [unclosed\n", encoding="utf-8")
    assert content_check.content_check_state(broken) == "malformed"

    flat = tmp_path / "flat"
    flat.mkdir()
    (flat / "content-check.yml").write_text("just a string\n", encoding="utf-8")
    assert content_check.content_check_state(flat) == "malformed"

    binary = tmp_path / "binary"
    binary.mkdir()
    (binary / "content-check.yml").write_bytes(b"\xff\xfe")
    assert content_check.content_check_state(binary) == "malformed"


def test_content_check_state_malformed_when_body_md_is_gone(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _body(folder)
    _content_check(folder)
    (folder / "body.md").unlink()

    assert content_check.content_check_state(folder) == "malformed"


@pytest.mark.parametrize("judges", ["two independent judges", {"role": "independent"}, 7])
def test_non_list_judges_marker_is_stale_not_a_crash(tmp_path: Path, judges: object) -> None:
    """T11: a present-but-non-list ``judges`` field routes to stale, never raises."""
    folder = _verify_folder(tmp_path / "wf")
    _content_check(folder, judges=judges)

    assert content_check.content_check_state(folder) == "stale"


def test_non_list_judges_with_foreign_schema_is_malformed_not_a_crash(tmp_path: Path) -> None:
    """T11: ``len()`` on an unsized ``judges`` value must never raise TypeError."""
    folder = _verify_folder(tmp_path / "wf")
    _content_check(folder, judges=7, schema="academic.content-check/v2")

    assert content_check.content_check_state(folder) == "malformed"


# ---------------------------------------------------------------------------
# verify-concise-drafts T6: links_resolve (injected fetcher), new-marker state
# bindings, legacy two-judge markers.
# ---------------------------------------------------------------------------


def _body_with_links(folder: Path, *urls: str) -> None:
    _body(folder, DEFAULT_CITED_BODY + "\n" + "\n".join(f"Ver {url} para el dato." for url in urls) + "\n")


def test_links_resolve_passes_on_200_and_records_the_check(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    _body_with_links(folder, "https://ok.example/a")
    calls: list[tuple[str, str]] = []

    def fetcher(url: str, method: str) -> int:
        calls.append((method, url))
        return 200

    assert _run(folder, fetcher=fetcher) == 0
    check = _mechanical(_marker(folder), "links_resolve")
    assert check["ok"] is True and "1" in check["detail"]
    assert calls == [("HEAD", "https://ok.example/a")]


def test_links_resolve_fails_on_404_and_names_the_url(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    _body_with_links(folder, "https://gone.example/x")

    assert _run(folder, fetcher=lambda url, method: 404) == 1

    marker = _marker(folder)
    check = _mechanical(marker, "links_resolve")
    assert check["ok"] is False and "https://gone.example/x" in check["detail"] and "404" in check["detail"]
    assert marker["result"] == "fail"
    assert any(f.startswith("links_resolve:") for f in marker["findings"])


def test_links_resolve_timeout_is_a_warning_and_never_blocks(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    _body_with_links(folder, "https://slow.example/x")

    def fetcher(url: str, method: str) -> int:
        raise TimeoutError("timed out")

    assert _run(folder, fetcher=fetcher) == 0
    marker = _marker(folder)
    assert _mechanical(marker, "links_resolve")["ok"] is True
    assert any("link warning" in f and "https://slow.example/x" in f for f in marker["findings"])
    assert marker["result"] == "pass"


def test_links_are_fetched_once_per_url_in_a_run(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    _body_with_links(folder, "https://dup.example/x", "https://dup.example/x")
    calls: list[str] = []

    def fetcher(url: str, method: str) -> int:
        calls.append(url)
        return 200

    assert _run(folder, fetcher=fetcher) == 0
    assert calls == ["https://dup.example/x"]


def test_body_without_urls_passes_links_resolve_without_fetching(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    assert _run(folder) == 0
    assert "no http" in _mechanical(_marker(folder), "links_resolve")["detail"]


# ---------------------------------------------------------------------------
# New markers: bindings and re-derived verdict; legacy two-judge markers stay valid
# ---------------------------------------------------------------------------


def test_legacy_two_judge_marker_still_reads_as_valid(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    _content_check(folder)  # conftest writes the legacy judges/disagreements shape

    assert "judges" in _marker(folder)
    assert content_check.content_check_state(folder) == "pass"


@pytest.mark.parametrize("edit", ["body", "rubric", "bib", "guide"])
def test_new_marker_goes_stale_when_an_input_changes(tmp_path: Path, edit: str) -> None:
    folder = _guide_folder(_verify_folder(tmp_path / "wf"))
    assert _run(folder) == 0
    assert content_check.content_check_state(folder) == "pass"

    if edit == "body":
        _body(folder, DEFAULT_CITED_BODY + "\nUna frase nueva.\n")
    elif edit == "rubric":
        _rubric(folder, source="otra rubrica")
    elif edit == "bib":
        _sources_bib(folder, count=6)
    else:
        (folder / "guia.txt").write_text("otra guia\n", encoding="utf-8")

    assert content_check.content_check_state(folder) == "stale"


def test_new_marker_forged_pass_with_a_missing_requirement_fails(tmp_path: Path) -> None:
    import yaml

    folder = _verify_folder(tmp_path / "wf")
    assert _run(folder) == 0
    marker = _marker(folder)
    marker["requirements"][0]["status"] = "missing"
    (folder / "content-check.yml").write_text(yaml.safe_dump(marker))

    assert content_check.content_check_state(folder) == "fail"


@pytest.mark.parametrize("drop", ["verifier", "requirements", "unmapped_paragraphs"])
def test_new_marker_missing_verifier_fields_is_malformed(tmp_path: Path, drop: str) -> None:
    import yaml

    folder = _verify_folder(tmp_path / "wf")
    assert _run(folder) == 0
    marker = _marker(folder)
    del marker[drop]
    (folder / "content-check.yml").write_text(yaml.safe_dump(marker))

    assert content_check.content_check_state(folder) in {"malformed", "stale"}
    assert content_check.content_check_state(folder) != "pass"


# ---------------------------------------------------------------------------
# report.yml `min_sources` override
# ---------------------------------------------------------------------------


def _min_sources_folder(folder: Path, value: str | None, bib_count: int = 1) -> Path:
    _report(folder)
    if value is not None:
        with (folder / "report.yml").open("a", encoding="utf-8") as handle:
            handle.write(f"min_sources: {value}\n")
    _sources_bib(folder, count=bib_count)
    _rubric(folder)
    _body(folder, "# Informe\n\nCuerpo con [@key1].\n")
    return folder


def test_min_sources_override_one_passes_with_one_cited_source(tmp_path: Path) -> None:
    folder = _min_sources_folder(tmp_path / "wf", "1")

    assert _run(folder) == 0

    eligible = _mechanical(_marker(folder), "eligible_sources_cited")
    assert eligible["ok"] is True
    assert eligible["detail"].startswith("1/1 eligible book or paper sources cited")


def test_absent_min_sources_still_requires_five_cited(tmp_path: Path) -> None:
    folder = _min_sources_folder(tmp_path / "wf", None)

    assert _run(folder) == 1

    eligible = _mechanical(_marker(folder), "eligible_sources_cited")
    assert eligible["ok"] is False
    assert "1/5" in eligible["detail"]


@pytest.mark.parametrize("bad", ["0", "-2", "'3'", "2.5", "true", "null"])
def test_invalid_min_sources_is_input_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], bad: str
) -> None:
    folder = _min_sources_folder(tmp_path / "wf", bad)

    assert _run(folder) == 2

    assert "min_sources" in capsys.readouterr().err
    assert not (folder / "content-check.yml").exists()


# ---------------------------------------------------------------------------
# Body format check (task 8a): level-1 headings and math sub/superscripts
# ---------------------------------------------------------------------------


def _body_problems(text: str) -> list[str]:
    return content_check.body_format_problems(text)


def test_body_without_level_one_heading_fails() -> None:
    problems = _body_problems("## Seccion\n\nTexto.\n\n### Sub\n")
    assert any("level-1" in problem and "# " in problem for problem in problems)


def test_body_with_level_one_heading_passes() -> None:
    assert _body_problems("# Seccion\n\n## Sub\n\nTexto.\n") == []


def test_level_one_heading_inside_a_fence_does_not_count() -> None:
    problems = _body_problems("## Seccion\n\n```\n# comentario\n```\n")
    assert any("level-1" in problem for problem in problems)


@pytest.mark.parametrize("text", ["c\u2081", "v\u2080", "10\u207b\u2075", "m/s\u00b2", "x\u00b3", "a\u2090"])
def test_unicode_sub_and_superscripts_fail_with_line_numbers(text: str) -> None:
    problems = _body_problems(f"# T\n\nlinea ok\nvalor {text} aqui\n")
    joined = " ".join(problems)
    assert "line 4" in joined
    assert "$c_1$" in joined and "$10^{-5}$" in joined and "m/s$^2$" in joined


def test_unicode_scripts_in_code_are_allowed() -> None:
    body = "# T\n\n```\nc\u2081 = 1\n```\n\nUsa `v\u2080` como nombre.\n"
    assert _body_problems(body) == []


def test_run_check_fails_on_format_defects_and_state_is_fail(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    (folder / "body.md").write_text(
        "## Informe\n\nc\u2081 con $x$ y [@key1] y [@key2], [@key3], [@key4], [@key5].\n", encoding="utf-8"
    )
    assert _run(folder) == 1
    findings = " ".join(_marker(folder)["findings"])
    assert "level-1" in findings
    # issue #96: backend formatting is rejected by name and line; Unicode scripts are plain text.
    assert "line 3" in findings and "math" in findings
    assert "m/s$^2$" not in findings


def test_body_check_mode_reports_without_writing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _verify_folder(tmp_path / "wf")
    (folder / "body.md").write_text("## Informe\n\nTexto con [@key1].\n", encoding="utf-8")
    assert content_check.main([str(folder), "--body-check"]) == 1
    out = capsys.readouterr().out
    assert "level-1" in out
    assert not (folder / "content-check.yml").exists()


def test_body_check_mode_passes_a_clean_draft(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    assert content_check.main([str(folder), "--body-check"]) == 0
    assert not (folder / "content-check.yml").exists()


def test_body_check_results_select_checks_by_name_and_name_format_defects(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    (folder / "body.md").write_text("## Informe\n\nTexto con [@key1].\n", encoding="utf-8")

    results = {item["check"]: item for item in content_check.body_check_results(folder)}

    assert {"citations_resolve", "eligible_sources_cited", "body_format"} <= set(results)
    assert "verification_matches_rubric" not in results
    assert not results["body_format"]["ok"] and "level-1" in results["body_format"]["detail"]
    assert results["citations_resolve"]["ok"]


def test_body_check_output_labels_body_format_defects(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _verify_folder(tmp_path / "wf")
    (folder / "body.md").write_text("## Informe\n\nTexto con [@key1].\n", encoding="utf-8")

    assert content_check.main([str(folder), "--body-check"]) == 1

    assert "[FAIL] body_format:" in capsys.readouterr().out


def test_marker_keeps_five_mechanical_entries_with_unambiguous_format_text(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    (folder / "body.md").write_text("## Informe\n\nTexto con [@key1].\n", encoding="utf-8")

    assert _run(folder) == 1

    marker = _marker(folder)
    assert [c["check"] for c in marker["mechanical"]][-2:] == ["rubric_checks", "links_resolve"]
    assert len(marker["mechanical"]) == 5
    assert "body_format: no level-1 heading" in _mechanical(marker, "rubric_checks")["detail"]


# ---------------------------------------------------------------------------
# Bold pseudo-headings: the pre-approval check applies validate_report's rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    ["**Por el club**", '**Por el club (en adelante, "el club"):**'],
)
def test_body_format_flags_bold_pseudo_headings_with_line_numbers_and_hint(line: str) -> None:
    problems = _body_problems(f"# Contrato\n\n{line}\n\nTexto.\n")

    joined = " ".join(problems)
    assert "line 3" in joined and "##" in joined


def test_body_format_ignores_inline_bold_and_headings() -> None:
    assert _body_problems("# Contrato\n\nTexto con **negrita** inline.\n\n## Por el club\n") == []


def test_body_format_uses_the_validate_report_rule() -> None:
    import validate_report

    assert content_check.bold_pseudo_heading_lines is validate_report.bold_pseudo_heading_lines


def test_body_check_fails_on_bold_pseudo_heading(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _verify_folder(tmp_path / "wf")
    (folder / "body.md").write_text("# Informe\n\n**Por el club**\n\nTexto con [@key1].\n", encoding="utf-8")

    assert content_check.main([str(folder), "--body-check"]) == 1

    out = capsys.readouterr().out
    # issue #96: bold is backend formatting; the plain-text check names it (typeset keeps the pseudo-heading rule).
    assert "[FAIL] plain_text:" in out and "line 3" in out and "bold" in out


def test_body_check_surfaces_a_section_scope_warning_without_failing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Task 11(e): a contains check scoped to a heading the draft lacks warns, it does not add a failure."""
    folder = _verify_folder(tmp_path / "wf")
    scoped = {"type": "contains", "section": "Seccion inexistente", "text": "Texto"}
    results = content_check.body_check_results(folder)
    assert "rubric_scope" not in {item["check"] for item in results}

    import yaml
    data = yaml.safe_load((folder / "rubric.yml").read_text(encoding="utf-8"))
    data["criteria"][0]["checks"] = [scoped]
    (folder / "rubric.yml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    scope = {i["check"]: i for i in content_check.body_check_results(folder)}["rubric_scope"]
    assert scope["ok"] and "Seccion inexistente" in scope["detail"] and "warning" in scope["detail"].lower()
    content_check.main([str(folder), "--body-check"])
    assert "rubric_scope" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Judgment reuse for markup-only body changes (task 11 f)
# ---------------------------------------------------------------------------

PLAIN_BODY = (
    "# Informe\n\nEl cliente dijo \"entrega inmediata\" con fuentes [@key1], [@key2], "
    "[@key3], [@key4] y [@key5].\n\n- primer punto\n- segundo punto\n\n"
    "| a | b |\n| --- | --- |\n| uno | dos |\n"
)
MARKUP_BODY = (
    "# **Informe**\n\nEl cliente dijo “**entrega inmediata**” con fuentes [@key1], [@key2], "
    "[@key3], [@key4] y [@key5].\n\n* primer punto\n* _segundo_ punto\n\n"
    "| a  | b  |\n|:---|:---|\n| uno | dos |\n"
)
# issue #96: the draft body check rejects tables and bold, so verification reuse is
# exercised with the markup a plain draft may still change (list markers, emphasis, quotes).
DRAFT_BODY = (
    "# Informe\n\nEl cliente dijo \"entrega inmediata\" con fuentes [@key1], [@key2], "
    "[@key3], [@key4] y [@key5].\n\n- primer punto\n- segundo punto\n"
)
DRAFT_MARKUP = (
    "# Informe\n\nEl cliente dijo “entrega inmediata” con fuentes [@key1], [@key2], "
    "[@key3], [@key4] y [@key5].\n\n* primer punto\n* _segundo_ punto\n"
)


def _verified_args(folder: Path) -> Path:
    """A verification bound to the current body, carrying ``body_text_sha256``."""
    return _verification(folder, findings=["first"])


def _reuse_folder(folder: Path) -> Path:
    _verify_folder(folder)
    _body(folder, DRAFT_BODY)
    return _verified_args(folder)


def test_verify_brief_carries_the_normalized_text_hash(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    _body(folder, PLAIN_BODY)
    assert f"body_text_sha256: {content_check.body_text_sha256(PLAIN_BODY)}" in content_check.verify_brief(folder)
    assert content_check.body_text_sha256(PLAIN_BODY) == content_check.body_text_sha256(MARKUP_BODY)
    assert content_check.body_text_sha256(DRAFT_BODY) == content_check.body_text_sha256(DRAFT_MARKUP)


def test_markup_only_edit_reuses_verification(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    path = _reuse_folder(folder)
    _body(folder, DRAFT_MARKUP)
    assert _run(folder, path) == 0
    marker = _marker(folder)
    assert "verification reused: markup-only change" in _mechanical(marker, "verification_matches_rubric")["detail"]
    assert content_check.content_check_state(folder) == "pass"


def test_unchanged_body_has_no_reuse_note(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    path = _reuse_folder(folder)
    assert _run(folder, path) == 0
    assert "reused" not in _mechanical(_marker(folder), "verification_matches_rubric")["detail"]


def test_one_word_edit_still_needs_a_new_verification(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "wf"
    path = _reuse_folder(folder)
    _body(folder, DRAFT_MARKUP.replace("primer", "tercer"))
    assert _run(folder, path) == 2
    assert "verification is for a different draft; re-run the verifier" in capsys.readouterr().err


def test_added_character_still_needs_a_new_verification(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    path = _reuse_folder(folder)
    _body(folder, DRAFT_MARKUP.replace("_segundo_ punto", "_segundo_ punto."))
    assert _run(folder, path) == 2


def test_rubric_change_blocks_reuse_even_for_markup_only_edit(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    path = _reuse_folder(folder)
    _body(folder, DRAFT_MARKUP)
    _rubric(folder, source="otra guia")
    assert _run(folder, path) == 2


def test_stale_verification_without_text_hash_is_not_reused(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    _body(folder, PLAIN_BODY)
    path = _verification(folder, body_text_sha256=None)
    _body(folder, MARKUP_BODY)
    assert _run(folder, path) == 2


def test_normalize_body_text_keeps_math_operators() -> None:
    """A change inside math is a content change: the verification must not be reused."""
    from content_check import body_text_sha256

    assert body_text_sha256("La masa es $a*b$.") != body_text_sha256("La masa es $ab$.")
    assert body_text_sha256("Vale $x^_$.") != body_text_sha256("Vale $x^$.")
    assert body_text_sha256("**Nota:** $x_1$") == body_text_sha256("Nota: $x_1$")


def _uncited_folder(folder: Path, body: str = "# Informe\n\nSin citas en el texto.\n") -> Path:
    _report(folder)
    with (folder / "report.yml").open("a", encoding="utf-8") as handle:
        handle.write("uncited_bibliography: true\n")
    (folder / "sources.bib").write_text("@misc{slides, title={Slides}}\n", encoding="utf-8")
    _rubric(folder)
    _body(folder, body)
    return folder


def test_uncited_bibliography_passes_without_citations(tmp_path: Path) -> None:
    folder = _uncited_folder(tmp_path / "wf")

    assert _run(folder) == 0

    marker = _marker(folder)
    eligible = _mechanical(marker, "eligible_sources_cited")
    assert eligible["ok"] is True
    assert eligible["detail"] == "uncited bibliography: 1 entry listed, no citations required"
    assert _mechanical(marker, "citations_resolve")["ok"] is True


def test_uncited_bibliography_still_resolves_cited_keys(tmp_path: Path) -> None:
    folder = _uncited_folder(tmp_path / "wf", "# Informe\n\nCita rota [@fantasma].\n")

    assert _run(folder) == 1

    marker = _marker(folder)
    assert _mechanical(marker, "citations_resolve")["ok"] is False
    assert _mechanical(marker, "eligible_sources_cited")["ok"] is True


def test_uncited_bibliography_body_check_passes(tmp_path: Path) -> None:
    folder = _uncited_folder(tmp_path / "wf")

    results = {item["check"]: item for item in content_check.body_check_results(folder)}

    assert results["eligible_sources_cited"]["ok"] is True


def _ape_folder(tmp_path: Path, headings: tuple[str, ...]) -> Path:
    folder = _verify_folder(tmp_path / "wf")
    report = folder / "report.yml"
    report.write_text(report.read_text(encoding="utf-8") + "format: ape\n", encoding="utf-8")
    body = "".join(f"# {title}\n\nTexto con [@key1].\n\n" for title in headings)
    (folder / "body.md").write_text(body, encoding="utf-8")
    return folder


def _ape_check(folder: Path) -> dict | None:
    return {i["check"]: i for i in content_check.body_check_results(folder)}.get("ape_structure")


def test_body_check_ignores_ape_headings_in_the_plain_draft(tmp_path: Path) -> None:
    # issue #96: the fixed headings are enforced on body.typeset.md (test_typeset.py), not on the draft.
    from validate_report import APE_BODY_HEADINGS

    titles = tuple("Materiales y Herramientas" if t.startswith("Materiales") else t for t in APE_BODY_HEADINGS)

    assert _ape_check(_ape_folder(tmp_path, titles)) is None


def test_body_check_skips_ape_structure_for_other_formats(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")

    assert _ape_check(folder) is None


def _brief_example(folder: Path) -> str:
    brief = content_check.verify_brief(folder)
    assert "Double-quote every string value" in brief
    return brief.split("```yaml\n", 1)[1].split("```", 1)[0]


def test_verify_brief_example_parses_with_parse_verification(tmp_path: Path) -> None:
    folder = _checked_folder(tmp_path / "wf", checks=[], body=PLAIN_BODY, guide="guia\n")
    path = tmp_path / "example.yml"
    path.write_text(_brief_example(folder), encoding="utf-8")
    parsed, errors = content_check.parse_verification(path)
    assert errors == []
    assert parsed["requirements"] and parsed["findings"]


def _findings_file(tmp_path: Path, findings_yaml: str) -> Path:
    path = tmp_path / "j.yml"
    path.write_text(
        "schema: academic.verification/v1\nverifier: {role: independent}\n"
        "requirements:\n  - {criterion: a, requirement: r, status: missing}\nfindings:\n" + findings_yaml,
        encoding="utf-8",
    )
    return path


def test_parse_verification_flattens_mapping_findings(tmp_path: Path) -> None:
    path = _findings_file(tmp_path, "  - {severity: WARNING, text: weak intro}\n  - {b: 2, a: x}\n  - plain\n")
    parsed, errors = content_check.parse_verification(path)
    assert errors == []
    assert parsed["findings"] == ["WARNING: weak intro", "a: x; b: 2", "plain"]


@pytest.mark.parametrize("bad", ["  - 3\n", "  - [a, b]\n", "  - null\n"])
def test_parse_verification_still_rejects_other_finding_types(tmp_path: Path, bad: str) -> None:
    _parsed, errors = content_check.parse_verification(_findings_file(tmp_path, bad))
    assert any("findings must be a list of strings" in e for e in errors)


def _brief_with_style(tmp_path: Path, style_line: str) -> str:
    folder = _checked_folder(
        tmp_path / "wf",
        checks=[{"type": "verbatim_from_guide", "section": "Objetivos", "source": "guia.txt",
                 "text": "preparar un informe de laboratorio"}],
        body="# Informe\n\n## Objetivos\n\nPreparar un informe de laboratorio.\n",
        guide="La catedra pide: preparar un informe de laboratorio.\n",
    )
    report = folder / "report.yml"
    report.write_text(report.read_text() + style_line, encoding="utf-8")
    return content_check.verify_brief(folder)


def test_verify_brief_names_ieee_by_default(tmp_path: Path) -> None:
    brief = _brief_with_style(tmp_path, "")
    assert "render in IEEE format at build time" in brief


def test_verify_brief_names_apa_when_opted_in(tmp_path: Path) -> None:
    brief = _brief_with_style(tmp_path, "citation_style: apa\n")
    assert "render in APA format at build time" in brief
    assert "IEEE" not in brief


# ---------------------------------------------------------------------------
# Concision in the body check (verify-concise-drafts T3/T4)
# ---------------------------------------------------------------------------


def test_body_check_fails_when_total_word_budget_is_exceeded(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    rubric = folder / "rubric.yml"
    rubric.write_text(rubric.read_text(encoding="utf-8") + "max_words: 3\n", encoding="utf-8")
    results = {item["check"]: item for item in content_check.body_check_results(folder)}
    assert results["word_budget"]["ok"] is False
    assert "> 3" in results["word_budget"]["detail"]
    assert content_check.main([str(folder), "--body-check"]) == 1


def test_body_check_fails_on_filler_phrase(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _verify_folder(tmp_path / "wf")
    body = folder / "body.md"
    body.write_text(body.read_text(encoding="utf-8") + "\nCabe destacar que funciona.\n", encoding="utf-8")
    assert content_check.main([str(folder), "--body-check"]) == 1
    assert "filler_phrases" in capsys.readouterr().out


def test_body_check_clean_draft_reports_concision_checks_ok(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    results = {item["check"]: item for item in content_check.body_check_results(folder)}
    for name in ("word_budget", "filler_phrases", "long_paragraphs"):
        assert results[name]["ok"] is True, name


# ---------------------------------------------------------------------------
# Incremental re-verify (verify-concise-drafts T7, S2)
# ---------------------------------------------------------------------------

SECTIONED_BODY = (
    "# Informe\n\n## Objetivos\n\nMedir la deriva con fuentes [@key1] y [@key2].\n\n"
    "## Metodologia\n\nSe usaron [@key3], [@key4] y [@key5].\n"
)


def _sectioned_verification(folder: Path) -> Path:
    """A verification of SECTIONED_BODY carrying the brief's section hashes."""
    _verify_folder(folder)
    _body(folder, SECTIONED_BODY)
    hashes = content_check.section_hashes(SECTIONED_BODY, content_check.rubric_plan.load_rubric(folder))
    return _verification(
        folder,
        requirements=[_req("objetivo", evidence="Medir la deriva"), _req("metodologia", evidence="Se usaron")],
        section_sha256=hashes,
    )


def test_verify_brief_records_one_section_hash_per_criterion(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    _body(folder, SECTIONED_BODY)
    hashes = content_check.section_hashes(SECTIONED_BODY, content_check.rubric_plan.load_rubric(folder))
    assert set(hashes) == {"objetivo", "metodologia"}
    brief = content_check.verify_brief(folder)
    assert f"objetivo: {hashes['objetivo']}" in brief
    assert f"metodologia: {hashes['metodologia']}" in brief


def test_section_hash_ignores_markup_and_skips_missing_sections(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    criteria = content_check.rubric_plan.load_rubric(folder)
    plain = content_check.section_hashes(SECTIONED_BODY, criteria)
    bold = content_check.section_hashes(SECTIONED_BODY.replace("Medir la deriva", "**Medir la deriva**"), criteria)
    assert plain == bold
    assert content_check.section_hashes("# Informe\n\n## Objetivos\n\nTexto.\n", criteria).keys() == {"objetivo"}


def test_since_brief_rechecks_only_changed_sections_and_carries_the_rest(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    previous = _sectioned_verification(folder)
    _body(folder, SECTIONED_BODY.replace("Se usaron", "Se midieron con"))
    brief = content_check.verify_brief(folder, since=previous)
    assert "Incremental re-verify" in brief
    assert "Re-check only these criteria: metodologia" in brief
    assert "Carried over unchanged (the tool merges them from the previous check; do not list them): objetivo" in brief
    assert "evidence: Medir la deriva" not in brief
    assert "evidence: Se usaron" not in brief


def test_since_brief_with_unchanged_body_carries_everything(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    previous = _sectioned_verification(folder)
    brief = content_check.verify_brief(folder, since=previous)
    assert "Re-check only these criteria: (none)" in brief
    assert "Carried over unchanged (the tool merges them from the previous check; do not list them): objetivo, metodologia" in brief


def test_since_brief_after_rubric_change_is_a_full_verify(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    previous = _sectioned_verification(folder)
    _rubric(folder, source="otra guia")
    brief = content_check.verify_brief(folder, since=previous)
    assert "Incremental re-verify" not in brief
    assert "full verify: the rubric changed since" in brief


def test_since_brief_without_previous_section_hashes_rechecks_everything(tmp_path: Path) -> None:
    folder = _verify_folder(tmp_path / "wf")
    _body(folder, SECTIONED_BODY)
    previous = _verification(folder, requirements=[_req("objetivo", evidence="Medir la deriva"),
                                                   _req("metodologia", evidence="Se usaron")])
    brief = content_check.verify_brief(folder, since=previous)
    assert "Re-check only these criteria: objetivo, metodologia" in brief
    assert "Carried over unchanged (the tool merges them from the previous check; do not list them): (none)" in brief


def test_since_brief_rejects_an_unusable_previous_verification(tmp_path: Path, capsys) -> None:
    folder = _verify_folder(tmp_path / "wf")
    bad = folder / "old.yml"
    bad.write_text("not: [valid", encoding="utf-8")
    assert content_check.main([str(folder), "--verify-brief", "--since", str(bad)]) == 2
    assert "content check input error: old.yml is not valid YAML" in capsys.readouterr().err


def test_since_requires_verify_brief(tmp_path: Path, capsys) -> None:
    folder = tmp_path / "wf"
    previous = _sectioned_verification(folder)
    assert content_check.main([str(folder), "--verification", str(previous), "--since", str(previous)]) == 2
    assert "--since only applies to --verify-brief" in capsys.readouterr().err


def _recheck(folder: Path, body: str, requirements: list[dict]) -> Path:
    """Edit body.md and write the verifier's incremental answer for the new bytes."""
    _body(folder, body)
    hashes = content_check.section_hashes(body, content_check.rubric_plan.load_rubric(folder))
    return _verification(folder, requirements=requirements, section_sha256=hashes)


def test_marker_records_the_section_hashes_it_verified(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    verification = _sectioned_verification(folder)
    assert _run(folder, verification) == 0
    hashes = content_check.section_hashes(SECTIONED_BODY, content_check.rubric_plan.load_rubric(folder))
    assert _marker(folder)["section_sha256"] == hashes


def test_check_merges_carried_requirements_from_the_previous_marker(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    assert _run(folder, _sectioned_verification(folder)) == 0
    edited = SECTIONED_BODY.replace("Se usaron", "Se midieron con")
    answer = _recheck(folder, edited, [_req("metodologia", evidence="Se midieron con")])

    assert _run(folder, answer) == 0
    marker = _marker(folder)
    assert [(r["criterion"], r["evidence"]) for r in marker["requirements"]] == [
        ("metodologia", "Se midieron con"), ("objetivo", "Medir la deriva")]
    assert [(c["id"], c["status"]) for c in marker["criteria"]] == [("objetivo", "cumple"), ("metodologia", "cumple")]
    assert answer.read_text(encoding="utf-8").count("criterion:") == 1  # the verifier's file stays unchanged


def test_check_does_not_carry_a_criterion_whose_section_changed(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    assert _run(folder, _sectioned_verification(folder)) == 0
    edited = SECTIONED_BODY.replace("Medir la deriva", "Estimar la deriva").replace("Se usaron", "Se midieron con")
    answer = _recheck(folder, edited, [_req("metodologia", evidence="Se midieron con")])

    assert _run(folder, answer) == 1
    marker = _marker(folder)
    assert [r["criterion"] for r in marker["requirements"]] == ["metodologia"]
    assert dict((c["id"], c["status"]) for c in marker["criteria"])["objetivo"] == "falta"


def test_check_does_not_carry_after_a_rubric_change(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    assert _run(folder, _sectioned_verification(folder)) == 0
    _rubric(folder, source="otra guia")
    answer = _recheck(folder, SECTIONED_BODY, [_req("metodologia", evidence="Se usaron")])

    assert _run(folder, answer) == 1
    assert [r["criterion"] for r in _marker(folder)["requirements"]] == ["metodologia"]


def test_check_accepts_an_empty_answer_when_every_criterion_is_carried(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    assert _run(folder, _sectioned_verification(folder)) == 0
    answer = _recheck(folder, SECTIONED_BODY.replace("\n\n## Metodologia", "\n\n\n## Metodologia"), [])

    assert _run(folder, answer) == 0
    assert len(_marker(folder)["requirements"]) == 2


def test_empty_answer_without_anything_to_carry_is_still_an_input_error(tmp_path: Path, capsys) -> None:
    folder = _verify_folder(tmp_path / "wf")
    before = (folder / "body.md").read_bytes()
    assert _run(folder, _verification(folder, requirements=[])) == 2
    assert "verification.yml requirements must be a non-empty list" in capsys.readouterr().err
    assert not (folder / "content-check.yml").exists()
    assert (folder / "body.md").read_bytes() == before


def _tamper_marker(folder: Path, record: dict) -> None:
    """Replace the previous marker's objetivo requirement, as a hand edit would."""
    import yaml

    path = folder / "content-check.yml"
    marker = yaml.safe_load(path.read_text(encoding="utf-8"))
    marker["requirements"] = [r for r in marker["requirements"] if r["criterion"] != "objetivo"] + [record]
    path.write_text(yaml.safe_dump(marker, sort_keys=False), encoding="utf-8")


def test_a_carried_found_requirement_without_a_quote_is_not_carried(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    assert _run(folder, _sectioned_verification(folder)) == 0
    _tamper_marker(folder, {"criterion": "objetivo", "requirement": "Demand", "status": "found",
                            "location": "", "evidence": ""})
    answer = _recheck(folder, SECTIONED_BODY.replace("Se usaron", "Se midieron con"),
                      [_req("metodologia", evidence="Se midieron con")])

    assert _run(folder, answer) == 1
    marker = _marker(folder)
    assert dict((c["id"], c["status"]) for c in marker["criteria"])["objetivo"] == "falta"
    assert marker["carried_criteria"] == []


def test_a_malformed_previous_marker_record_carries_nothing_instead_of_crashing(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    assert _run(folder, _sectioned_verification(folder)) == 0
    _tamper_marker(folder, {"criterion": ["objetivo"], "requirement": "Demand", "status": "found",
                            "location": "", "evidence": "Medir la deriva"})
    answer = _recheck(folder, SECTIONED_BODY.replace("Se usaron", "Se midieron con"),
                      [_req("metodologia", evidence="Se midieron con")])

    assert _run(folder, answer) == 1
    assert [r["criterion"] for r in _marker(folder)["requirements"]] == ["metodologia"]


def test_a_legacy_marker_without_section_hashes_carries_nothing(tmp_path: Path) -> None:
    import yaml

    folder = tmp_path / "wf"
    assert _run(folder, _sectioned_verification(folder)) == 0
    path = folder / "content-check.yml"
    marker = yaml.safe_load(path.read_text(encoding="utf-8"))
    del marker["section_sha256"]
    path.write_text(yaml.safe_dump(marker, sort_keys=False), encoding="utf-8")
    answer = _recheck(folder, SECTIONED_BODY.replace("Se usaron", "Se midieron con"),
                      [_req("metodologia", evidence="Se midieron con")])

    assert _run(folder, answer) == 1
    assert [r["criterion"] for r in _marker(folder)["requirements"]] == ["metodologia"]


def test_verification_with_section_hashes_still_passes(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    assert _run(folder, _sectioned_verification(folder)) == 0


# issue #98: currency amounts and Windows paths are plain text, not backend formatting.
@pytest.mark.parametrize(
    "line",
    [
        "Cuesta $5 y $10 por unidad.",
        "El rango va de $1.000 a $2.500.",
        "Guardá el archivo en C:\\Users\\ana\\datos.csv antes de correr.",
        "Ejecutá .\\scripts\\run.ps1 o \\\\servidor\\carpeta\\informe.docx.",
        "Abrí docs\\notas.txt y src\\app\\main.py.",
    ],
)
def test_plain_text_allows_currency_and_windows_paths(line: str) -> None:
    assert content_check.plain_text_problems(f"# Informe\n\n{line}\n") == []


@pytest.mark.parametrize(
    ("line", "label"),
    [
        ("El error $e_a$ baja.", "math"),
        ("Vale $x + 1$ en total.", "math"),
        ("Bloque $$x$$ aparte.", "math"),
        ("Inline \\(x\\) y bloque.", "math"),
        ("Fracción \\frac{1}{2} sin dólares.", "LaTeX command"),
        ("Texto (\\textbf{negrita}).", "LaTeX command"),
        ("Producto 2\\times3 y x\\cdot y.", "LaTeX command"),
    ],
)
def test_plain_text_still_flags_math_and_latex_commands(line: str, label: str) -> None:
    problems = content_check.plain_text_problems(f"# Informe\n\n{line}\n")
    assert len(problems) == 1 and f"line 3 ({label})" in problems[0]


def test_body_check_passes_a_draft_with_currency_and_a_windows_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _verify_folder(tmp_path / "wf")
    body = folder / "body.md"
    body.write_text(
        body.read_text(encoding="utf-8") + "\nCuesta $5 y $10; el archivo está en C:\\Users\\ana\\datos.csv.\n",
        encoding="utf-8",
    )

    assert content_check.main([str(folder), "--body-check"]) == 0
    assert "[FAIL]" not in capsys.readouterr().out
    assert not (folder / "content-check.yml").exists()
