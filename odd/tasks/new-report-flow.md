# New report flow (content first, rubric driven)

Feature: `new-report-flow`. Branch: `feat/new-report-flow` (from `main` @ `cf3cc28`).
Worktree: `academic-report-automation-worktrees/pi`.
Engram mirror: topic `odd/new-report-flow/tasks`, project `academic-report-automation`.

## Objective
Replace the format-first document workflow with the user's content-first flow:
the AI drafts content against the teacher's rubric, the user reviews it with literal
edit orders, a hard content check reports findings, and only then the format
(APE, AA or libre, always IEEE) is applied, built, validated, and handed back to the
user for a final review before delivery.

## Problem / why
The current route asks for every formatting detail before a single line is written,
lets research be skipped, and has no notion of the rubric. The teachers require at
least five book or paper sources with a per-document `.bib`, IEEE citations, and
human-sounding prose. Decided with the user on 2026-09-28 (flow v3 diagram).

## Target route
`intake > research > plan > draft > approval > verify > format > generate > validate > review > deliver`

| phase | artifact | done when |
|---|---|---|
| intake | `report.yml` | exists, `title` and `student` present, guide recorded |
| research | `sources.bib` | >= 5 book/paper entries (`research: skipped` removed) |
| plan | `rubric.yml` | valid schema, >= 1 criterion, each mapped to a section |
| draft | `body.md` | present and non-empty |
| approval | `approval.yml` | explicit user approval bound to `body.md` bytes |
| verify | `content-check.yml` | `result: pass` bound to current `body.md` bytes |
| format | `report.yml` `format:` | `ape`, `aa` or `libre` + that format's metadata |
| generate | final PDF | newer than approval |
| validate | `validation.yml` | pass bound to PDF bytes (RDD or fallback) |
| review | `final-review.yml` | explicit user OK bound to PDF bytes |
| deliver | `<slug>-vNNN.pdf` | published copy hash-equal |

## Design decisions
- `preview` phase removed: the draft is the only thing the user reviews.
- A stale approval (body edited after approval) routes back to `approval` as
  `pending`, not `blocked`: editing after approval is the normal review loop.
  Malformed markers stay `blocked`.
- The review loop applies the user's edit orders verbatim; the AI never polishes
  user-authored text. The content check reports findings and never rewrites.
- Source eligibility = BibTeX types `book`, `inbook`, `incollection`, `article`,
  `inproceedings`, `conference`, `phdthesis`, `mastersthesis`, `techreport`.
- `format:` is orthogonal to the internal `route:`; `ape` and `aa` map to the
  academic route, `libre` to a user-specified spec (`format_spec:`) on the plain
  template. Every format uses biblatex `style=ieee`.
- APE = LaTeX replica of the teacher DOCX (no cover, identification table,
  10 fixed sections, Montserrat-like sans, header logo + "FEIRNNR - Carrera de
  Computación"), delivered as PDF.

## Scope / constraints
- Runner: `/home/alejo/devwork/.projects/apps/academic-report-automation/.venv/bin/python -m pytest tools/ tests/`.
- Test-first: observed RED, GREEN, refactor, per task.
- One work-unit commit per task (Conventional Commits, no AI attribution).
- Out of scope: existing documents under `reports/`, other skills' internals.

## Tasks
- [x] T1 Markers: approval binds `body.md` only (drop preview), stale -> pending;
      new `final-review.yml` marker bound to the PDF; deliver/publish require it.
- [x] T2 Research gate: >= 5 eligible book/paper entries in `sources.bib`;
      remove `research: skipped`.
- [x] T3 Rubric plan + content check: `rubric.yml` schema/validator and
      `content-check.yml` validator (per-criterion cumple/flojo/falta + where,
      mechanical checks: citations resolve, >= 5 eligible sources cited).
- [x] T4 Format choice + APE template: `format: ape|aa|libre` in `report.yml`,
      per-format required metadata, template mapping, `templates/ape-report.tex`.
- [x] T5 `doc_status` new 11-phase route, handlers, guidance, tests; content check
      binds `rubric.yml` + bib hashes.
- [x] T6 Rewrite `skills/document-workflow` (SKILL.md + references), contract
      tests, skill sync, flow diagram under `docs/`.

## Evidence
(commit ids recorded per task)
- T1: RED 19 focused failures + missing `final_review_marker`; GREEN `pytest tools/ tests/ -q`
  1222 passed (baseline 1208). Schema kept at `academic.doc-approval/v1`.
  Commit `78ed109`. RDD lineage `review-d6e32b187ef0cee2`: approved (high tier,
  4 lenses), acknowledged/burned. Advisory follow-ups (non-blocking):
  final-review marker has no producer yet (T5/T6 owns it); non-mapping YAML and
  missing-PDF cases in `final_review_marker.py`; gate ownership wording in
  `deliver_report.py`; hidden validated-PDF coupling in `test_pdf_publication.py`.
- T2: RED `source_count` missing + 27 focused failures; GREEN `pytest tools/ tests/ -q`
  1236 passed. `research: skipped` and matrix-only no longer complete research.
  Residual skip prose in `intake.md`, `draft.md`, `preview.md` left for T6.
  Commits `3744470` + correction `ccae95b` (non-UTF-8 `.bib` crashed doc_status;
  now reported as pending). RDD lineage `review-be9fa277b00c6f49`: correction
  validated, approved, acknowledged/burned. Advisory follow-ups: bib regex may count
  nested `@` entries inside field values; `research.md` wording; guidance at
  `doc_status.py:365`.
- T3: RED collection errors (`rubric_plan`, `content_check` missing); GREEN
  `pytest tools/ tests/ -q` 1316 passed (+77). `content_check.py` derives pass/fail
  itself (all criteria `cumple` + mechanical checks) and never writes `body.md`.
  Commit `ee0f6e1`. RDD lineage `review-cad64846ab646d45`: approved, acknowledged/
  burned. Advisory follow-ups taken into T5: content check must also bind
  `rubric.yml` and the bib (stale when they change) and not trust a recorded
  `result` blindly. Others: atomic marker write, body-hash race, id normalization.
- T4: RED import/collection errors + 6 focused failures; GREEN `pytest tools/ tests/ -q`
  1377 passed. Real smoke build (Docker texlive, 5 IEEE refs) passed: 2 pages A4,
  0 overfull, Montserrat embedded, title falls back to TeX Gyre Heros (Play missing).
  Logo extracted from the teacher DOCX to `assets/ape-faculty-logo.png` (root
  `assets/` is the existing asset convention). Open check for E2E: large blank
  space after section 2 on page 1 of the smoke sample.
  Commit `f7bf80c`. RDD lineage `review-c33b299e7587dce7`: approved, acknowledged/
  burned. Advisory follow-ups: annex split ignores code fences; unknown format
  silently falls back to a template; logo copy guard; duplicated APE
  identification contract between `report_config.py` and the builder.
- T5: RED 51 focused failures; GREEN `pytest tools/ tests/ -q` 1399 passed. Route is
  now the 11 phases; `preview` removed. Content check binds rubric + bib hashes,
  re-derives its verdict, and writes atomically. Minimal skill references for
  plan/verify/format/review; full prose rewrite is T6.
  Commit `c5f45ed`. RDD lineage `review-98ebd49eea86fb81`: approved, acknowledged/
  burned. Advisory follow-ups: an empty mechanical list derives a vacuous pass;
  re-derivation trusts the recorded mechanical list; `load_rubric` unguarded in
  the state path; legacy content-check markers block after upgrade.
- T6: RED 11 focused contract failures; GREEN `pytest tools/ tests/ -q` 1410 passed.
  Skill prose rewritten for the 11 phases (minimum intake, verbatim edit orders,
  report-only check, one format question, no detector gate). Diagram at
  `docs/diagrams/new-report-flow.es.{svg,png}`, linked from README. Follow-up:
  `document-intake.md` keeps a "post-preview confirmation" sentence pinned by
  `test_report_builder_routing.py`.

## Pending follow-ups (from E2E test)

Closed items verified on 2026-11-03 in `odd/tasks/report-flow-render-express.md` (T1-T5).
- [ ] Ask the format question (APE, AA or libre) through a structured single-choice
      prompt (`ask_user_choice` / ask-a-question tool), not free text. User request
      2026-09-28; implement at the end of the E2E run.
- [ ] Format metadata the guide does not provide (subject, teacher, cycle, unit,
      learning outcome, practice number, schedule, place, date) is also asked through
      structured choice prompts with suggested options, never as free text.
- [x] Markdown -> LaTeX: an ordered list with a nested bullet list restarts its
      numbering after the sublist (E2E APE PDF page 2: steps 5 and 6 render as 1, 2).
- [ ] Share drafts with the user as the real document (open the PDF / give its
      path), never as rendered PNG page screenshots. Applies to generate and review.
      Always present it as a copy-paste fish command whose lines all stay short
      (the chat wraps long lines and copied newlines break the command):
      `set d ~/<folder>` then `xdg-open $d/<prefix>*.pdf`.
- [x] Figure paths in body.md resolve from `build/`, not the report folder, so
      `figures/x.png` fails and `../figures/x.png` works. Resolve relative to the
      report folder (or document it in draft.md); E2E build failed on it.
- [x] Markdown autolinks `<https://...>` in body.md render as plain text, not
      clickable `\url{}` links (E2E: 4 PR links + commits link had no URI annots;
      only bibliography DOIs were clickable).
- [ ] Citation links are correct in the PDF (GoTo to `cite.0@key`), but `hidelinks`
      gives no visual cue and the user's viewer (zathura) did not follow them on
      click. CONFIRMED 2026-09-28: links work in Brave; zathura is the limitation, not
      the PDF. Optional: visible `colorlinks` for citations.
- [x] deliver_report.py reports "sin HUMAN_REVIEW" even when final-review.yml is
      current for the PDF; grant HUMAN_REVIEW from that marker.
- [x] Content-check judgments are written by the same agent that drafted the body
      (self-grading). Delegate judgments to an independent read-only subagent.
- [ ] Every body edit re-runs verify + generate + validate + RDD. Batch the user's
      edit orders into one round before re-approval; skip RDD re-runs when only
      markers changed.
- [ ] Source verification (CrossRef/Open Library) as a deterministic script, not an
      ad-hoc subagent prompt.
- [ ] Long `\texttt` URLs overflow (13 pt on page 2): render repo URLs with `\url`.
- [ ] Blocked `verify` Gate line repeats "run the check" instead of "fix through the
      user's edit orders".
- [ ] `plan` maps criteria to sections before the format is known; record the
      document family at intake when the guide makes it obvious (APE).

## Scope notes
- The AI-detector limit (<= 20 %) applies only to the course "Simulación"; the flow
  has no percentage gate for any course (user clarification 2026-09-28).
