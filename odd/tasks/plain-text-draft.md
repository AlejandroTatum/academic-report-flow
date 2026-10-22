# Plain-text draft, typeset after approval (issue #96)

The draft the user reviews and approves is plain text; backend formatting moves to a new `typeset` phase after approval, so a formatting fix never invalidates verified or approved content.
Branch: fix/plain-text-draft-96. Risk: item 3 (changes the draft body check, the doc_status phase list and the build input that existing reports consume).

## Specs

- S1. User rule, verbatim: "cuando hacemos un borrador no quiero ningún formato, quiero texto plano solo para el body; luego de eso sí le damos el formato correspondiente, siempre tengo ese problema".
- S2. Draft markers, user choice verbatim: "Títulos # y citas [@clave] (recomendado)" — "Las secciones se marcan con «# Título» y las citas con [@clave]. Son separadores, no formato: el verificador las necesita para mapear criterios a secciones y comprobar fuentes. Todo lo demás es texto plano." The draft body check (`content_check --body-check`, the doc_status draft gate and the verify run) rejects backend formatting outside fenced or inline code, naming the line: inline or display math (`$...$`), LaTeX commands (`\word`), Markdown pipe tables, image syntax (`![...](...)`), bold (`**...**`) and HTML comments/directives (`<!--`). Fenced code stays allowed (a listing is content). Unicode sub/superscripts are allowed in the draft. The draft no longer checks the format's fixed headings (`aa_structure`, `ape_structure`, `acd_structure`).
- S3. A figure in the draft is a plain line `Figura: <caption> (<relative/path.png>)`; a link is a bare `https://...` URL. The rubric checks `figure_referenced` and `link_present` accept these plain forms as well as the formatted ones.
- S4. Typeset phase, between `format` and `generate`. After approval, `tools/typeset.py bind <folder>` creates `body.typeset.md` as a copy of `body.md` when it is missing, and writes `typeset.yml` binding it to the current `body.md` sha256; it refuses while approval is not current or carried. The agent applies the backend formatting (math, tables, figures, fixed format headings) only in `body.typeset.md`, never in `body.md`. `typeset.py check <folder>` (and the doc_status phase) passes only when the binding matches the current `body.md`, the typeset body passes the existing format check (level-1 headings, no Unicode sub/superscripts, no bold pseudo-headings), the format's fixed headings when the format has them, and cites exactly the same `[@key]` set as `body.md`.
- S5. The build and its validators render `body.typeset.md` when its binding is current; otherwise `body.md`. A final build (without `--no-approval-check`) refuses while a required typeset is not current. A final PDF older than `body.typeset.md` is stale (generate pending).
- S6. Legacy: an `approval.yml` recorded before this change carries no `typeset: required` field; its report needs no typeset (`typeset` done, `body.md` renders as before). New approvals write `typeset: required`.
- S7. A preview build (`--no-approval-check`) of the plain draft reports validation failures as preview findings and exits 0: formatting is fixed in typeset after approval, never in `body.md`. The approval guidance no longer asks to fix layout defects in `body.md` before approval.
- S8. Skill references (content.md, approval.md, production.md, routing.md, SKILL.md) document the plain draft, the typeset phase and its tool.

## Tasks

- T1 (S2, S3). Plain-text draft check and plain rubric forms, tests, content.md. Route: inline. Commit: 32c0e0e.
- T2 (S4, S5, S6). typeset.py, typeset phase, body resolution, build gate, approval field, tests, docs. Route: inline (old-contract test updates: worker). Commit: 48e1b03.
- T3 (S7, S8). Preview findings, approval guidance, remaining docs. Route: worker. Commit: 48e1b03.
- T4 (S1-S8). Independent verification: PASS S1-S8. Route: gentle-ai-verify. Follow-up fixes (LaTeX-delimited math, bare-URL punctuation): see L6.

## Log

- L1 (user, verbatim): "abri un issue para el tema de los borradores"
- L2 (user, verbatim): "si soluciona, y reivsa que no existan mas issues"
- L3 (user choice, verbatim): "Títulos # y citas [@clave] (recomendado)"
- L4 (evidence): `gh issue list --state open` shows only #96 open.
- L5 (evidence): full suite 2696 passed (tools/ + tests/, template tests via Docker) on 48e1b03. Slice note: 32c0e0e + 48e1b03 total ~1020 changed lines; 32c0e0e alone leaves contract tests red until 48e1b03.
- L6 (evidence): verifier PASS S1-S8, no legacy regressions. Fixed its findings on \\( \\[ math and bare-URL trailing punctuation; suite 2510 passed (template tests excluded). Left open: currency `$5 y $10` and Windows paths flagged; binding does not prove the post-approval edit reached body.typeset.md (only citations_match ties content); a manual bind on a legacy report renders an unchecked typeset body.
