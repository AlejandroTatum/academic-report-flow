---
name: academic-report-flow
description: "Trigger: academic report, exercise/ejercicio, homework/tarea, APE, AA, university report, project documentation, professional or business report, technical document, PDF, DOCX, doc status, resume or approve report. Drives doc_status phases."
license: Apache-2.0
metadata:
  author: "gentleman-programming"
  version: "4.0"
  scope: "full-report-flow"
---
## Activation Contract

Use for creating, adapting, reviewing, exporting, resuming, or advancing a structured academic, project, professional, business, technical, PDF, or DOCX document. PDF or DOCX is a format signal only. The user chooses the document type; never infer it from format, prompt, files, or history.

Entry rule: a new request creates the work folder `$REPORT_CONTENT_ROOT/reports/<slug>/` before `doc_status.py` (empty folder -> `next: intake`); an existing folder for the same document is resumed. The standalone full route (`references/data.md`) applies only when the work-folder flow is unavailable. Loop: `doc_status -> next -> reference -> delegate -> re-run`; load only the reference `next` names (`references/routing.md`); intake data (`references/data.md`) never authorizes generation.

### Prohibition On Inferring Document Type

Recommend at most one type with a reason, never select it. Ambiguity stops the run; there is no default document type or academic fallback. Sole exception: content-first intake records `route: academic` when the request names an academic assignment (`references/data.md`).

## Hard Rules

Tools enforce quality (`doc_status`, `content_check --body-check`, verify, `validate_report.py`, visual audit, `deliver_report.py`); run them and obey their blocks. Three human decisions: data, draft approval plus format, final review.

- Present the human block verbatim and every human gate losslessly; never proceed on silence.
- Quality over quantity: no minimum length; every paragraph answers a guide requirement, and findings are fixed by cutting, never by adding prose (`references/content.md`).
- Require rubric TDD checks in the plan before drafting; the draft turns them green.
- Use one independent verifier for semantic verification (requirement -> evidence matrix, unquotable evidence is `missing`); the drafter never verifies itself.
- Require verified sources before research is finished.
- Apply batched edit orders verbatim before seeking re-approval; a bounded edit (at most 40 changed words, no heading touched) keeps the approval and the final review without asking, and verify, rebuild and validation still run.
- The draft is plain text: `# Title` headings and `[@key]` citations only, no math, tables, images or bold (`references/content.md`); backend formatting goes in `body.typeset.md` after approval, never in `body.md`.
- Never build before approval is `done` and `typeset` passes; never present the approval gate before `draft` is `done`.
- Stop at the earliest failed gate; never substitute an unsupported backend or executor.
- Publish only through `deliver_report.py` with a current `APPROVAL_CURRENT` marker; publication is not approval.
- No script, validator, or auditor ever grants `VISUAL_PASS`; `visual_pdf_auditor.py` PASS is only `AUDITOR_PRECHECK` evidence. Only independent semantic inspection of the assembled report grants it; `HUMAN_REVIEW` against immutable hashes precedes `READY_TO_SUBMIT`.
- Never ghostwrite a final submission. Preserve privacy, provenance, citations, and consent boundaries.
- Use `academic-visual-builder` for figures and inspect them again in the assembled report; the visual direction changes hierarchy and composition, not only decoration.
- When supplied a research-workflow evidence package, preserve claim-to-source traceability, limitations and unresolved questions; do not treat the package as confirmed document intake: this skill owns intake, composition, and document creation.
- Route A only: load `references/unl-shell.md` and the `references/profiles/` file whose front-matter `match:` fits the subject (`tools/course_profile.py`). Rendering defaults are derived from the confirmed `route:`; an explicit `report.yml` option wins (`references/routing.md`).

## Decision Gates

| Situation | Action |
|---|---|
| `next` names a phase | Load its reference and run its executor (this skill, `research-workflow`, or the verifier). |
| Intake data missing or ambiguous | Stop and ask; recording the contract is never approval. |
| `next: approval` / `next: review` | Present the gate; write `approval.yml` / `final-review.yml` only on an explicit answer; record them with `approval_marker.py approve` / `final_review_marker.py record`, never `printf`. |
| Type ambiguous or non-academic | Recommend or resolve a route; never fall back to Route A. |
| Script PASS contradicts visible evidence | Record `VISUAL_FAIL`, correct, rebuild, repeat all gates. |
| Inspection incomplete | Return `REVIEW_REQUIRED`, without `VISUAL_PASS`. |
| `next: done` | Report completion; route no further. |

## Execution Steps

1. Run `doc_status.py`; present the human block verbatim; read `next`.
2. Load that reference; run its executor and tools.
3. Fix findings only through the user's literal edit orders, then rebuild and rerun the gates.
4. Re-run `doc_status`; report the new phase.

## Output Contract

Return the verbatim human block, the `academic.doc-status/v1` block, the routed token, the executor, the single artifact produced, hashes and tool results. `READY_TO_SUBMIT` only after approval and final review.

## References

- `references/routing.md` - loop, work folders, status block, routes A-E.
- `references/data.md` - Decision 1: intake, `report.yml`.
- `references/content.md` - research, plan, draft, body check.
- `references/approval.md` - Decision 2: approval plus format.
- `references/production.md` - verify, typeset, generate, validate, quality gates.
- `references/delivery.md` - Decision 3: final review, deliver.
- `references/unl-shell.md`, `references/profiles/` (Route A only), `references/visual-directions.md`.
