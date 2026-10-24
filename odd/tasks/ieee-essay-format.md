# IEEE essay format

Adds a `format: ieee` document format so an academic essay can be built as an IEEE two-column conference-style PDF through the normal pipeline (typeset, generate, validate, deliver).
First consumer: reports/simulacion-aa-deterministica-vs-estocastica (Simulación AA, tema 18).

## Specs

- S1 — User decision (verbatim choice): "Agregar formato IEEE al pipeline (recomendado)" — "Issue + rama: plantilla IEEEtran (A4, 2 columnas, Times, título 24 pt, cuerpo 10 pt) como formato 'ieee', con tests. Tarda más pero queda para futuros AA y pasa por todos los gates".
- S2 — Teacher format spec (verbatim): "A4 · Dos columnas · Times New Roman · Título 24 pt · Cuerpo 10 pt · 4–6 páginas · Mín. 5 referencias".
- S3 — Teacher structure (verbatim): "Título del ensayo: conciso, máximo 12 palabras / Nombre Apellido¹ / ¹Facultad de Ingeniería, Universidad XXX, Ciudad, País / correo@universidad.edu"; "Resumen— (150–250 palabras, un solo párrafo, sin citas)"; "Palabras clave— simulación; eventos discretos; teoría de colas; M/M/1 (4–6 términos, orden alfabético)."; sections "I. Introducción", "II. Marco teórico y metodología", "III. Desarrollo / Análisis", "IV. Conclusiones", "Referencias".
- S4 — Citations (verbatim): "Citas en el texto con corchetes [1], [2]–[4] antes del punto final."
- S5 — Delivery (verbatim): "Entrega: PDF a 2 columnas con plantilla IEEE".
- S6 — `ieee` passes every pipeline gate (typeset heading checks, generate, validate, visual audit) without AA/APE cover or fixed-section rules; existing formats `aa`, `ape`, `acd`, `libre` keep their current behavior.

## Tasks

- T1 — S1-S6 — map format→template wiring (explore) — no commit
- T2 — S1-S6 — template `templates/ieee-report.tex` + format wiring + tests — commit 59f8c48; fixes 3a0abb8, 08dd41e, 3c92785
- T3 — S2-S5 — build AA18 with `format: ieee` and audit the PDF — no repo commit

## Log

- L1 — User (2026-10-22): "aprobado" (AA18 draft), then chose "Agregar formato IEEE al pipeline (recomendado)".
- L2 — Teacher guide stored at reports/simulacion-aa-deterministica-vs-estocastica/guia-aa.txt.
- L3 — Smoke typeset build of AA18 failed: `Unknown float option 'H'` (figure_placement: here from the Simulación course profile; ieee template lacked float.sty). Fixed test-first in 3a0abb8 (`fix(latex): load float.sty in the ieee template for pinned figures`).
- L4 — Slice boundary: branch holds 838 authored lines in 2 commits (59f8c48, 3a0abb8), past the ~400-line slice. Delivery strategy for review: one PR for the feature with the fix as a separate commit; split only if the reviewer asks (template+wiring vs. tests). Push/PR remain the user's decision.
- L5 — Final AA18 build surfaced overfull boxes: column tables inherited \parindent (10pt) and a long affiliation could not wrap in IEEEtran's tabular author block. Fixed test-first in 3c92785; table gap fixed in 08dd41e. Suite 2624 passed before 3c92785.
