# Accepted partial gaps — human waiver for the verify gate

Branch `feat/accepted-partial-gaps` (from origin/main 7e158a2). Lets the human explicitly accept named `partial` requirements that only a person outside the flow can close, so the verify gate does not block forever; `missing` requirements and mechanical failures still block.

## Specs

- S1: The user's complaint, verbatim: "me parece falla de skill bloquear tanto". Accepted fix (user choice, verbatim option): "Agrego a academic-report-automation una «aceptación humana de parciales»: vos aceptás con nombre y motivo cada requisito parcial, queda registrado en approval.yml y el gate de verify lo respeta. Lo hago con tests y en una rama." Implementation note: the record lives in its own file `accepted-gaps.yml` (approval.yml comes after verify and is carried across bounded edits, so it cannot gate verify); the user-facing promise (named, with reason, recorded, respected by the verify gate, tested, on a branch) is unchanged.
- S2: Writer CLI `tools/accepted_gaps.py accept <folder> --by NAME --requirement "<exact requirement text>" --reason "<text>" [--criterion ID]` (repeatable `--requirement`/`--reason` pairs or one gap per call, appending). Refuses: blank `--by` or `--reason`; a requirement that is not currently `partial` in `content-check.yml` (missing, found, or no exact match); content-check state `absent`, `stale` or `malformed`. Exit code non-zero with a clear stderr message; refused input writes nothing.
- S3: `accepted-gaps.yml` (schema `academic.accepted-gaps/v1`) records accepted_at, accepted_by, body/rubric/bib hashes and a hash of the normalized `requirements` of `content-check.yml`, plus `gaps: [{criterion, requirement, gap, reason}]`. Any change to body, rubric, bib or the recorded requirements makes it stale (ignored). Not carried across bounded edits. Writing it never changes `content-check.yml`.
- S4: Verdict: `content_check_state` returns `pass` when mechanical checks pass, ids match, and every requirement is `found` or is a `partial` covered by a current, valid `accepted-gaps.yml`. `missing` requirements, mechanical failures, a stale/forged/malformed waiver, or a waiver naming a different requirement leave `fail`. Recorded statuses stay `partial`/`falta` (no rewrite to `cumple`); `rubric_grade` output is unchanged.
- S5: `doc_status` verify phase DONE detail names the accepted gaps count; verify guidance tells the human that `accepted_gaps.py` exists when only partial requirements remain. `approval_packet.py` lists accepted gaps with reason and who accepted them.
- S6: Docs: skills/academic-report-flow SKILL.md Hard Rules + references (production.md verify steps, approval.md packet, content.md partial rule, routing.md if it describes the verify gate) describe the waiver: human-only, never agent-written, requires the person's name and reason, never for `missing`.
- S7: The agent never runs `accepted_gaps.py` on its own initiative; only after the human names the requirement and reason in the conversation (documented in SKILL.md like the other human gates).

## Tasks

- [x] T1 S1-S7 — implement tool + content_check/doc_status/approval_packet changes + tests + docs (worker) — commit ab36c8a
- [ ] T2 S4 — independent verification (Risk item 2: guard change) — evidence
- [ ] T3 — PR (user decides merge)

## Log

- L1 (2026-11-08, user): "vio la ultima version, yo ya le expuse en quarto amigo. me parece falla de skill bloquear tanto"
- L2 (2026-11-08, user): chose "Arreglar la skill (recomendado)".
- L3 (2026-11-08, evidence): explorer map — verdict sites tools/content_check.py:~952/:981 (write) and :1087/:1116-1122 (re-derive); approval_marker independent of verify; doc_status _phase_verify :351-381; approval_packet.py:71/:89; tests pattern tools/test_content_check_partial.py, tools/conftest.py helpers _verification/_content_check; run `python3 -m pytest tools/ tests/`.
