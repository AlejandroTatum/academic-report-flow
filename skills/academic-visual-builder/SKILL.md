---
name: academic-visual-builder
description: "Trigger: figures, graphs, diagrams, infographics, academic visuals. Generates and validates visuals for Alejandro's UNL reports."
license: Apache-2.0
metadata:
  author: "gentleman-programming"
  version: "1.2"
  scope: "figures-and-visuals"
---

## Activation Contract

Use for figures, diagrams, charts, infographics, photo evidence, visual specs,
rendering, or visual checks before a PDF/DOCX export. This skill owns visual
assets only; `academic-report-flow` owns prose, assembly, and report readiness.

## Hard Rules

- Prefer original, editable SVG visuals. Keep specs and generated assets in the paths defined by `references/visual-workflow.md`.
- Concept maps and process maps default to the Bauhaus técnico style (`references/bauhaus-maps.md`): write a YAML spec and render it with `tools/bauhaus_maps.py` (`concept_map`, `process_map`); never draw them by hand or substitute another look. A layout over 860 SVG units is split or shortened, never shrunk.
- Other diagrams keep the editorial technical style (`references/editorial-style.md`): `tools/editorial_svg.py` `actor_map`, hand-written SVG when no layout fits. Every figure passes `editorial_svg.py check` (5.5 pt printed) and is shown to the user at full size before insertion.
- Visual assets, specs, manifests, and audits are working evidence: they live in the repo-defined work paths and are never copied to the user's Documents delivery folder. Only the final assembled PDF/DOCX produced by `academic-report-flow` reaches that folder; see `references/delivery.md` in that skill.
- Every manifest must follow `references/figures-yml-schema.md`. Require stable unique `request_id`/`result_id`, raw-byte SHA-256, source/provenance, explicit license text and status, canonical section, caption, and `alt_text` accessibility text.
- Treat `section` as canonical; accept `intended_section` only when section is absent or identical after trimming. Reject conflicts and integrity mismatches; never silently crop, substitute, overwrite, or accept unknown licensing.
- Validate asset existence, listed/unlisted assets, metadata, readability, clipping, and photo rules before insertion. Stop on missing metadata, duplicate identity, missing/unreadable/mutated assets, or unavailable dependencies. Renderer values remain open-ended; unsupported dependencies fail explicitly.
- The visual PDF auditor PASS is automated `AUDITOR_PRECHECK` evidence only; the auditor does not grant `VISUAL_PASS`. Direct semantic inspection of the assembled report owns report-level `VISUAL_PASS`; `HUMAN_REVIEW` after immutable hashes is required for `READY_TO_SUBMIT`.
- Diagram connectors are checked automatically, not by eyeballing: `tools/visual_builder.py validate` runs the isolated `connector_geometry` precheck (obstruction, unnecessary crossing, 0.80 SVG-unit minimum clearance, source/target/marker direction), and `validate_report.py`'s LaTeX visual validator independently re-audits every diagram SVG at its actual final print scale via `connector_pdf_stage`, warning on an open connector defect there too (warn-only, never blocking). Neither run substitutes for the other, and neither grants `VISUAL_PASS` — both stay `AUDITOR_PRECHECK` warning evidence.
- Keep private evidence local unless explicit scoped upload consent exists; redact secrets from diagnostics and provenance.

## Decision Gates

| Need | Renderer |
|---|---|
| Concept map or process map | `bauhaus_maps.py` (Bauhaus técnico) |
| Other flow/tree | Mermaid |
| Chart/comparison | Vega-Lite / Altair / vl-convert |
| Dashboard-like visual | ECharts SVG SSR |
| Custom card | HTML + Playwright |
| Unsupported dependency | Fail; do not substitute silently. |

## Execution Steps

1. Load `references/figures-yml-schema.md` and `references/visual-workflow.md`; choose the visual and distinguish generated figures from photos.
2. Create the editable spec and complete manifest before drafting; render with the canonical local toolchain.
3. Run `tools/visual_builder.py validate`, then run the report validator when the asset is assembled. Retain hashes and provenance.
4. Inspect the complete assembled report and applicable full-size pages directly; use the auditor only as precheck evidence. Report defects and stop on failure.

## Readiness Model

`BUILD_PASS → VALIDATION_PASS → AUDITOR_PRECHECK → RENDERED_READBACK →
SEMANTIC_VISUAL_INSPECTION → VISUAL_PASS → HUMAN_REVIEW → READY_TO_SUBMIT`.
Only the parent report skill can expose final report readiness.

## Output Contract

Return asset paths, request/result IDs, manifest status, renderer, raw-byte hashes,
source/license status, alt text, validation/precheck result, semantic-inspection
evidence, and readability/layout issues. Never imply `HUMAN_REVIEW` or readiness.

## References

- `references/figures-yml-schema.md` — executable metadata contract and examples.
- `references/visual-workflow.md` — asset classes, photo rules, renderer gates, and commands.
- `references/bauhaus-maps.md` — Bauhaus técnico tokens, `concept_map` and `process_map` schemas, limits, commands; examples in `assets/examples/`.
- `references/editorial-style.md` — editorial tokens, print-size rule, `actor_map` layout.
