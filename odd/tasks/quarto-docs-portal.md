# Quarto docs portal, README and skill improvement backlog

Feature branch: `feat/quarto-docs-portal`. Builds a Quarto website portal following the
convention of the user's other repos (gymkad, sistema-practicas-preprofesionales-unl,
aso-computacion-admin), rewrites the README, and proposes skill improvements (proposal only).

## Specs

- S1: "quiero que hagas la docuemntacion del proeycto en quarto como los demas repos" — a Quarto
  `website` portal with the shared skeleton of the reference repos: `_quarto.yml` with a whitelist
  `render:`, `output-dir: _site`, `lang: es`, `execute.enabled: false`, theme `cosmo` with `toc`,
  `code-copy`, `lightbox`, docked sidebar with sidebar search, the `mermaid-fence` extension,
  `index.qmd` with a "Por dónde empezar" table, `docs/portal.md` describing the portal, sidebar
  sections in the shared order (Contexto, Especificación, Modelado, Arquitectura, Calidad,
  Operación, Equipo — sections without content are omitted). Portal prose in Spanish (the
  reference portals use `lang: es`). `quarto render` must succeed with Quarto 1.11.9 locally.
  Real course data (`skills/**/profiles/`, `outputs/`, `openspec/changes/archive/**`) is not published.
- S2: "mejores readme" — a shorter README (~100-150 lines) leading with the canonical pipeline
  (`build_report_auto.py`), a "Which pipeline" table, a structure map, tests, skills sync
  one-liner, a link to the portal for deep docs; internals (the `---` compatibility note, hook
  details, Node toolchain, portfolio notes) move to portal pages. README stays in English.
- S3: "podemos ir planteando mejoras en la skill. aunque por ahora me va regular" — a proposal
  document (no skill edits) published in the portal under Equipo. User priorities (L2):
  "en cuanto a la rubrica, me gustaria que este mas presente en cada punto y sobre todo al final,
  califique sobre eso." plus "Muy lenta / demasiadas fases", "Calidad del texto",
  "No sigue la rúbrica/guía". Each proposal names the problem with `path:line` evidence from the
  skill and tools, the proposed change, and its cost.

## Tasks

- T1 (S1): `_quarto.yml`, `_extensions/mermaid-fence`, `index.qmd`, `docs/portal.md`, portal pages, `.gitignore` — worker A
- T2 (S2): README rewrite — worker A (links to T1 pages)
- T3 (S3): `docs/portal/mejoras-skill.qmd` skill improvement proposal — worker B
- T4 (S1-S3): render the site, verify, commit work units — parent

## Log

- L1: "quiero que hagas la docuemntacion del proeycto en quarto como los demas repos, mejores readme, y podemos ir planteando mejoras en la skill. aunque por ahora me va regular"
- L2: User answer on skill pain points: selected "Muy lenta / demasiadas fases", "Calidad del texto", "No sigue la rúbrica/guía"; custom: "en cuanto a la rubrica, me gustaria que este mas presente en cada punto y sobre todo al final, califique sobre eso."
- L4: "tambien otro problema es que el borrador lo da en formato AA, para mayor eficiencia, un formato simple sin logos sin plantilla. que abra un pdf temporar con el contenido" — added as proposal (e) in docs/portal/mejoras-skill.qmd (S3 scope: proposal only).
- L5: README doc-contract tests (tools/test_readme_compatibility_note.py, tools/test_build_report_html.py) require the `---` compatibility note, a `## Project Structure` txt block and `npm install` in README; the note was kept in README (short) instead of moved.
- L3: Decision: no CI workflow or GitHub Pages deploy in this feature (repo has no CI; delivery/env change left as a proposed next step). Quarto 1.11.9 installed locally.
