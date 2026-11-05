# Data - Decision 1 (intake)

`doc_status` returns `next: intake`. This skill runs it and writes one artifact, `reports/<wf>/report.yml`. Run the intake on every execution, even when the prompt appears to already contain the answers: a prompt statement, prior document, template, or memory is a proposal, never a confirmation.

## Content-first intake

Default for every new request (work folder rules: `routing.md`; state the folder in the intake summary). Ask only the content-first minimum: route, title, student, the teacher's guide and rubric material, teacher explanation. One compact question batch, then stop.

- Route: an academic assignment signal (subject or course, teacher, APE, AA, exercise/ejercicio, homework/tarea, practice/práctica, guide or rubric) records `route: academic` without asking and is stated in the intake summary. Ask the route only when signals are absent or conflicting. Only this mode derives it; the full route never infers the type.
- Identity: `metadata.title` and `metadata.student` are what intake is done on. A student identity saved as permanent (memory or preference such as "use this name for all future sessions") is confirmed: records it without asking. Otherwise suggest Alejandro Padilla through `ask_user_choice` as a single-choice confirmation; never auto-fill, never invent a name.
- Free-text sanity: a title (or any free-text identity) holding commentary, a question or a complaint is not accepted; show the cleaned candidate and ask for a one-line confirmation.
- Guide: intake always requests the teacher's guide, rubric and teacher explanation when not already supplied, in the same single compact question batch; never a second round unless an answer is unusable. Record the folder-relative `guide:` path, run `tools/guide_facts.py <folder>` and record `format_hint: ape` or `format_hint: aa` when it detects a family (planning only, never `format:`). It reports only explicit facts, lists clashing values under `conflicts:` (a conflicted family yields no `format_hint`) and never guesses; ask any unresolved fact through `ask_user_choice`. `tools/guide_facts.py <folder> --inventory` is the separate, heuristic list of the guide's demands (`G1`...; plan phase, `content.md`); it is not a fact and never writes `report.yml`.
- Course profile: once `metadata.subject` is recorded, run `tools/course_profile.py <folder>` (`--check` writes nothing) and report what it applied. A profile in `references/profiles/` with front-matter `match:` supplies `report.yml` defaults and the delivery folder; values already in `report.yml` win and the user may override any of them. Without a profile template (no profile, or a matching profile that only sets `report_defaults`), a course repo `~/Documents/Academicos/<subject-slug>/AGENTS.md` supplies the delivery folder `unidad-{unit}/{practice_type}-{practice_number}-{topic}/documento/` once the format batch records those fields (`approval.md`). The practice type is the word the course's existing practice folders use (`ejercicio`, `ape`, `aa`), the document format when the course has none or already uses it; an existing folder for the same unit, type and number is reused whatever its topic.
- Record without asking when the material names them: `metadata.date`, `metadata.audience`, `metadata.purpose`, `metadata.visual_direction`, top-level `template:`, `cover:`, `output:`, `metadata.subject`, `metadata.teacher`. When the requirement names the `.bib` as a submitted artifact, record `deliver_bibliography: true` (plus `bibliography:` when not `sources.bib`); intake never asks for it and never adds an approval gate for it.
- No additional permanent intake questions without the user's explicit approval; ad-hoc clarifications stay ad-hoc.
- Never ask formatting questions at intake (template, identity tables, cover, visual direction, document format APE, AA, ACD or libre, delivery format PDF or DOCX): intake never asks the delivery format; the format phase owns every formatting decision (`approval.md`), including group work (`metadata.practice_type: Grupal`, `metadata.members`).
- Full-route confirmations 1 to 5 below do not apply in content-first: audience and purpose (derived and recorded, never asked), template and identity, delivery format, visual direction.

## Express flow (quick daily documents)

For a quick project, business, technical or one-page document the user wants without intermediate stops, record `flow: express` (routes B-E only; `doc_status` blocks it on `route: academic`). Offer it through `ask_user_choice` when the request is a non-academic document and does not say which flow; never infer it.

- Intake asks only what the request lacks to identify the document (route, title, author); no guide, rubric or teacher batch.
- Record the format defaults yourself, never ask them: `format: libre`, `format_spec: "documento sobrio sin portada"`, `output: pdf`, plus `min_sources: 0` unless the user supplies or requests sources.
- Plan: write `rubric.yml` from the route's section list (`routing.md`) and the user's request; the independent verifier still runs.
- Approval: run `approval_marker.py approve <folder> --express` (never `--by`); no draft PDF, no approval packet, no question. The tools refuse it outside `flow: express`.
- The only human gate is the final review of the built PDF (`final-review.yml`); a request for changes there edits `body.md`, re-runs `--express` and rebuilds.

## report.yml record

Keys the pipeline reads; never add `report.yml` keys beyond this record, and never invent a parallel key for a meaning that already has one (no top-level `audience:`, `document_type:` or `visual_direction:`):

```yaml
type: report                  # backend: essay | report | technical_report | visual | docx ...
route: project                # academic | project | business | technical | other
# flow: express               # routes B-E only: one human gate, the final review (see Express flow)
output: pdf                   # pdf | docx
template: plain               # only when confirmed; omit otherwise

metadata:
  title: "Manual de despliegue"
  student: "Nombre y apellido"         # author/nombre accepted; group: members: [...] (complete roster)
  date: "2026-09-10"
  audience: "Equipo tecnico"
  purpose: "Implementar el despliegue"
  visual_direction: "Technical"

cover:                        # top-level, optional; explicit values win over the route default
  required: true
  logo_required: true
  body_starts_on_page: 2

deliver_bibliography: true    # only when the course requires the .bib as a submitted artifact
bibliography: sources.bib
min_sources: 1                # only when a requirement limits sources; positive integer, default 5
# citation_style: apa        # default ieee; apa only when the course guide demands it; any route, PDF only
# uncited_bibliography: true  # instead of min_sources: academic only; prints every bib entry, no citations needed
# ape_omit_sections: ["Preguntas de Control"]  # format ape only; a fixed APE section the teacher said to leave out
```

- `pdf:`/`docx:` are optional top-level overrides; unset, the build path is derived under the content root's outputs tree (`routing.md`).
- `route:`, `output:`, `cover:` are top-level (a nested `metadata.cover` is read nowhere). Only Route A carries `metadata.subject` and `metadata.teacher`.
- Intake is done when `route:` is known and `metadata.title` and `metadata.student` are real (no bracket templates). Intake writes only `report.yml`.

## Full-route confirmations

Standalone run, only when the work-folder flow is unavailable. Ask, then stop. The Document Contract below is a data record written to `report.yml`; it does not authorize generation, and intake never asks for approval. Generation starts only after the one human approval in `references/approval.md`.

1. Document type: University academic work, Project documentation, Professional/business report, Technical document, Other. May recommend one with a one-line reason; must never auto-select or continue on silence. There is no default type.
2. Audience and purpose, two independent fields: who reads it, and what the reader must do after. A mismatch stops the run.
3. Template and identity (template, institutional format, logo, palette, typography, reference document, client requirements): a template applies only when confirmed; otherwise record `Template/identity: none`.
4. Delivery format: PDF, DOCX, or both; never inferred, and a format request never implies a type, route or shell.
5. Visual direction: Sober, Institutional, Technical, Executive or Custom (operational definitions: `visual-directions.md`); it must materially change the rendering.

Identity confirmation: individual report = full name; group report = complete membership list, every member's full name. Placeholders and blanks are rejected. The skill never prompts for Paralelo (academic route renders A unless an explicit value says otherwise).

Structure confirmation: ask whether the teacher/client supplied a mandatory structure. Combine requirements from every supplied source; a contradiction between sources blocks confirmation until the user resolves it. Record each required section's exact title, order and at least one criterion; quantitative limits stay entirely optional per section and are never inferred. With no supplied structure, propose one and require explicit confirmation; never a provisional structure. The confirmed `structure:` (`tools/structure_contract.py`) downstream phases stay blocked while it is unconfirmed; a changed source requires reconfirmation.

Question scope: length, depth or page count must not be a mandatory question; ask compactly, one targeted clarification per missing route-mandatory field; adaptivity never adds, removes or relocates the single approval gate.

Render the record before writing it:

```
Document Contract

Type: Project documentation
Audience: Technical team and project reviewers
Purpose: Define implementation scope and expected behavior
Template/identity: KIPU visual identity; no UNL shell
Outputs: PDF and DOCX
Visual direction: Technical
```
