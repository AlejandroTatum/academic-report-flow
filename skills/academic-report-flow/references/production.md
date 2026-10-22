# Production - verify, generate, validate, quality gates

Tools enforce quality between Decisions 2 and 3: run each, report findings, never polish silently. Roots and interpreter: `routing.md`.

## Verify (artifact `reports/<wf>/content-check.yml`)

Runs after the draft passes the body check and before `approval`, so the approval packet (`approval.md`) carries the matrix. A failing verify shows the user that same packet (`approval_packet.py <folder> --open`) to collect literal edit orders; after the edits rebuild the draft PDF and re-verify with `--since`.

1. `"$REPORT_PYTHON" "$REPORT_AUTOMATION_ROOT/tools/content_check.py" "$REPORT_CONTENT_ROOT/reports/<work-folder>/" --verify-brief`. Do not pass the drafting conversation to the verifier.
2. Give its exact output to ONE independent read-only verifier subagent. It never scores: it returns the requirement -> evidence matrix YAML the brief specifies (per rubric criterion, one or more `requirement` entries with `status: found|missing`, `location`, and `evidence`, an exact quote from `body.md`, required when `found`; plus `unmapped_paragraphs` and `findings`). Evidence it cannot quote is `missing`, never "seems to comply".
3. Save the YAML unchanged as `verification.yml`; the drafting agent never writes verification.yml. Run `content_check.py <folder> --verification verification.yml`.
4. The tool validates the file; a `found` requirement whose exact quote is not in `body.md` (whitespace-normalized) is downgraded to `missing` with a finding; a criterion is `cumple` when all its requirements are found, `falta` otherwise. It adds the mechanical checks (citations resolve; at least 5, or the report's `min_sources:`, eligible sources cited, or with `uncited_bibliography: true` at least 1 bib entry and no citation required; `links_resolve`: every http(s) URL in the body is opened, an HTTP error fails, a timeout or DNS failure only warns) and writes `content-check.yml` bound by hash to body, rubric, bib and guide. A stale marker means re-run the verifier on current inputs; a verification is reused only when the body change is markup-only (same `body_text_sha256`, same rubric). Legacy markers with `judges:` stay valid.
5. Re-verify after an edit: run step 1 with `--since verification.yml` (the previous file). The brief lists only the criteria whose mapped section changed for re-check; the verifier returns requirements for those criteria only (an empty list when none changed). Step 3 merges the carried-over requirements itself from the previous `content-check.yml` (same rubric, same section hash, criterion absent from the answer) and re-checks their quotes against `body.md`; the marker lists them under `carried_criteria`. A rubric change forces a full verify. Then continue with steps 2-4 as usual.

When the executor cannot launch subagents, it stops at verify and reports the verifier pending; the orchestrator runs the verifier exactly as above (brief verbatim, one independent read-only subagent, YAML saved unchanged) and the executor never stands in for the verifier.

The check only reports (per-criterion `cumple|falta`, the requirement matrix with missing items, citation and link problems, unmapped paragraphs as deletion candidates). It never rewrites `body.md`; never add requirements for criteria the plan does not name. Report every finding verbatim and collect literal edit orders (`approval.md`); unmapped paragraphs are proposed for deletion, never added to. A recorded `fail` blocks the route (`content_check_failed`) until fixed; an edited draft stales the marker and reruns the check.

## Typeset (artifact `reports/<wf>/body.typeset.md`, bound by `typeset.yml`)

Runs after approval and `format`, before generate: the approved `body.md` is plain text, so backend formatting is applied only in its copy and never invalidates verified or approved content.

1. `"$REPORT_PYTHON" "$REPORT_AUTOMATION_ROOT/tools/typeset.py" bind "$REPORT_CONTENT_ROOT/reports/<work-folder>/"` copies `body.md` to `body.typeset.md` when missing and writes `typeset.yml` with the `body.md` sha256. It refuses while the approval is neither current nor carried.
2. Format `body.typeset.md` only: formulas as math, data as tables, `Figura: caption (path.png)` lines as `![caption](path.png)`, bare URLs as links, the format's fixed headings. Keep every word and `[@key]` of `body.md`; never touch `body.md`.
3. `typeset.py check <folder>` passes only when the binding matches the current `body.md`, the typeset body passes the format check (level-1 headings, no Unicode sub/superscripts, no bold pseudo-headings) and the format's fixed headings, and it cites exactly the same `[@key]` set as `body.md`. Run it until it passes (`doc_status` shows `typeset: done`).
4. A bounded edit of `body.md` after approval stales the binding: re-bind and re-apply the edit in `body.typeset.md`.

Legacy: an `approval.yml` without `typeset: required` predates this phase; its report needs no typeset (`done`) and `body.md` renders as before. Both tools exit non-zero on failure and print the finding.

## Generate (artifact: the final PDF under `outputs/<materia>/`)

Runs only when `approval: done` (`approval.yml` exists and its `body_sha256` matches the current `body.md`) and `typeset: done`. Never build before approval is done; the final build prints `TYPESET REQUIRED` while a required typeset is not current.

`"$REPORT_PYTHON" "$REPORT_AUTOMATION_ROOT/tools/build_report_auto.py" "$REPORT_CONTENT_ROOT/reports/<work-folder>/"` builds from `report.yml` (including `format:`) plus `body.typeset.md` while its binding is current (otherwise the approved `body.md`), runs the configured technical validation, and reports the artifact hash and page count. A final PDF older than `body.typeset.md` is stale (generate pending). It does not publish, copy or version, and never writes `approval.yml` or claims `VISUAL_PASS`, `HUMAN_REVIEW` or `READY_TO_SUBMIT`. Final PDF/DOCX stay under `outputs/<materia-slug>/`, intermediates in `build/` or `backups/`.

Optional `figure_placement: here` in `report.yml` pins every figure where it appears in `body.md` (LaTeX `[H]`) instead of letting it float to the end of its section or subsection (a figure never crosses the next heading of either level); the default `float` keeps today's output, and any other value is rejected.

## Validate (`next: validate`, artifact `reports/<wf>/validation.yml`)

Receipt schema `academic.doc-validation/v1`: `artifact_sha256`, `result: pass|fail`, `mode: fallback`, `gates`, `recorded_at`, `evidence`, optional `reason`, and `bibliography_sha256` only when `report.yml` sets `deliver_bibliography: true`. There is no production writer: the executor records the hashes. Done = `result: pass` and `artifact_sha256` matches the current PDF; `fail` is `blocked` (`validation_failed`); a missing receipt or stale hash stays `pending`.

When `deliver_bibliography: true`, the receipt also records the exact SHA-256 of the declared `.bib`, written only after the applicable checks pass; missing, malformed or stale keeps validate pending and delivery refuses.

Document validation never uses RDD: the work folder lives in the content root, outside the session's repository, so a native review would always stop to ask. Run the chain below regardless of the global review switch, without probing it and without asking; RDD stays for code changes in the automation repository. Older receipts may still say `mode: rdd`; they are read like any other receipt.

Chain (`mode: fallback`, `evidence: backups/quality_report.md`), in order:
1. `"$REPORT_PYTHON" "$REPORT_AUTOMATION_ROOT/tools/validate_report.py" "$REPORT_CONTENT_ROOT/reports/<work-folder>/"`: `common` is mandatory and PDF output also needs `pdf_layout` (only `--tex-only` skips it).
2. `"$REPORT_PYTHON" "$REPORT_AUTOMATION_ROOT/tools/visual_pdf_auditor.py" "$REPORT_CONTENT_ROOT/outputs/<materia-slug>/<final-pdf>.pdf"`: report and `contact_sheet.png` are `AUDITOR_PRECHECK` evidence only (manual unless `validators: {visual_pdf: true}`).
3. Rendered readback and semantic inspection: headings, paragraphs, captions, bibliography, tables and figure labels present, legible and equivalent to the source.

Gates: `BUILD_PASS`, `VALIDATION_PASS`, `VISUAL_PASS`, `HUMAN_REVIEW`, `READY_TO_SUBMIT`; the chain never lowers, skips or renames one, or grants one it did not verify on the same immutable artifact. Validation is not approval.

| Gate | Proof |
|---|---|
| `APPROVAL_CURRENT` | `approval.yml` current for the exact `body.md` bytes |
| `BUILD_PASS` / `VALIDATION_PASS` | build completed / validators pass (layout still unproven) |
| `VERSIONED_PDF_PUBLISHED_OR_REUSED` | precondition `APPROVAL_CURRENT`; PDF-only version published or hash-reused; not approval |
| `VISUAL_PASS` | readback plus direct page inspection pass on one immutable artifact |
| `HUMAN_REVIEW` | `final-review.yml` for the same bytes |
| `READY_TO_SUBMIT` | every previous gate passes, artifacts unchanged |

`VISUAL_PASS` ownership: the validate phase executor that performed the direct page-by-page inspection (every page rendered and read back, or after a correction the pages `visual_qa.md` lists as changed, no blocking defect) records `VISUAL_PASS` in `validation.yml` `gates:` and notes it in the evidence report; a receipt without an inspection never records `VISUAL_PASS`. `READY_TO_SUBMIT` follows once `HUMAN_REVIEW` exists for the same bytes (`deliver_report.py` derives it).  Never write `approval.yml`, `body.md` or `report.yml` here.

## Quality gates (inspection a tool cannot do)

Visible evidence overrides automation: a visible blocking defect fails the artifact even when every script passes. Record the artifact hash and page count first; inspect every contact-sheet page and open every page with diagrams, figures, captions or tables at readable size. After any correction rebuild the whole artifact and rerun every tool on it; explain material page-count changes. The auditor compares rendered pixels with its previous run in the same output folder (`page_hashes.json`): `visual_qa.md` lists the **Changed pages** and `changed_contact_sheet.png` shows them. Inspect only those pages again; a pixel-identical page keeps its earlier verdict. A first audit, a DPI change or `Changed pages: first audit` means inspect every page.

Blocking defects:
- Academic route only: cover on page 1, body from page 2, UNL logo present.
- Headings without substantial following content (orphan heading: after a heading the same page must fit two lines of body text, a table header plus one data row, or a complete figure); clipped images, overfull boxes, accidental blank pages, pages under 20% meaningful content, half-empty pages from table pagination. `visual_pdf_auditor.py` only warns on orphans; inspect before deciding.
- Whitespace: over 40% of the lower page empty without a natural section close. An intentional gap or natural close is approvable only with a recorded visual justification; page-break space, an unsplit table or a page holding an isolated title is a defect. Record every page under 20% content, over 40% lower empty, heading before a page break, or whole table displaced.
- Tables render as real grids (visible rules, distinct header, legible type; never raw Markdown pipes). Remove unneeded columns before compressing; split wide tables (e.g. `Code | Actor | Requirement | Priority` and `Code | Acceptance criterion`). Broken tables repeat the header. With `table_styles: {enabled: true}` every table needs a `<!-- table-style: <key> purpose=... -->` directive; run `tools/check_table_contexts.py <dir>`.
- Type shrunk to fit is a defect; a table that cannot split is a defect unless a split was attempted.
- Figures: lower border clears the footer, terminal nodes complete, no clipped or overlapped node or connector, full caption attached to the right asset. Each diagram models its module's real decisions and visually differentiates user, system, internal module, external service, validation, error, retry and final state. Diagrams that only restate the text, clipped terminal nodes and captions detached from their figure are defects. Reject repeated templates, generic decisions such as `¿Validación correcta?`, flows with no real alternatives, ambiguous arrows.
- Practice reports keep each exercise self-contained (data first, process and evidence after); conclusions never open with formulaic `Se concluye`; validate the rendered bibliography (IEEE, or APA with `citation_style: apa`), not only the `.bib`.
