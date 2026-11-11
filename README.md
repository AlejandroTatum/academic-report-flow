# Academic Report Automation

Python toolkit that turns Markdown/YAML content into structured university-style reports (PDF or DOCX), with
deliverable validation, IEEE reference checks and reproducible visual assets. The student's reasoning and final review
stay the most important part of the process: the toolkit automates the repetitive parts only.

> This public version is sanitized for portfolio use. It contains generic templates and sample data only.

## Build a report (canonical pipeline)

`tools/build_report_auto.py` is the canonical entry point for anything you intend to submit. It reads a report folder
(`report.yml`, `body.md`, `sources.bib`), routes to the LaTeX or DOCX backend, and is the only pipeline that renders
BibTeX citations, institutional covers and the validation gates.

```bash
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install -r requirements.txt

python3 tools/build_report_auto.py <report-folder>/
python3 tools/validate_report.py <report-folder>/
```

Start from `examples/ejemplo_informe_academico/`: a complete, minimal report folder that satisfies every validator
rule. Copy it into `$REPORT_CONTENT_ROOT/reports/`, rename it and edit. The final build requires a current
`approval.yml`; see [Builds](docs/portal/builds.qmd) for previews, covers and the full walkthrough, and
[Installation](docs/portal/instalacion.qmd) for LaTeX and the optional Node toolchain
(`npm install`, used by the visual builder).

## Which pipeline?

| | Canonical pipeline | Preview pipeline |
| --- | --- | --- |
| Entry point | `tools/build_report_auto.py` | `tools/build_report.py` |
| Route | Markdown → LaTeX → PDF | Markdown → HTML → WeasyPrint PDF |
| Input | report folder (`report.yml`, `body.md`, `sources.bib`) | a single Markdown file |
| Covers, bibliography, validation gates | yes | no |
| Use it for | every deliverable | a quick look at one file |

```bash
python3 tools/build_report.py examples/sample_report.md --html outputs/sample_report.html
```

The preview pipeline neither reads `report.yml` nor resolves `[@citation]` keys. Details: [Pipelines](docs/portal/pipelines.qmd).

### Markdown compatibility note: `---` means different things

- **LaTeX branch** (`build_latex_report.py`): a line matching `^-{3,}$` becomes a `\newpage`, i.e. a page break.
- **DOCX branch** (`build_docx_report.py`): the same `^-{3,}$` line inserts a page break, matching the LaTeX branch.
- **HTML branch** (`build_report.py`): a `---` on the **first** line opens a YAML front-matter block; any later `---`
  renders as a horizontal rule.

Keep a `body.md` bound to one backend.

## Project Structure

```txt
├── tools/        # pipeline, validators, gates and their tests (tools/test_*.py)
├── templates/    # LaTeX templates (UNL, APE, AA, Proyecto, ACD, plain, cover page), CSS, table styles
├── examples/     # ejemplo_informe_academico/ (report folder) and sample_report.md
├── skills/       # agent skills — source of truth for the runtimes
├── tests/        # skill contract tests (tests/skills/)
├── scripts/      # sync_skills.sh, install_hooks.sh
├── .githooks/    # versioned hooks that re-sync skills after a pull
├── openspec/     # specs of the document workflow
├── docs/         # diagrams, skill style guide and the Quarto portal pages (docs/portal/)
├── assets/ outputs/   # generated assets and published PDFs (git-ignored)
└── requirements.txt, requirements-dev.txt, package.json
```

A report folder lives under `$REPORT_CONTENT_ROOT/reports/<slug>/`, not in this checkout: code and coursework are
separate roots (see [Pipelines](docs/portal/pipelines.qmd)). Catalog of every tool by purpose:
[Tools](docs/portal/herramientas.qmd).

## Tests

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest tools/ tests/
```

Layout and notes: [Tests](docs/portal/pruebas.qmd).

## Agent skills

`skills/` holds three skills: `academic-report-flow` (the whole document flow, three human decisions),
`research-workflow` (traceable evidence packages) and `academic-visual-builder` (figures and diagrams). The runtimes
(`~/.claude/skills/`, `~/.config/opencode/skills/`, ...) are mirrors: edit here, then sync.

```bash
./scripts/sync_skills.sh --apply   # without --apply it is a dry run
./scripts/install_hooks.sh         # once per clone: re-sync automatically after a pull on main
```

More: [Skills](docs/portal/skills.qmd), [Document flow](docs/portal/flujo.qmd),
[Skill sync and hooks](docs/portal/sincronizacion-skills.qmd).

## Documentation portal

The full documentation is a [Quarto](https://quarto.org) website (Spanish) built from this repository:

```bash
quarto preview   # serve locally and reload on save
quarto render    # write the site to _site/ (git-ignored)
```

Start at `index.qmd`; how the portal is built and what it publishes: [docs/portal.md](docs/portal.md). Optional visual
builder (Mermaid, Vega-Lite, ECharts, screenshots) setup and its known issue:
[Installation](docs/portal/instalacion.qmd#cadena-de-node).

## Important principle

Automation should support understanding, structure, formatting and review. It should not replace the student's
technical reasoning, source evaluation or final responsibility for the content.

## Author

Alejandro Padilla

- GitHub: [AlejandroTatum](https://github.com/AlejandroTatum)
- LinkedIn: [Alejandro Emanuel Padilla Espinoza](https://www.linkedin.com/in/alejandro-emanuel-padilla-espinoza-58003b408/)
