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

Tools record phase durations in `timings.yml` (informational, never a gate; `tools/timings.py <folder>`). Tools check quality (`doc_status`, `content_check --body-check`, verify, `validate_report.py`, visual audit, `deliver_report.py`); run them and relay their non-blocking warnings. There is no draft approval: after data and format the first formatted build is v1, with rubric findings shown honestly; generation is not a compliance claim. The human reviews the formatted version, then asks for v2, v3 or gives an explicit instruction to publish (`references/delivery.md`).

- Present the human block verbatim and every human gate losslessly; never proceed on silence.
- Quality over quantity: no minimum length; preserve complete coverage. Cut redundancy or add necessary evidence or explanation when needed (`references/content.md`).
- Require rubric TDD checks in the plan before drafting; the draft turns them green.
- Keep the rubric visible: `tools/rubric_trace.py` at plan, per draft section, in the v1 findings and in validate (final artifact); at review present `rubric-grade.md` from `tools/rubric_grade.py` with the PDF. Only that tool computes the estimated score; it is informational, never a gate; no agent or verifier assigns one.
- Use one independent verifier for semantic verification (requirement -> evidence matrix, unquotable evidence is `missing`); the drafter never verifies itself.
- A `partial` requirement only a person can close may be accepted by the human alone: `tools/accepted_gaps.py accept` records their name, the exact requirement and reason in `accepted-gaps.yml`; never for `missing` or mechanical failures, on your own initiative or by hand (`references/production.md`).
- Require verified sources before research is finished.
- Apply batched edit orders verbatim, then build the next version; a bounded edit (at most 40 changed words, no heading touched) keeps the final review and the verification without asking; validation still runs.
- The draft is plain text: `# Title` headings and `[@key]` citations only, no math, tables, images or bold (`references/content.md`); backend formatting goes in `body.typeset.md`, never in `body.md`.
- No draft PDF or approval packet is required (`approval.md`). Format, typeset, preview with `build.py`, inspect every page while the verifier works; fix visual and verifier findings in ONE edit round: v1 is the build made after that round. Build v1 once `verify`, `format` and `typeset` are `done`.
- Stop only on a hard failure; never substitute an unsupported backend or executor.
- Publish only through `deliver_report.py`, on the user's explicit instruction; it flags unresolved rubric failures without an accepted gap, unresolved citations, a missing final review or generation record (legacy reports: `APPROVAL_CURRENT`). Publication is not approval.
- No script, validator, or auditor ever grants `VISUAL_PASS`; `visual_pdf_auditor.py` PASS is only `AUDITOR_PRECHECK` evidence. Only independent semantic inspection of the assembled report grants it; `HUMAN_REVIEW` against immutable hashes precedes `READY_TO_SUBMIT`.
- Never ghostwrite a final submission. Preserve privacy, provenance, citations, and consent boundaries.
- Use `academic-visual-builder` for figures and inspect them again in the assembled report; the visual direction changes hierarchy and composition, not only decoration.
- When supplied a research-workflow evidence package, preserve claim-to-source traceability, limitations and unresolved questions; do not treat the package as confirmed document intake: this skill owns intake.
- Route A only: load `references/unl-shell.md` and the `references/profiles/` file matching the subject (`tools/course_profile.py`). Rendering defaults are derived from the confirmed `route:`; an explicit `report.yml` option wins (`references/routing.md`).

## Decision Gates

| Situation | Action |
|---|---|
| `next` names a phase | Load its reference and run its executor (this skill, `research-workflow`, or the verifier). |
| Intake data missing or ambiguous | Stop and ask; recording the contract is never approval. |
| `next: review` | Present the current version with its findings; write `final-review.yml` only on an explicit answer, via `final_review_marker.py record`, never `printf`. |
| Only `partial` requirements stay open | Offer `accepted_gaps.py`; run it only after the user names requirement and reason. |
| Type ambiguous or non-academic | Recommend or resolve a route; never fall back to Route A. |
| Script PASS contradicts visible evidence | Record `VISUAL_FAIL`, correct, rebuild, repeat all gates. |
| Inspection incomplete | Return `REVIEW_REQUIRED`, without `VISUAL_PASS`. |
| `next: done` | Report completion; route no further. |

## Execution Steps

1. Run `doc_status.py`; present the human block verbatim; read `next`. On resume ("continue", "retomá") this is always the first step: `doc_status` decides the phase; never restart from zero or hand a phase to another session or the user when it names its command.
2. Load that reference; run its executor and tools.
3. Apply the correction policy in `approval.md`, preserve user-authored wording, then rerun the affected gates.
4. Re-run `doc_status`; report the new phase.

## Output Contract

Return the verbatim human block, the `academic.doc-status/v1` block, the routed token, the executor, the single artifact produced, hashes and tool results; at `review`, also `rubric-grade.md`. `READY_TO_SUBMIT` only after validation and final review.

## References

- `references/routing.md` - loop, work folders, status block, routes A-E.
- `references/data.md` - Decision 1: intake, `report.yml`.
- `references/content.md` - research, plan, draft, body check.
- `references/approval.md` - Decision 2: format before v1, versions, edit orders, legacy approval.
- `references/production.md` - verify, typeset, generate, validate, quality gates.
- `references/delivery.md` - Decision 3: final review, deliver.
- `references/unl-shell.md`, `references/profiles/` (Route A only), `references/visual-directions.md`.
