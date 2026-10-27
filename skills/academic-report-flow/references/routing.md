# Routing - doc_status loop, work folders, document routes

Loop: `doc_status -> next -> reference -> delegate -> re-run`. The returned `next` token owns the route; never read executor internals to decide where a run stands.

## Roots and command

Three independent choices, never mixed: `REPORT_AUTOMATION_ROOT` (checkout that owns `tools/`; a feature worktree qualifies), `REPORT_PYTHON` (dependency-equipped interpreter; a worktree has `tools/` and no `.venv`, so point it at the shared one), `REPORT_CONTENT_ROOT` (holds `reports/`, `academic-sources/`, `outputs/`; never derived from the source root). Resolve it with the tools' own loader, never a personal path:

```bash
REPORT_AUTOMATION_ROOT="<absolute path of the checkout that owns tools/>"
# set REPORT_PYTHON explicitly when the checkout has no .venv (worktree, shared environment)
REPORT_PYTHON="${REPORT_PYTHON:-$REPORT_AUTOMATION_ROOT/.venv/bin/python}"
REPORT_CONTENT_ROOT="$("$REPORT_PYTHON" -c 'import sys; sys.path.insert(0, sys.argv[1]); from report_config import CONTENT_ROOT; print(CONTENT_ROOT)' "$REPORT_AUTOMATION_ROOT/tools")"
printf 'REPORT_CONTENT_ROOT=%s\n' "$REPORT_CONTENT_ROOT"
```

Every command is absolute and cwd-independent. Run first:

`"$REPORT_PYTHON" "$REPORT_AUTOMATION_ROOT/tools/doc_status.py" "$REPORT_CONTENT_ROOT/reports/<work-folder>/"`

| next | reference | executor | artifact |
|---|---|---|---|
| intake | `data.md` | academic-report-flow | `reports/<wf>/report.yml` |
| research | `content.md` | research-workflow | `reports/<wf>/sources.bib` |
| plan | `content.md` | academic-report-flow | `reports/<wf>/rubric.yml` |
| draft | `content.md` | academic-report-flow | `reports/<wf>/body.md` |
| verify | `production.md` | academic-report-flow + one independent verifier | `reports/<wf>/content-check.yml` |
| approval | `approval.md` | human gate, no executor | `reports/<wf>/approval.yml` |
| format | `approval.md` | academic-report-flow | `reports/<wf>/report.yml` |
| typeset | `production.md` | academic-report-flow | `reports/<wf>/body.typeset.md` |
| generate | `production.md` | academic-report-flow | `outputs/<materia>/<final>.pdf` |
| validate | `production.md` | academic-report-flow or `gentle-ai review` | `reports/<wf>/validation.yml` |
| review | `delivery.md` | human gate, no executor | `reports/<wf>/final-review.yml` |
| deliver | `delivery.md` | academic-report-flow | `~/Documents/<category>/[<subject-slug>/]<slug>/<slug>-vNNN.pdf` |

Each phase produces one artifact. Research is mandatory (at least 5 book or paper sources, or the report's `min_sources:`; `0` only off the academic route; `business` defaults to 0; `uncited_bibliography: true`, academic only and exclusive with `min_sources`, lists the whole bib with no citations).

## Work folders

A new request creates the work folder `$REPORT_CONTENT_ROOT/reports/<slug>/` first, so `doc_status` sees an empty folder (`next: intake`). The slug is lowercase ASCII kebab-case from the request's subject and assignment (e.g. `metodos-numericos-ejercicio-1-5`); append a numeric suffix if that folder belongs to a different document. Never ask the user for the slug.

- Same document: the folder's `report.yml` names the same assignment (same `metadata.title`, or the same exercise or guide). In progress: resume, never recreate.
- Delivered: delivered means a current final-review.yml plus a published version. When the same document is already delivered, ask one single-choice question: start a new version in a suffixed folder, or resume the delivered one; never overwrite a delivered folder.
- A folder that exists without a report.yml is an unfinished intake of that document: `doc_status` returns `next: intake`.
- The standalone full route (`data.md`) applies only when the work-folder flow is unavailable (no content root, or the user asks for a one-off document outside the reports flow).
- Backend (`type:`): `latex` for long textual or mixed documents, a visual backend for maps and infographics, `docx` only for editable delivery or a mandatory DOCX template.
- Default build file: `<work-folder-slug>.pdf/.docx` under `outputs/<materia>/` or `outputs/<route category>/` (legacy `<title-slug>` builds are kept); `pdf:`/`docx:` in `report.yml` win.

## Status block

Present the human block verbatim (ASCII only, flat bullets, no tables, no nested headers). The `**Gate**` line names the phase the route is waiting on and appears only while a phase is not `done`; the tool binds `<report-folder>` to the absolute work folder:

```text
**Gate**: plan pending - record the teacher's rubric in <report-folder>/rubric.yml, then re-run doc_status
Route: intake > research > [plan] > draft > verify > approval > format > typeset > generate > validate > review > deliver

**Summary**
- intake: done - route=academic, title and student recorded
- research: done - sources.bib has 5/5 book or paper sources
- plan: current - rubric.yml missing
- draft: pending
- verify: pending
- approval: pending
- format: pending
- typeset: pending
- generate: pending
- validate: pending
- review: pending
- deliver: pending

**Next**: plan - record the teacher's rubric in <report-folder>/rubric.yml, then re-run doc_status
```

## Document routes

The user chooses one route (`data.md`); load only its references; never blend routes or fall back silently. Declare it as `route:` in `report.yml` (an absent key means Route A, for legacy reports only; an unrecognised value stops the run). The section lists below are structural defaults, not independent content requirements: the guide, rubric and explicit user instructions govern scope. Do not invent content to fill a default; resolve incompatible fixed-format requirements with the user.

### Route A - University academic work (`route: academic` or `a`)

The only route that may activate institutional machinery (UNL shell, teacher, subject, parallel, academic period, institutional cover, rubric alignment, IEEE bibliography by default, teacher profile; `citation_style: apa` is allowed on any route). Required metadata: `title`, `subject`, `teacher`, `student`, `date`. Sections: cover, metadata table, `Tema`, `Antecedentes`, `Desarrollo`/`Descripción`, comparative tables or maps, `Conclusiones`, `Bibliografía`. Forbidden: management framing, commercial recommendations, sales language, changelog. `unl-shell.md` and `profiles/` load only here, whatever the output format.

| Route | `route:` | Sections in order | Forbidden |
|---|---|---|---|
| B Project documentation | `project` / `b` | name and version, objective, audience, scope, modules, requirements, flows, architecture, decisions, risks, traceability, pending | UNL cover, teacher, subject, motto, academic footer or numbering, "university submission" language |
| C Professional/business | `business` / `c` | executive summary, problem, evidence, analysis, impact, options, recommendation, risks, next steps (decidable from page 1) | academic cover and metadata table, rubric alignment, required bibliography (IEEE default, `citation_style: apa` opt-in); implementation-level technical appendices in the main flow (technical depth moves to annexes) |
| D Technical document | `technical` / `d` | purpose, scope, concepts, architecture, contracts, procedures, examples, errors, observability, verification, references | academic cover, rubric language, executive persuasion, marketing copy |
| E Other | `other` / `e` | built with the user before generating: sections, forbidden content, format sources, reading priorities | never fall silently back to academic or any other route; an incomplete contract stops the run; reuse fragments of other routes only when the user confirms each |

B to E require metadata `title`, `student`, `date`; `subject`/`teacher` there warn. Business omits the author/date line unless `metadata.show_author: true`; put signature blocks in one table (Por X | Por Y) so they never split.

Rendering defaults derive from the route at build time and an explicit `template:`, `cover:` or `section_numbering:` always wins: academic = `unl` template, cover on page 1 with logo, body from page 2, numbered headings; other routes = `plain` template, no institutional cover, unnumbered headings (B, C, D forbid numbering).
