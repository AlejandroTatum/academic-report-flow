# Project format (AA look, no sidebar)

Objective: a `format: proyecto` report variant that keeps the AA visual identity but carries no AA labels and no sidebar, for a university group project report (Sistemas Digitales, Jarvis ESP32).
Branch: feat/project-format (worktree `academic-report-automation-worktrees/project-format`); base: main e0f258d. Runner: `.venv/bin/python -m pytest -q -p no:cacheprovider tools/test_aa_template.py` (the venv lives in the main checkout: `/home/alejo/devwork/.projects/apps/academic-report-automation/.venv/bin/python`).

## Specs

S1. "quita este apartado de la plantilla y del doc" (screenshot of the AA ficha entry "TIEMPO EN EL SÍLABO / Tiempo de ejemplo") — the AA ficha never prints a syllabus-time entry, even when `planned_time` is set. Already implemented in the working tree (uncommitted): `tools/build_latex_report.py`, `tools/test_aa_template.py::test_aa_ficha_never_prints_syllabus_time`.

S2. "no bro usa la de aa, pero para proyecto" — a project report uses the AA template's look (UNL header with logo, faculty and career lines, typography, colours, numbered green headings, AA table style) but is a project, not an "Aprendizaje autónomo" activity. Parent decisions for the variant, selected with `format: proyecto` under `route: academic`:
  - the large title reads "Proyecto" and the italic subtitle is `metadata.title`;
  - the eyebrow reads "PROYECTO · <SUBJECT>" and the running header on later pages reads "PROYECTO · <SUBJECT>"; no "AA-<n>", "ACTIVIDAD" or "Aprendizaje autónomo" text appears anywhere in the output;
  - required metadata: `title`, `subject`, `teacher`, `student`, `date`; `cycle`, `parallel` optional;
  - the AA required-section check (Objetivo(s), Introducción, Desarrollo, Conclusiones) does not apply to `format: proyecto`; no section list is enforced.
  - existing `format: aa` output must stay byte-identical apart from S1.

S3. "y la barra lateral de la informacion manejalo de manera normal, sin barra el documento" — in `format: proyecto` there is no sidebar: the identification data is a normal full-width table in the document flow, right under the title block and before the first section, and the body uses the full text width on every page. Rows, in order, omitted when the value is absent: Integrantes (`student`), Asignatura, Ciclo (with ", paralelo X" when both are set), Docente, Fecha de entrega. No "Unidad", "Resultado de aprendizaje", "Actividad" or syllabus-time row.

S4. Observed defect in the AA preview: the heading "4 Presupuesto" stayed alone at the bottom of page 1 while its table went to page 2, and after S1 a four-row table split with its total row alone on page 2. In `format: proyecto` a section heading is never separated from the first lines of its content, and a short table (up to about 12 rows) is not split across pages.

S5. "centra el tittulo y el encabezafo" — in `format: proyecto` the title block (eyebrow "PROYECTO · <SUBJECT>", large title "Proyecto", italic subtitle) is horizontally centred on page 1, and so is the header: the page-1 letterhead (logo plus the three institution lines, centred as one group) and the running header on later pages.

S6. "mejora als tablas" — parent reading for `format: proyecto`: (a) the identification table is compact and aligned: each label sits on the same baseline as the first line of its value (the `\leavevmode` fix already in `\proyectodato` must stay), label column no wider than needed, rows not taller than the text needs; (b) data tables get a clearly distinguished header row (light tint background, bold sans labels), numeric columns right-aligned with the header aligned the same way, a visually distinct total row (bold, rule above) when the last row's first cell starts with "Total", and comfortable row spacing; no vertical rules.

S7. "un solo formato para los titulos" — in `format: proyecto` every heading level uses one style family: the section style (sans, bold, green, number in the same face). Subsections and sub-subsections differ from sections only by size; no italic serif heading and no differently styled number.

S8. Defects the parent saw on the first real report built with `format: proyecto` (pages at `/home/alejo/devwork/.projects/apps/academic-report-automation/outputs/_jarvis_research/pages/p-1.png` and `p-3.png`), all within the user's "mejora als tablas": (a) the headers of right-aligned numeric columns were hyphenated and stacked ("Precio unita-/rio/(USD)", "Subto-/tal/(USD)") because those columns are too narrow: a numeric column must be wide enough for its header on one line, or break it only at a space, never hyphenate a header word; text columns give up the width; (b) a plain line "Tabla N. <caption>" directly above a table rendered as an indented body paragraph: in proyecto it renders as a table caption (no paragraph indent, sans, "Tabla N." bold, small gap to the table) and never separates from its table; (c) the identification table printed the date as "2026-11-11": an ISO `metadata.date` prints in Spanish long form ("11 de noviembre de 2026"); any other date text prints unchanged.

## Tasks

- T1 [S1] inline (parent): remove the AA syllabus-time ficha entry; done, uncommitted in this worktree; committed with T2 and T4.
- T2 [S2-S4] delegated worker: implement `format: proyecto` with tests and docs; done (20 new tests pass; AA, format-choice, section-structure, report-config, optional-fields suites pass); uncommitted.
- T3 [S2-S7] parent: build the sample at `outputs/_proyecto_aa_preview/` with `format: proyecto` and inspect the pages; first build inspected (no sidebar, no AA labels, budget table whole); found label/value misalignment in the identification table, fixed with `\leavevmode` in `\proyectodato`; re-inspection pending after T4.
- T4 [S5-S7] delegated worker: centred title block and header, better tables, single heading style; done (33 proyecto tests pass; AA suite 71 passed; other formats render identical to HEAD); worker inspected the sample pages.
- T5 [S8] delegated worker: numeric header widths, table captions, long-form date; done (proyecto + AA suites: 109 passed after the parent fixed a missing brace in the S8a test assertion; final Jarvis PDF built with it).

## Log

L1. Original request: "tengo que armar un informe con los siguientes componentes, [Image#1] es del grupo de sistemas digitales, te paso el repo cuando ya definamis bien todo, es un proyecto con esp32 haremos un jarvis. quiero formato proyecto. primero muestrame que plantilla vas a usar" — whiteboard image lists: Tema, Integ., Rol, Alcance, Presup.
L2. After seeing the plain (Route B) sample: "no bro usa la de aa, pero para proyecto".
L3. "[Image#2] quita este apartado de la plantilla y del doc" (the "Tiempo en el sílabo" ficha entry). Parent RED observed (1 failed), GREEN 111 passed across test_aa_template, test_format_choice, test_optional_template_fields.
L4. "mientras en el repo ya estaba el presupuesto, ya comienza a documentar. y la barra lateral de la informacion manejalo de manera normal, sin barra el documento".
L5. Parent decision (user did not answer the label question, session runs without permission questions): large title "Proyecto".
L6. The main checkout is shared with other sessions; this feature lives only in its own worktree. A full-suite run takes many minutes on this machine and main has 24 known baseline failures unrelated to this work.
L7. User after seeing the first `format: proyecto` sample: "centra el tittulo y el encabezafo, mejora als tablas, un solo formato para los titulos".
L8. T4 worker evidence: RED 9 failed/23 passed, GREEN 33 passed; sample pages show centred letterhead/title/running header, aligned identification labels, tinted table header, bold Total row. Known leftovers: `doc_status` format question still lists only APE, AA, ACD or libre (pinned by tools/test_doc_status_approval.py); tables styled through `table_styles.enabled` do not get the proyecto table treatment.
L9. Slice boundary: commit 3bccf41 holds T1, T2 and T4 (966 authored lines, one cohesive new format; over the ~400-line slice). T5 goes in its own commit.
