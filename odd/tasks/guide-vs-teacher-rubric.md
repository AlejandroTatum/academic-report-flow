Separate the guide's requirement checklist from the teacher's grading rubric in academic-report-flow.
Root cause of low Redes U1 grades: one rubric.yml served both, graded by presence, never by the teacher's levels.
Every new check is advisory: the skill warns, it never blocks (S2).

## Specs

- S1 "tambien de la skill por no separar la rubrica de criterios de la guia, y la rubrica de califiacion" — rubric.yml distinguishes guide criteria from teacher criteria: each criterion may carry `origin: guide|teacher`; teacher criteria may carry `levels` (points + descriptor) and their real `weight`.
- S2 "no quiero que nunca bloquee la skill, por nada, solo avisar" — nothing added by this feature blocks a phase, a build or a delivery. Missing teacher rubric, low level scores and guide-vs-rubric conflicts are warnings only.
- S3 A rubric.yml with no teacher criterion is reported as guide-only ("no teacher rubric") by doc_status, unless the file records that the user confirmed there is none (`teacher_rubric: none`). Warning only (S2).
- S4 Existing rubric.yml files (no `origin`, no `levels`) stay valid and keep their current behaviour; they are reported as guide-only.
- S5 Per-course memory: the teacher rubric is stored once per course and reused in every APE of that course; a per-course feedback log holds the teacher's grade and comments per delivery and the next report's plan reads it; the AI declaration is an explicit per-course decision (Redes: included by default).
- S6 Plan for the top level: each teacher criterion's highest-level descriptor becomes report requirements even when the guide does not ask for them as a step; guide-vs-rubric conflicts are listed for the user before drafting.
- S7 rubric_grade reports "guide coverage" and "leveled grade" separately and stops presenting coverage as a grade (the APE 5 self-grade was 21/21 while a strict grader gave 15/20). An independent strict grader (1-4 per teacher criterion, descriptor quoted, what is missing for the top level) is a fixed step. A criterion at 2 or less, or at 3, produces a warning only (S2).
- S8 Calibration case from the real Redes U1 grades (teacher /10: Fase 1 6.0, Fase 2 9.0 with comment "declaración de IA??", APE 3 6.0, APE 4 5.0, APE 5 8.5; strict grader gave 7.0, 7.5, 7.5, 6.0, 7.5). Orientative only.

## Tasks

- [ ] T1 S1,S3,S4,S2 schema (`origin`, `levels`, `teacher_rubric`) + doc_status guide-only warning + skill text (content.md, data.md) — inline — commit:
- [ ] T2 S5,S2 per-course rubric, feedback log, AI declaration decision — inline — commit:
- [ ] T3 S6,S2 plan for the top level + guide-vs-rubric conflict list — inline — commit:
- [ ] T4 S7,S8,S2 rubric_grade split, independent leveled grader step, warnings, calibration case — inline — commit:

## Log

- L1 (2026-11-12) "como mejoramos la skill, he tenido el problema de notas con el docente porque se estan haciendo los informes segun la guia, pero ninguno cumplio completamente con la rubrica, se que en parte es culpa del docente por las guias confusas, pero tambien de la skill por no separar la rubrica de criterios de la guia, y la rubrica de califiacion, califica con obejtividad los 5 apes de redes. partamos por ahi"
- L2 (2026-11-12) Independent strict grading against the teacher rubric (on body.md): APE1 14/20, APE2 15/20, APE3 15/20, APE4 12/20, APE5 integrado 15/20. Skill gap map: rubric_plan.py:202-255 (no origin, no levels), content.md:14-18 (silent fallback to guide demands), doc_status.py:299-315 (plan done for any valid file), rubric_grade.py:40-44 (presence coverage), rubric_trace.py:46-49 (equal weights by default), `docente-*` ids are an ad-hoc convention.
- L3 (2026-11-12) "[Image#1] ahora compara con mis notas, en alguna guia pide declaracion de IA?, no?, entoinces esta bien grave la situacion. haber pero primero comentame cuales sonals fallas de las guias, fallas de la rubrica y finalmente cuales son fallas de la skill" → teacher grades in S8. No guide text nor the rubric mentions an AI declaration; only fase-5 and the integrated report carry one.
- L4 (2026-11-12) "como quedaria el plan completo?" → 8 changes in 4 slices presented.
- L5 (2026-11-12) "no quiero que nunca bloquee la skill, por nada, solo avisar. y ya comienza con el plan" → S2; the proposed delivery gate is dropped. Parent interpretation: applies to everything this feature adds; already-existing gates are left as they are (not decided by the user).
