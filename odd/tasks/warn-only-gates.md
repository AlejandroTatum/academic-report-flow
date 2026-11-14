# warn-only-gates

Make every quality check of academic-report-flow warn instead of block, make the AI declaration default to include behind one ask-to-choose, and mark the Redes teacher criteria `origin: teacher`.
Branch `feat/warn-only-gates`. Preference source: Engram `preference/report-skill-warn-never-block`.

## Specs

- **S1 – AI declaration defaults to include.** User: "la declaracion de ia, si para material academico que siempre vaya, a no ser que te pida lo contrario, podria ser como un ask to chose."
  - A course with no recorded decision is treated as `include`, and `course_memory` no longer prints `warning: no AI declaration decision for this course; ...`. It prints an informational line saying the default include applies.
  - The format phase note no longer says "never ask whether to include it". When neither the course `feedback.yml` nor `report.yml` records a decision, the agent asks once with an ask-to-choose question. "Incluir declaración de IA (recomendado)" is the first option and "Omitir" the second. The answer is recorded in the course `feedback.yml` (`ai_declaration: include|omit`) so that course is never asked again. A recorded decision is applied without a question.
  - `course_memory` gets a write option that records `ai_declaration: include|omit` in `feedback.yml`. It exits 2 with a usage error on any other value, leaving the file unchanged.
  - `omit` writes `ai_declaration: false` in `report.yml`. `include` writes the declaration text.
- **S2 – Quality checks warn, never block.** User: "no quiero que nunca bloquee la skill, por nada, solo avisar."
  - Every check that judges quality reports a warning and lets the flow continue (exit 0, phase not `blocked`). This covers `rubric_malformed`, `guide_inventory_unmapped`, `content_check_failed`, `content_check_malformed`, `validation_failed`, body-check FAILs, `VALIDATION FAILED`, IEEE reference errors, and the `deliver_report` refusals for stale hash, missing receipt or final review, unresolved rubric, and unmapped inventory.
  - Each warning keeps its code and message, prefixed `warning:`, on stderr or in the phase detail.
  - Genuine hard failures with nothing to work on still fail: a missing PDF to deliver, an unreadable file, a missing required input file, a LaTeX compile crash, and usage errors. Questions to the user (intake data, custom direction) are not gates and stay.
- **S3 – Docs match S1 and S2.** `SKILL.md` and its references stop describing these checks as blocks or refusals. `tests/skills` contract literals are updated with the docs.
- **S4 – Redes teacher criteria get `origin: teacher`.** In the content repo, the `docente-*` criteria get `origin: teacher` in `reports/redes-lab-banda-ancha/rubric.yml` (4 criteria) and `reports/redes-ape-5-integrado/rubric.yml` (5 criteria). The files are untracked, so there is no commit.

## Tasks

- T1 | S1, S3 (AI docs) | writer A | DONE 3c10d6c (focused 541 pass; 12 red caused by B, reconciled in T5)
- T5 | S2 | parent | reconcile test_needs_person ×9, test_accepted_gaps ×1, test_doc_status_v1_revision ×1, test_doc_status_render_cli ×1 (deliver without approval must still refuse per L3); also doc_status draft body_check_failed still locks the draft phase and its detail says "they block publication"; content.md wording
- T2 | S2, S3 (gate docs) | writer B | DONE 0213f0e (focused 830 pass)
- T3 | S4 | parent inline (data) | DONE: 4 + 5 criteria tagged, validate_rubric returns [] on both; backups /tmp/*.rubric.bak; no commit (untracked content repo)
- T5 done: cece281. Full suite 3463 passed. Fixed: no approval.yml and no generation.yml now refuses delivery. Plus 381e977, the visual-builder docs.
- T4 | S1–S4 | gentle-ai-verify mwf67pzg | PARTIAL (S1 and S4 PASS): S1 and S4 pass. S2 has a HIGH L3 bypass: any generation.yml skips the approval check. S3 still has blocking wording in a few docs. rubric_trace, verify_sources and editorial_svg still exit 1.
- T6 | S2, S3, L3 | worker fix round 1 of 2 | DONE b4e98e9: approval anchor fixed (18 L3 tests); rubric_trace, verify_sources and editorial_svg warn; docs updated; full suite 3492 passed plus 1 fixed v1 test
- T7 | S2, S3, L3 | scoped gentle-ai-verify | PASS at b4e98e9: all 8 delivery cases behave per L3; the 3 tools warn; docs clean; 451 focused tests pass; no new findings
- Slice boundary: about 2192 authored lines across 4 commits. Deliver as ONE PR with commits as the review units (behavior plus its tests cannot be split cleanly). Chained PRs only if the user asks.

## Log

- L1 (2026-11-13, user): "la declaracion de ia, si para material academico que siempre vaya, a no ser que te pida lo contrario, podria ser como un ask to chose. y si los demas 2 pasos hacerlos". The other two steps are S2 (downgrade pre-existing gates to warnings) and S4 (mark the Redes `docente-*` criteria `origin: teacher`).
- L3 (parent decision for writer B q1): tools/publish_pdf.py joins T2. Its quality refusals now warn: unmapped inventory, unresolved rubric, stale generation, missing or stale final review, carried-gate stale draft. These still refuse: missing PDF or bib, category/slug errors, version-claim errors, and missing or stale approval.yml. The last stays a refusal because it is the user's explicit approve, a human decision and not a quality check.
- L2: The exploration map is from task mwf4tw8a-1-egn9. It lists the gate sites in rubric_plan, doc_status, content_check, validate_report, build_report_auto, deliver_report and validate_ieee_refs.
