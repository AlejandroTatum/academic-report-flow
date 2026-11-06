# Report-flow defects found during Simulación APE 6

Fix the five defects worked around by hand while delivering APE 6, on branch `fix/ape6-flow-defects`.
Evidence: APE 6 work folder `reports/simulacion-ape-6-validacion-chi-cuadrado-ks/` and its build logs.

## Specs

- S1. The APE template font (Montserrat) has no Greek: "Missing character: There is no α (U+03B1) in font name:Montserrat". A Greek letter written as text in body.typeset.md (α, χ, π, λ, Σ...) must render in the final PDF instead of being dropped or extracted as "�".
- S2. tools/validate_report.py rejects "Conclusión inicia/usa fórmulas prohibidas: Se concluye" when "se concluye" appears anywhere in the PDF text (it fired on a control-question answer: "y se concluye que el generador no produce valores uniformes"). The banned openers must only be checked in the conclusions section, as the rule's name says; a phrase elsewhere must not fail validation, and an opener inside the conclusions must still fail.
- S3. tools/course_profile.py with profile simulacion-guaman.md fails: "error: profile simulacion-guaman.md produces an invalid report.yml: uncited_bibliography: no se puede combinar con min_sources". When report.yml already sets `min_sources` (the user asked for in-text citations), the profile must not add `uncited_bibliography`; the rest of the profile defaults still apply.
- S4. In the APE template every markdown table is a grid with equal-width centered X columns (render_table, legacy grid). In a 6-column table "no se rechaza H0" wrapped onto two lines while the numeric columns had empty space. Column widths must follow the content (as render_booktabs_table already does) so short numeric columns do not take the same width as text columns; grid look, centering and page breaking stay unchanged.
- S5. A body list line whose text starts with "[" (for example "- [0.0, 0.1): 1001") becomes `\item [0.0, 0.1): 1001`, which LaTeX reads as the optional label: "! Paragraph ended before \@item was complete." and no PDF. List items whose text starts with "[" must render as normal items.

## Tasks

- [x] T1 (S4, S5) build_latex_report.py: grid widths by content (ape, unl, plain, chamba); list items starting with "[". Route: gentle-ai-worker A. Commit: 8669dd3.
- [x] T2 (S1) APE template Greek fallback font (Libertinus Sans). Route: gentle-ai-worker B. Commit: 7d66c85.
- [x] T3 (S2) validate_report.py conclusions-only banned openers (whole text when no section). Route: gentle-ai-worker B + parent. Commit: 314ab4e.
- [x] T4 (S3) course_profile.py skips uncited_bibliography when min_sources is set. Route: gentle-ai-worker B. Commit: 6665182.
- [x] T5 Full suite (3082 passed) + differential --tex-only on 4 reports + real APE 6 build. Route: parent.

## Log

- L3. Full suite: tools/test_metadata_validation.py::test_banned_openers_flag_found_text failed (text with no Conclusiones heading). Decision: when the conclusions section cannot be located, the banned-opener check falls back to the whole text (as strict as before); only a located section narrows it.
- L2. The legacy grid is shared by the ape, unl, plain and chamba-overleaf templates. User chose "Para todas las plantillas (recomendado)": S4 applies to every legacy-grid template, checked with a differential build of existing reports.
- L1. User: "dale con los pendientes" (after the APE 6 delivery summary listing: la fuente de la plantilla APE no tiene α; el validador busca "Se concluye" en todo el PDF; el perfil del curso fuerza la bibliografía sin citas; la plantilla APE ignora los anchos de columna; una línea de lista que empieza con "[" rompe LaTeX).
