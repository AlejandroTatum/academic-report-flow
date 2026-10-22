# Academic Report Automation

Academic report automation toolkit built with Python. It helps generate structured university-style reports, validate deliverables, manage references, and create reproducible visual assets.

> This public version is sanitized for portfolio use. It contains generic templates and sample data only.

## Why this project exists

Academic reports often require consistent formatting, metadata, figures, references, and PDF/DOCX delivery. This toolkit automates the repetitive parts while keeping the student's reasoning and final review as the most important part of the process.

## Features

- Markdown/YAML based report content.
- HTML and PDF generation helpers.
- Academic formatting templates.
- IEEE reference validation helpers.
- Report quality validation checks.
- Visual asset generation with Mermaid, Vega-Lite, ECharts and HTML screenshots
  (requires the optional Node toolchain — see [Node toolchain](#node-toolchain)).
- Sample report for local testing.
- Clean project structure prepared for public GitHub use.

## Which pipeline should I use?

There are two Markdown pipelines and they are not interchangeable.

| | Canonical pipeline | Preview pipeline |
| --- | --- | --- |
| Entry point | `tools/build_report_auto.py` | `tools/build_report.py` |
| Route | Markdown → `build_latex_report.py` → LaTeX → PDF | Markdown → HTML → WeasyPrint PDF |
| Input | a report folder with `report.yml`, `body.md`, `sources.bib` | a single Markdown file |
| Covers, bibliography, validation gates | yes | no |
| Use it for | every deliverable | a quick look at one Markdown file |

**`build_report_auto.py` is canonical for anything you intend to submit or
ship.** It is the pipeline the agent skill mandates
(`skills/academic-report-flow/references/routing.md` and `production.md`), and it is
the only one that renders BibTeX citations, institutional covers and the
validation gates.

`build_report.py` is a lightweight HTML/WeasyPrint preview of a single Markdown
file. It is useful when you want to see prose and tables in a browser without a
LaTeX toolchain. It does not read `report.yml`, does not resolve `[@citation]`
keys and does not build a bibliography; when it finds citation syntax it says
so in a warning banner instead of rendering it. The Quick Start below uses it
because it is the shortest path to a visible result, not because it is the
recommended way to produce a report.

### Markdown compatibility note: `---` means different things

The three Markdown backends read the same character sequence differently, and a
`body.md` written for one can be misread by another:

- **LaTeX branch** (`build_latex_report.py`): a line matching `^-{3,}$` becomes
  a `\newpage`, i.e. a page break, anywhere in the document.
- **DOCX branch** (`build_docx_report.py`): the same `^-{3,}$` line inserts a
  page break, matching the LaTeX branch.
- **HTML branch** (`build_report.py`): a `---` on the **first** line opens a
  YAML front-matter block, which supplies the document metadata.

`build_report.py` treats `---` as front-matter only when it opens the file *and*
the block reads as `key: value` pairs. A `---` used as a page break — or any
`---` further down the document — renders as an ordinary horizontal rule and is
never mistaken for metadata. The LaTeX and DOCX branches have no equivalent
guard, so a front-matter block written for the HTML branch will turn into page
breaks there. Keep a `body.md` bound to one backend.

## Tech Stack

- Python 3
- Markdown
- WeasyPrint
- python-docx
- BeautifulSoup
- Matplotlib / Altair / Plotly
- Mermaid CLI / Playwright / ECharts for optional visuals

## Project Structure

```txt
academic-report-flow/
├── examples/
│   ├── ejemplo_informe_academico/  # complete report folder — copy this to start
│   │   ├── report.yml
│   │   ├── body.md
│   │   └── sources.bib
│   ├── placeholder.svg
│   └── sample_report.md            # Markdown syntax snippet, not a report folder
├── templates/
│   ├── academic_format.yml        # shared academic formatting rules
│   ├── ensayo_unl.css             # stylesheet for the HTML preview branch
│   ├── ensayo_unl.md              # sample UNL essay with YAML front-matter
│   ├── unl-report.tex             # LaTeX template with the UNL cover
│   ├── plain-report.tex           # LaTeX template without institutional furniture
│   └── chamba-overleaf.tex        # Overleaf-compatible variant
├── tools/
│   ├── build_report_auto.py       # canonical entry point (report folder -> PDF)
│   ├── build_latex_report.py      # Markdown -> LaTeX -> PDF renderer
│   ├── build_report.py            # HTML/WeasyPrint preview of one Markdown file
│   ├── report_config.py           # CODE root / CONTENT root resolution
│   ├── typeset.py                 # post-approval formatting of the plain-text draft
│   ├── output_router.py           # publishes final PDFs under outputs/<subject>/
│   ├── source_library.py          # local academic source library
│   ├── validate_report.py         # deliverable validation gates
│   ├── validate_ieee_refs.py      # IEEE reference checks
│   ├── visual_builder.py          # Mermaid / Vega-Lite / ECharts / screenshots
│   ├── visual_pdf_auditor.py      # rendered-PDF visual audit
│   └── test_*.py                  # pytest suite for the tools above
├── scripts/
│   ├── sync_skills.sh
│   └── install_hooks.sh
├── skills/                        # agent skill definitions (source of truth)
├── tests/                         # skill contract tests
├── assets/generated/
├── outputs/
├── requirements.txt
├── requirements-dev.txt
└── package.json
```

A few tools in `tools/` are one-off report builders kept for reference
(`build_vm_contenedores_report.py`, `build_prompting_final_pdf.py`,
`build_mapa_conceptual_investigacion.py`, `restyle_docx_aa1.py`). They are not
part of the general pipeline.

## Quick Start

### 1. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Python dependencies

```bash
python3 -m pip install -r requirements.txt
```

### 3. Generate sample HTML

```bash
python3 tools/build_report.py examples/sample_report.md --html outputs/sample_report.html
```

### 4. Generate sample PDF

```bash
python3 tools/build_report.py examples/sample_report.md --pdf outputs/sample_report.pdf
```

Both commands use the preview pipeline. For an actual deliverable, use the
canonical one against a report folder:

```bash
python3 tools/build_report_auto.py <report-folder>/
python3 tools/validate_report.py <report-folder>/
```

### Starting a real report

`examples/ejemplo_informe_academico/` is a complete, minimal report folder:
`report.yml`, `body.md`, `sources.bib`. Copy it into
`$REPORT_CONTENT_ROOT/reports/`, rename it, and edit — the relative paths inside
are written for that location.

It satisfies every validator rule with no exemption, and
`tools/test_shipped_example.py` keeps it that way, so the pattern you copy is
the pattern the validator enforces. Two things it demonstrates on purpose:

- `route:` is declared rather than left to the academic default. The route
  decides which metadata is required; a project or business document that never
  declares one is validated as university coursework and asked for a teacher.
- The final PDF goes to `outputs/<materia>/`, never to
  `reports/<trabajo>/outputs/`.

A folder named with a leading `_` is scratch work and is not copied to
`outputs/<materia>/`. That prefix is *only* about publication — use
`publish_global:` when you want to say so explicitly.

### 5. Optional: install the Node toolchain

Only needed for `tools/visual_builder.py`. Everything above works without it.

```bash
npm install
```

See [Node toolchain](#node-toolchain) for what else it needs.

## Running the tests

The suite needs `pytest`, which is not part of the runtime dependencies:

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest tools/ tests/
```

## Agent skills

`skills/` holds the agent skill definitions and is the single source of truth
for them. The agent runtimes — `~/.claude/skills/` and
`~/.config/opencode/skills/` — are mirrors. Edit here and sync outward; a file
edited directly in a runtime directory is overwritten on the next sync.

Sync by hand:

```bash
./scripts/sync_skills.sh          # dry run — shows what would change
./scripts/sync_skills.sh --apply  # write the changes
```

The sync is gated on the skill contract tests, so a skill that fails its own
routing contract never reaches a runtime.

### Document workflow

One skill, `skills/academic-report-flow/`, owns the whole document flow: intake,
research, plan, draft, approval, verify, format, generate, validate, review, deliver.
`research-workflow` and `academic-visual-builder` stay separate.

- **Entry:** a new request first creates its work folder `reports/<slug>/`; then `doc_status` runs and its `next` token selects the one phase reference to load (an empty folder yields `intake`). The standalone full route runs only when the work-folder flow is unavailable.
- **Route:** an academic assignment (subject, teacher, APE, AA, exercise, homework) records `route: academic` without asking; the route is asked only when signals are absent or conflicting.
- **Identity:** a student name the user saved as permanent counts as confirmed; otherwise it is a single-choice suggestion, never auto-filled. A title holding commentary gets a one-line confirmation.
- **Guide:** the teacher's guide, rubric and explanation are always requested, in one compact question batch, then the run stops.
- **Three decisions:** (1) intake data, (2) draft approval plus format (APE, AA, ACD or libre; PDF or DOCX) asked in one batch, (3) final review. Intake never asks formatting questions.

Flow diagram: [`docs/diagrams/report-flow.mmd`](docs/diagrams/report-flow.mmd)
(rendered: [`report-flow.png`](docs/diagrams/report-flow.png); Spanish:
[`report-flow.es.png`](docs/diagrams/report-flow.es.png)). Older diagrams in `docs/diagrams/`
(`intake-flow*`, `new-report-flow.es.*`) are historical.

### Syncing automatically on pull

Install the versioned hooks once per clone:

```bash
./scripts/install_hooks.sh
```

This sets `core.hooksPath` to `.githooks/`, which is needed because `.git/hooks/`
is not versioned — the hooks travel with the repository, but each clone has to be
told where to look.

After that, `post-merge`, `post-rewrite` and `post-checkout` re-sync the runtimes
whenever the repository changes. All three are covered because a plain `git pull`
fires `post-merge` while `git pull --rebase` fires `post-rewrite` instead, and a
branch switch fires neither.

The hook fingerprints the tracked contents of `skills/` and exits immediately when
nothing changed, so an ordinary pull costs nothing. When a sync fails it says so
and deliberately leaves the fingerprint unwritten, so the next pull retries rather
than silently skipping a pending update. Git ignores the exit code of `post-*`
hooks, so this can never block a pull.

## Visual Builder

The toolkit includes a visual builder for reproducible diagrams and charts.

```bash
python3 tools/visual_builder.py --help
```

Supported visual workflows include:

- Mermaid diagrams
- Vega-Lite charts
- ECharts visuals
- HTML screenshots through Playwright
- Generated asset validation

### Node toolchain

The visual builder is the only part of the toolkit that needs Node. A fresh
checkout ships no `node_modules/`, so nothing under `visual_builder.py` works
until you install it:

```bash
npm install                # @mermaid-js/mermaid-cli, playwright, echarts
```

Some subcommands also need a local Chrome/Chromium binary. `visual_builder.py`
looks for one under `.cache/puppeteer/chrome/` in the code root and then in the
content root, and tells you to install it with:

```bash
npx @puppeteer/browsers install chrome@stable --path .cache/puppeteer
```

Requirements per workflow:

| Workflow | Needs |
| --- | --- |
| Vega-Lite charts | Python only (`vl-convert-python`) |
| Asset validation | Python only |
| Mermaid diagrams | `npm install` + local Chrome |
| ECharts visuals | `npm install` |
| HTML screenshots | `npm install` + local Chrome |

`echarts` and `html-shot` generate a temporary `.cjs` and run it with Node. It is
written to `.cache/visual-renders/` **inside this repository**, because Node
resolves `require(...)` by walking up from the script's own directory: a script
parked on the content tree could never reach `node_modules/` here, whatever you
installed. Both commands now check the dependency before spawning Node and say
what to install if it is missing, instead of surfacing a module-resolution stack
trace.

For a browser, `npx playwright install chromium` matches the declared
devDependency. An existing `@puppeteer/browsers` install under `.cache/puppeteer/`
is still detected and takes precedence.

### Known issue in the Node toolchain

**Two browser managers for one binary.** `@mermaid-js/mermaid-cli` bundles
Puppeteer, while `playwright` manages its own Chromium. Both are declared. When
both are installed the Puppeteer build wins for every renderer, including
`html-shot`, which then drives a Puppeteer-managed Chrome through Playwright.
That usually works, but Playwright pins its builds to its own version, so the
pairing is not guaranteed across upgrades. Picking one manager is the proper fix.

## Portfolio Notes

This project demonstrates:

- Python scripting for automation.
- File organization and output routing.
- Template-based document generation.
- Validation-oriented thinking.
- Report rendering workflows.
- Reproducible academic visuals.

## Important Principle

Automation should support understanding, structure, formatting and review. It should not replace the student's technical reasoning, source evaluation or final responsibility for the content.

## Author

Alejandro Padilla

- GitHub: [AlejandroTatum](https://github.com/AlejandroTatum)
- LinkedIn: [Alejandro Emanuel Padilla Espinoza](https://www.linkedin.com/in/alejandro-emanuel-padilla-espinoza-58003b408/)
