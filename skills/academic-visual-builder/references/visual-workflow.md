# Visual workflow details

## Canonical roots and placement

```bash
REPORT_AUTOMATION_ROOT="/home/alejo/devwork/apps/academic-report-automation"
REPORT_CONTENT_ROOT="/home/alejo/devwork/.projects/university/.reports-system/automation"
```

Run commands from `REPORT_AUTOMATION_ROOT`. Final report PDFs belong in
`outputs/<materia-slug>/`; visual assets are intermediate files in
`assets/generated/<materia>/<tarea>/`. Visual assets, specs, manifests, and
audits are working evidence and are never copied to the user's Documents
delivery folder — only the assembled final PDF/DOCX from
`academic-report-flow` is delivered there (see that skill's
`references/delivery.md`).

## Asset classes

Generated figures (Mermaid, Vega-Lite, ECharts, Matplotlib, or HTML/Playwright)
keep editable specs in `visuals/specs/<materia>/<tarea>/` and rendered assets in
`assets/generated/<materia>/<tarea>/`. Prefer SVG; add PNG only when DOCX or
LibreOffice requires raster output.

Photographic or handwritten evidence is not regenerated: preserve aspect ratio,
do not crop without explicit approval, never enlarge, and scale only when the
source exceeds 1200px wide. Give each photo a descriptive caption and use
`source` text that identifies the own photograph/scan and its context. Set
`renderer: photo`. Inspect clipping, legibility, and blank space at normal PDF
zoom before insertion; replace or split unreadable evidence.

## Renderer gates

| Need | Renderer |
|---|---|
| Concept map or process map | `tools/bauhaus_maps.py` from a YAML spec (`bauhaus-maps.md`) |
| Other flow or tree | Mermaid |
| Academic chart or comparison | Vega-Lite / Altair / vl-convert |
| Dashboard-like visual | ECharts SVG SSR |
| Custom card or infographic | HTML + Playwright screenshot |
| Simple curve | Vega-Lite, unless custom mathematics requires Matplotlib |

Unsupported dependencies fail explicitly. Do not substitute a renderer silently.
Reject raw Mermaid when labels are tiny, hierarchy is unclear, arrows are
awkward, or styling is weak; use custom CSS or HTML/Playwright instead.

## Mermaid layout limits and raster scale

- ER diagrams: Mermaid parses `direction` on an `erDiagram` but does not lay out
  entities by it — entity placement is decided by the layout engine, so do not
  promise direction control for ER diagrams.
- Supported practical workaround, with capabilities this workflow already has:
  restructure the spec instead of negotiating with the layout engine — reduce
  entities per diagram, split one large ER model into focused sub-diagrams (for
  example per bounded context or aggregate), keep relationship labels short — or
  render the model as a custom HTML/Playwright figure (see the renderer gates
  above). If the hierarchy stays unclear after restructuring, reject raw Mermaid
  as above rather than inserting an unreadable diagram.
- Raster scale: `mermaid --scale <N>` passes `-s <N>` to mmdc for PNG output.
  Omitting `--scale` preserves mmdc's native default; nonpositive or nonfinite
  values are rejected explicitly instead of falling back.
- Readability: a larger `--scale` increases pixel density only. It does not prove
  the figure is readable at final print size — density is not legibility.
  Connector readability (obstruction, crossings, clearance, direction) is
  enforced automatically instead of eyeballed: `tools/visual_builder.py
  validate <asset.svg>` runs `connector_geometry`'s isolated precheck
  (unrelated connectors and connectors-to-nodes/text/annotations/cluster
  labels/legends must clear 0.80 SVG units; obstruction and unnecessary
  crossings always fail), and `validate_report.py`'s LaTeX visual validator
  independently re-audits every diagram SVG at its real final print scale
  through `connector_pdf_stage` (the 0.80-SVG-unit rule's final-scale
  equivalent, derived from the template's own page geometry), flagging the
  report there too as a warning (never blocking). A figure reference that cannot be resolved, or has no
  matching SVG next to it, is reported as a warning naming the figure — never
  silently skipped, so the gate cannot pass having audited nothing. The
  isolated run is precheck evidence only; the final-size run is the
  mandatory, independent enforcement — neither substitutes for the other, and
  passing both is still not `VISUAL_PASS` (see the report skill's
  `references/production.md`). Non-connector legibility (label
  wrapping, page geometry, overall composition) still needs inspection in the
  assembled PDF at normal zoom before insertion, per the photo/evidence rule
  above.
- Direction and end-marker checks (#43, 2026-09-23 decision, supersedes the
  earlier "every connector MUST use a defined end marker" rule): the `.mmd`
  source is the sole authority on connector intent. The gate looks for it in
  order — the sibling `.mmd` next to the SVG (same stem), then, since the
  canonical layout above keeps specs and renders in parallel trees rather
  than as siblings, the mirrored path under `visuals/specs/` obtained by
  swapping the `assets/generated/` segment pair for `visuals/specs/` (same
  relative subpath and stem). An undirected link (`---`, `-.-`, `===`, with
  or without a label) declared there skips direction/marker checks; a link
  declared with an arrowhead (`-->`, `-.->`, `==>`, `<-->`, `--o`, `--x`,
  ...) keeps the full check. When neither location has a matching `.mmd`,
  the check falls back to the strict pre-#43 rule and reports that it did
  (an informational finding naming the figure, never silently different
  behavior).
- Necessary-crossing exemption (#43, conservative): a crossing between two
  connectors is exempt only when an obstacle-aware visibility check, within
  the diagram's own viewBox, proves every route for one of the two
  connectors must cross the other (no way around the diagram's nodes and
  protected regions). When that proof is inconclusive — a route around does
  exist, or the obstacle count exceeds the bounded state budget — the
  crossing keeps failing, exactly as before #43.

## Subject presets

Use these only as topic suggestions, not automatic style selection: Sistemas
Operativos (VMs, containers, process flows, memory, scheduling, security),
Diseño de Software (use cases, domain/component models, requirements, journeys),
Complejidad Computacional (automata, graphs, recursion, Big-O, Turing machines),
Investigación (article matrices, methodology, evidence maps), and Ecuaciones
Diferenciales (curves, slope fields, sensitivity, model comparisons). Every
subject uses the editorial technical style (`editorial-style.md`) except concept
and process maps, which use the Bauhaus técnico style (`bauhaus-maps.md`).

## Commands

Run from the canonical automation root, after setting the content root described
by the skill. Use the local environment and preserve specs/manifests:

```bash
./.venv/bin/python tools/bauhaus_maps.py render <spec.yml> --out <asset.svg> [--png <asset.png>]
./.venv/bin/python tools/visual_builder.py mermaid <spec.mmd> --out <asset.svg>
# PNG at higher density: add --scale <N> (omit it for mmdc's native default)
./.venv/bin/python tools/visual_builder.py vegalite <spec.vl.json> --out <asset.svg>
./.venv/bin/python tools/visual_builder.py echarts <spec.echarts.json> --out <asset.svg>
./.venv/bin/python tools/visual_builder.py html-shot <spec.html> --out <asset.png>
./.venv/bin/python tools/visual_builder.py validate assets/generated/<materia>/<tarea>
```
