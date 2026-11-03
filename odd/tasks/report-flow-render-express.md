# Report flow: render/delivery fixes and express mode for daily documents

Feature: `report-flow-render-express`. Branch: `feat/report-flow-render-express` from `origin/main` @ `553212f`.
Engram mirror: topic `odd/report-flow-render-express/tasks`, project `academic-report-automation`.
Runner: `.venv/bin/python -m pytest tools/ tests/`. RDD: user-left-unreviewed for this skill (preference `preference/no-rdd-with-report-skill`).

## Specs

- S0 (found 2026-11-03) The `.githooks` sync published skills from any checked-out branch: switching this worktree to a feature branch rsynced its skills into the live runtimes. Only `main` may publish.
- S1 (from `odd/tasks/new-report-flow.md` follow-ups) "Markdown -> LaTeX: an ordered list with a nested bullet list restarts its numbering after the sublist (E2E APE PDF page 2: steps 5 and 6 render as 1, 2)."
- S2 "Figure paths in body.md resolve from `build/`, not the report folder, so `figures/x.png` fails and `../figures/x.png` works. Resolve relative to the report folder (or document it in draft.md); E2E build failed on it."
- S3 "Markdown autolinks `<https://...>` in body.md render as plain text, not clickable `\url{}` links (E2E: 4 PR links + commits link had no URI annots; only bibliography DOIs were clickable)."
- S4 "deliver_report.py reports "sin HUMAN_REVIEW" even when final-review.yml is current for the PDF; grant HUMAN_REVIEW from that marker."
- S5 "Content-check judgments are written by the same agent that drafted the body (self-grading). Delegate judgments to an independent read-only subagent."
- S6 Advisory review follow-ups listed in `odd/tasks/report-flow-issues-79-85.md` (R3-exemption-requires-verbatim-render, R3-lazy-import-path, R3-patterns-vs-collapsed-text, R3-whitespace-free-first-occurrence-cut): fix each that is still real, or record why it is not.
- S7 Daily documents: routes B-E (project, business, one-pager, other) get profiles like Route A has, and an express path with fewer gates for quick professional/business documents, without weakening the academic route. Exact gate design is a user decision taken before T7 starts.

## Tasks

- [x] T0 S0 skills sync hook publishes only from `main` — parent — commit: (this commit)
- [x] T1 S1 nested lists already render (tools/test_latex_links.py::test_nested_list_preserves_enumerate_and_continuation); real root cause was an interrupted list restarting at 1, fixed with \setcounter — parent — commit: (this commit)
- [x] T2 S2 already fixed: tools/test_figure_paths.py (report-relative precedence + legacy build-relative) — no commit
- [x] T3 S3 already fixed: tools/test_latex_links.py::test_autolink_and_named_link_are_clickable — no commit
- [x] T4 S4 already fixed: tools/deliver_report.py:167 grants HUMAN_REVIEW from a current final-review.yml — no commit
- [x] T5 S5 already in skill: references/production.md:10-15 (one independent read-only verifier; drafter never verifies) — no commit
- [x] T6 S6 reviewed against tools/validate_report.py:672-750,886-896, no code change: verbatim-render — a listing the PDF does not hold verbatim removes nothing, so it fails toward a false positive, never a hidden defect (docstring L712-714); lazy-import — same in-function `from build_latex_report import` pattern used at L290/340/590/915, tools/ is always on sys.path; patterns-vs-collapsed-text and first-occurrence-cut — the check only counts occurrences (L893-896); cutting the first match instead of the code's own one keeps the count, so detection is unchanged; a hidden defect needs a code span whose whitespace-free text straddles half of a prose command, no realistic reproducer found — no commit
- [ ] T7 S7 express mode + route B-E profiles — after user decision — commit:
- [ ] T8 sync skills to runtimes after merge (user authorizes integration) — parent — commit:

## Log

- L1 (2026-11-03, user, verbatim) "tengo que quemar tokens, pero no quiero iniciar nada nuevo, quiero ocuparlos para ir cerrando planes pendientes, limpiando worktrees y demas, revisa en que podemos usarlos, creo que la skill de documentos y proyectos asi del dia hay que irlos mejorando ya actualizando. revisa porfavor y me traes el plan para aprobarlo"
- L2 (2026-11-03) User approved blocks 5c (render/delivery bugs with tests) and 5d (express mode + project/business profiles).
- L3 (2026-11-03) Ask-format-as-structured-choice items from new-report-flow.md are excluded here: verify whether the skill already does it before reopening.
