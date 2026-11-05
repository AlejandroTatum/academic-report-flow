# academic-report-flow skill improvements (rubric, draft, text quality)

Implements the proposals in `docs/portal/mejoras-skill.qmd` (sections (a), (c), (d), (e); slice table in
section 3). Branch: `feat/skill-rubric-improvements` from `main`. Each slice is one commit with tests and the
skill references it changes; `scripts/sync_skills.sh` refreshes the installed skill at the end.

## Specs

- S1 (rubric everywhere, slice 1): "en cuanto a la rubrica, me gustaria que este mas presente en cada punto" —
  a read-only `tools/rubric_trace.py <folder>` that maps every rubric criterion to the sections of `body.md`
  that cover it and reports uncovered criteria; it runs at plan, draft (per section), approval and validate, and
  the approval packet (`approval_packet.py`) shows weight and the trace per criterion.
- S2 (final grading, slices 2-3): "y sobre todo al final, califique sobre eso." — `tools/rubric_grade.py <folder>`
  writes a final table (criterion, weight, evidence location as section and PDF page, estimated score, gap) to the
  working folder (never the delivery folder, `references/delivery.md:28`) and the skill presents it with the PDF in
  `review`. The score is computed by the tool (`weight × found/total`), never by the verifier: user answer to
  question 1, "agrega si" (L2). Defaults for the open questions: weights from the rubric when it has them, else
  equal weights; score shown over the rubric total and as a percentage; `partial` counts 0.5 (S5).
- S3 (rubric on the final artifact, slice 4): rubric checks re-run against `body.typeset.md` and the PDF text in
  `validate`, so losses introduced by typeset are caught.
- S4 (plain draft, slice 9): "el borrador lo da en formato AA, para mayor eficiencia, un formato simple sin logos
  sin plantilla. que abra un pdf temporar con el contenido" — the preapproval draft preview is a plain PDF with no
  cover, logos or course template, written to a temporary directory outside the report and delivery folders and
  opened in the viewer; `doc_status` still detects a stale preview through the recorded `body.md` sha256.
- S5 (guide/rubric gaps, slice 7): a guide requirement inventory that `rubric_plan.py` forces to be mapped to a
  criterion or listed as `not_applicable:` with a reason, and a `partial` state (`found|partial|missing`) in the
  content check, backward compatible with existing `content-check.yml` files.
- S6 (text quality, slice 6): more deterministic lint in `concision.py` (warn-only except unambiguous patterns)
  and `prose_findings` surfaced in the verifier output.

Out of scope until the user decides (questions 5-6 of `mejoras-skill.qmd`): slice 5 (timings, parallel verify)
and slice 8 (`typeset.py auto`, grouping phases).

## Tasks

- T1 (S4): plain draft preview in a temporary PDF — writer A — commit: see git log "feat(approval): plain draft preview" (600 focused tests pass; one manual Docker texlive build)
- T2 (S6): concision lint and prose_findings — writer C — commit: 354babd (242 focused tests pass; docs/portal/herramientas.qmd row update deferred to T1 surface)
- T3 (S1-S3): rubric_trace, rubric_grade, review presentation, validate checks — writer B — commit: "feat(rubric): trace, informational grade and final-artifact checks" (842 focused tests pass)
- T4 (S5): guide inventory and `partial` state — after T3 — commit: pending
- T5: full suite, sync installed skill, PR — parent — commit: pending

## Log

- L1: "quiero que hagas la docuemntacion del proeycto en quarto como los demas repos, mejores readme, y podemos ir planteando mejoras en la skill. aunque por ahora me va regular" (context: odd/tasks/quarto-docs-portal.md)
- L2: "subelos en pages y agrega si. tambien pushea y actualiza la skill"
- L3: Earlier user priorities: "en cuanto a la rubrica, me gustaria que este mas presente en cada punto y sobre todo al final, califique sobre eso."; "Muy lenta / demasiadas fases", "Calidad del texto", "No sigue la rúbrica/guía".
- L5: "exacto solo es informativa" — the rubric grade is informational only: never a gate on review or delivery; `test_skill_tree_adds_no_detector_or_percentage_gate` stays unchanged.
- L4: "tambien otro problema es que el borrador lo da en formato AA, para mayor eficiencia, un formato simple sin logos sin plantilla. que abra un pdf temporar con el contenido"
