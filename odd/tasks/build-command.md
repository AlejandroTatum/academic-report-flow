# Single build command and proyecto leftovers

Second part of "slice 8" (`docs/portal/mejoras-skill.qmd:82-86`) plus two leftovers of `format: proyecto`.
Worktree `academic-report-automation-worktrees/build-command`, branch `feat/build-command` (base main 179f63f, which already has `typeset.py auto`).
Not in this feature: grouping the visible phases 12 -> 8, auto-deliver after review, `course_profile.PRACTICE_FORMATS`.

## Specs

S1. Source requirement (`docs/portal/mejoras-skill.qmd`): "`typeset + generate + validate` se presentan como una sola fase `build` con un único comando que encadena las tres." The user chose only "Fase única build: Un solo comando encadena typeset + generate + validate"; "Agrupar 12 a 8 fases visibles" was not chosen, so `PHASES`, the `Route:` line, the Summary and `next:` of `doc_status` stay exactly as they are.
S2. New command `tools/build.py <folder>`. Step 1, typeset: it runs the same code as `typeset.py auto <folder>` (same messages, same `left for you:` lines, same check lines). When the bind is refused or any typeset check fails it builds nothing, says the typeset body must be finished and the same command run again, and exits 1. When the report does not use typeset (`typeset.typeset_in_use` is false) the step is skipped and says so.
S3. Step 2, generate and validate: it runs the same code as `build_report_auto.py <folder>`, with the same messages, refusals and exit status, and adds no option that skips a gate (no `--no-approval-check`, no `--validate-only`).
S4. After a successful build it prints what is left for the validate phase: inspect every page of the final PDF and record `validation.yml`. The command never writes `validation.yml`, `approval.yml`, `final-review.yml` or `body.md`, and never claims `VISUAL_PASS`.
S5. Timings: each step records the phase it records today (`typeset`, `generate`) in `timings.yml`; no new phase name.
S6. `doc_status` guidance for `typeset` and for `generate` names the single command (the typeset guidance keeps saying what the agent finishes by hand). `typeset.py auto|bind|check` and `build_report_auto.py` keep working unchanged.
S7. Help text, module docstring, `skills/academic-report-flow/references/production.md` (Typeset and the generate step) and `docs/portal/mejoras-skill.qmd` describe the command.
S8. Proyecto leftover (user chose "Leyendas Tabla A y B: Que la declaración de IA use el mismo estilo de leyenda que el resto"): in `format: proyecto`, a line "Tabla A. Herramientas utilizadas" or "Tabla B. Prompts por iteración" directly above a table gets the same caption treatment as "Tabla 1. ..." (a single capital letter is a valid table label, both for the caption and for keeping it with its table). A "Tabla A." line without a table stays a paragraph. Other formats render the AI declaration exactly as before.
S9. Proyecto leftover (user chose "doc_status menciona proyecto: La pregunta de formato hoy lista solo APE, AA, ACD o libre"): the three user-facing format-question strings of `tools/doc_status.py` (near lines 146, 458 and 570) keep the substring "APE, AA, ACD or libre" and add Proyecto in the wording `references/approval.md` uses ("APE, AA, ACD or libre, plus Proyecto for a project report").

## Tasks

- T1 [S1-S7] delegated worker: `tools/build.py` with tests and docs; done (L3): test_build_command.py 12 passed; test_typeset*.py 44, test_doc_status*.py 211, test_report_v1_flow.py 14, test_build_report_auto*.py 50, test_timings.py 27, tests/skills 225 passed.
- T2 [S8] delegated worker: letter-labelled table captions in proyecto; done (L3): test_proyecto_template.py 41 passed (3 new), test_ape_template.py 64, test_aa_template.py 71 passed.
- T3 [S9] delegated worker: format question mentions Proyecto; done (L3): test_doc_status*.py 211, tests/skills 225 passed.
- T4 [S1-S9] parent: full suite, independent verify, land.

## Log

L1. Original request: "que decesiones, con ask to choose", answered through the questionnaire: delivery "Push, PR y merge a main" (done for `typeset.py auto`: PR #127 merged as 179f63f); headers "Cabecera vacía, la completa el agente"; slice 8 "Fase única build"; proyecto "Leyendas Tabla A y B", "doc_status menciona proyecto".
L2. Explorer map: `build_report_auto.py` already refuses while typeset is pending (`typeset.build_gate`, `TYPESET REQUIRED`), builds, validates (`VALIDATION FAILED` / `VALIDATION PASSED`) and writes the generation record; no tool writes `validation.yml` and contract tests pin that no script grants `VISUAL_PASS` (`tests/skills/test_document_workflow_contract.py:976-984`, `test_report_builder_routing.py:380`, `test_visual_builder_contract.py:73,80,110`). Proyecto caption regexes: `tools/build_latex_report.py:1197` and `:1212` require `\d+` after "Tabla". Format-question pins: `tools/test_doc_status_approval.py:316-330` (exact detail string at :330), `tests/skills/test_document_workflow_contract.py:727-749`.
L3. Worker commits on feat/build-command: T1 6a50ce8 `feat(build): add build.py chaining typeset, generate and validate` (S1-S7; `typeset.main` now delegates to a shared `typeset.run(command, folder)` so build.py reuses the exact output; build.py calls `build_report_auto.main()` with its own argv and turns a string SystemExit into stderr + exit 1, as the CLI does; doc_status `build_command` is now build.py and the `typeset_bind_command`/`typeset_check_command` keys are gone; pinned entrypoints updated in `tools/test_doc_status_render_cli.py` (2) and `tests/skills/test_document_workflow_contract.py:226`). T2 cecb1d5 `feat(proyecto): style letter-labelled table captions like numbered ones` (S8; the letter label applies only when `keep_blocks_together or emphasised_tables`, so other formats keep `\d+`). T3 bf3645a `feat(doc-status): offer Proyecto in the format question` (S9; exact detail pin at `tools/test_doc_status_approval.py` updated). Not run here: the full `tools` suite (T4).
