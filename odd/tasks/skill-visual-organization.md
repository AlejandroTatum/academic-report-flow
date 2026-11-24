# Skill: visual organization, tables and layout (academic-report-flow)

Add to the existing academic-report-flow skill and its tools the defaults the user asked for after Redes APE 7: organized, visual reports instead of prose blocks, clean tables and good use of page space. No new skill.
Evidence: APE 7 work folder university/.reports-system/automation/reports/redes-ape-2-fase-2-mac-ip (body.md, body.typeset.md, PDF in outputs/fundamentos-de-redes-de-comunicaciones/).

## Specs

- S1. User verbatim: "me das texto en un solo bloque amontonado, no hay graficos, sueles poner mucha cosa textual" — the skill must default to organized content: each Resultados subsection and each control question carries at least one table, list or own diagram; answers open with a short síntesis and split into subheadings/lists; paragraphs over 120 words fail the body check (80 stays a warning). Earlier user preference (2026-11-19): "prefiero calidad y graficos que cantidad bruta de texto".
- S2. User verbatim: "no hay graficos" — at least one explanatory own diagram (academic-visual-builder) per major concept section is planned and required; "no quota / none is a valid outcome" wording is replaced.
- S3. User verbatim: "hay fallas de espacios vacios en las tablas" — tables built from '- a; b; c' lines take column names from the caption parentheses "Tabla N. Caption (col a; col b; col c)." instead of empty header rows; a check fails on empty header or body cells, ragged rows and cells split by a stray ';'; long unbreakable tokens (MAC, IPv6, IP ranges) can break inside table cells.
- S4. User verbatim: "no estas asigandno bien tema de espacios" — no large blank gaps: figures float by default ([!htbp]-style) unless report.yml asks otherwise; 2+ consecutive screenshots can be grouped (grid) so each does not take a full page; the visual auditor reports blank gaps also on pages with figures.
- S5. Figure robustness (defect found in the delivered APE 7 PDF): a 'Figura:' line merged with the next sentence printed literally ("Figura: Partes de una dirección IPv6 ... (figures/diag-03-ipv6-estructura.png) La Tabla 8 resume..."); typeset must recognize or flag it, and the typeset check must fail on any leftover literal 'Figura:' text.
- S6. User verbatim: "osea quiero agregar a la skill que ya tenemos" — changes go into the existing skill academic-report-flow and its tools; no new skill. Keep the "never block delivery / warn-only" user preference for delivery gates: new checks fail body-check/typeset-check (work-time checks) but never block deliver_report.

- S7. User verbatim (on whether typeset checks block the build): "podriamos ahcer la regla salte en ciertas materias, por ejemplo en redes va de ley" — table_cells/figure_leftovers (and the existing typeset checks) block build only for subjects that opt in; Redes opts in; other subjects get warnings. Delivery is never blocked.
- S8. User choice: "Commit aparte con tests al día" for the uncommitted templates/ape-report.tex change. Grid default kept: "Cualquier imagen seguida (Recomendado)".

## Tasks

- [x] T1 (S1, S2, S6) skill rules: SKILL.md, references/content.md, references/visual-directions.md, references/production.md + tools/concision.py paragraph threshold (fail > 120 words) with tests — writer W1.
- [x] T2 (S3, S5) typeset tools: tools/typeset_auto.py, tools/typeset.py headers from caption parentheses, cell audit, inline/leftover 'Figura:' handling, with tests — writer W2.
- [x] T3 (S3, S4) layout: tools/build_latex_report.py float default + screenshot grouping + breakable tokens in table cells, tools/visual_pdf_auditor.py gaps on figure pages, with tests — writer W3.
- [x] T4 verify (Risk: item 3, shared build/typeset code used by every report) — independent verifier; rebuild APE 7 to compare.
- [x] T6 (S7) per-subject typeset gate: report.yml `typeset_gate: block|warn` (default warn); Redes reports block (profile/intake sets it); build.py, build_report_auto.py and doc_status honor it — writer.
- [x] T7 (S8) commit the user's templates/ape-report.tex change on its own with the 2 test_ape_template expectations updated — inline.
- [x] T5 commits per unit on feat/visual-organization; push/PR is the user's call.

## Log

- L1 (2026-11-24) User: "listo ya lo entregue, pero veo falencias en la skill ahora que reviso bien, me das texto en un solo bloque amontonado, no hay graficos, sueles poner mucha cosa textual, hay fallas de espacios vacios en las tablas. y no estas asigandno bien tema de espacios, revisalo y contrastalo"
- L2 Audit (gentle-ai-explore): plain-text draft rule SKILL.md:32/content.md:38; concision.py:492-494 long_paragraphs always ok; content.md:36 + visual-directions.md:12 graphics optional; typeset_auto.py:151 empty header rows, :23 Figura regex needs whole line, :82-87 ';' split; build_latex_report.py:1074-1076 pads cells, ~887 tabularx X no token breaking, :1483-1484 [H] + Needspace; ape-report.tex:61 FloatBarrier per subsection; visual_pdf_auditor.py:99-114 whitespace check exempts image pages.
- L3 User answer to which fixes: "osea quiero agregar a la skill que ya tenemos" (interpreted: all four areas, inside the existing skill).
- L4 Note: templates/ape-report.tex has an older uncommitted user change (biblatex Spanish strings); not part of this feature, writers must not touch it.
- L5 (2026-11-24) T1-T3 done by W1-W3 (uncommitted). APE 7 rebuilt with new tools: typeset auto regenerated 12 tables/20 figures with zero manual fixes, all typeset checks ok, 29 -> 25 pages, no overflow, auditor no warnings; screenshots in 2-per-row grids. Comparison PDF ~/Downloads/APE2-F2-comparacion-skill-nueva.pdf; previous in backups/pre-skill-rebuild. Verifier mwuxv7sa-9-twt5 running.
- L6 Verifier T4: S1,S3,S4,S5 pass; S2 partial (diagram requirement enforced only via plan deliverables); S6 partial (typeset checks gate build). SKILL.md trim lost ': this skill owns intake' -> restored, new rule line shortened to keep the 1000-word budget (tests/skills 242 pass). 2 test_ape_template failures confirmed caused by the user's template change (pass with HEAD template).
- L7 User answers: gate -> "podriamos ahcer la regla salte en ciertas materias, por ejemplo en redes va de ley"; grid -> "Cualquier imagen seguida (Recomendado)"; template -> "Commit aparte con tests al día".
- L8 Commits on feat/visual-organization: 65fbf35 T7 template; 183651f T1 rules; f9bd765 T3 layout (+ typeset_gate key validation in report_config); 70985de T2+T6 typeset + per-subject gate + Redes profile. Full suite at tip: 3576 passed. Existing Redes report.yml files lack typeset_gate (default warn) until course_profile.py runs or the key is added. Push/PR: user's decision.
