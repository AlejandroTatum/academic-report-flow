# Redes APE 2 · Fase 1 — Capa Física y medios de transmisión

Group report for Fundamentos de Redes (Unidad 2), teacher format "Reporte Técnico de APE" (11 sections).
Work folder: university/.reports-system/automation/reports/redes-ape-2-fase-1-capa-fisica. Team templates: ~/Documents/Universidad/Ciclo-5/fundamentos-de-redes/unidad-2/ape-2-fase-1-capa-fisica-redes/partes/.

## Specs

- S1. "tengo que hacer un trabajo excepcional" — grade against the teacher rubric (guide §8, 5 criteria, 20 % c/u, top level "Bueno 1.5 pts").
- S2. "emilio flores hara la parte de cisco packet tracer y los demas queda por repartir" — split: Emilio PT, Miguel guided media, Julian unguided media, Royel case study, Alejandro fundamentos + preguntas de control + integration.
- S3. "quiero una redaccion humana, clara sin vueltas, pero eso seria despues de que mis compañeros me pasen sus partes."
- S4. "son los mismos integrantes de la unidad pasada" — Miguel Veintimilla, Emilio Flores, Royel Jima, Julian Vega, Alejandro Padilla Espinoza.
- S5. Teacher format: /home/alejo/Downloads/ape_reporte_tecnico_.docx (sections 1-11: datos, objetivos, materiales, procedimiento, resultados, preguntas de control, conclusiones, recomendaciones, reflexión crítica, bibliografía IEEE, anexos).
- S6. "empieza por mi parte y lo que ya podamos adelantar" — Alejandro's part (fundamentos + preguntas de control) and everything not blocked on teammates.

## Tasks

- [x] T1 (S4, S5) intake: report.yml, guide text, course rubric unidad 2 — inline.
- [x] T2 (S1) rubric.yml from teacher rubric + guide (16 criteria, 4 uncovered = teammates' parts) — inline.
- [x] T3 (S1, S6) research: sources.bib 11 entries, 6 book/report — inline (web tools).
- [x] T4 (S3, S6) Alejandro's part in partes/05 + body.md with PENDIENTE markers for teammates — inline.
- [x] T5 (S2) integrate teammates' parts: reviewed, contrasted with sources, corrected (Anexo A2) — inline.
- [x] T6 verify (3 passes, 83 requirements, 49/49 checks), typeset, build v1 (21 pages, sha 5dae171d…), validation.yml VISUAL_PASS; copy ~/Downloads/APE2-F1-Capa-Fisica-v1.pdf.
- T7 deliver on explicit instruction.

## Log

- L1 (2026-11-18) User: "tengo que hacer este ape de redes, tengo que hacer un trabajo excepcional. emilio flores hara la aprte de cisco packet tracer y los demas queda por repartir, te paso el formato que pide el docente. quiero una redaccion humana, clara sin vueltas, pero eso seria despues de que mis compañeros me pasen sus partes. son los mismos integrantes de la unidad pasada"
- L2 User asked for per-member .md assignment files and a strict WhatsApp message; done (partes/01-06, mensaje-grupo.md). Practice title = whole APE 2 title.
- L3 User: "ya envie todo, ahora empieza por mi parte y lo que ya podamos adelentar".
- L4 Evidence: the guide's ISBN 978-0136764052 for Kurose & Ross belongs to Tanenbaum, Computer Networks 6th ed (verify_sources). Teacher rubric levels have 0 points; rubric_plan/course_memory warn (points must be > 0), non-blocking. doc_status next: verify, deferred until teammates' parts arrive.
- L5 User: "aca estan las partes de mis compañeros, revisa contrasta, corrige y crea el doc". Received Miguel (02), Royel (04 + reflection), Emilio (01 + 6 captures + .pkt in zip), reflections Miguel/Julian. Missing: Julian's 03 table, Emilio's reflection.
- L6 User decisions: Julian table -> "La armo yo y Julian la revisa"; Emilio reflection -> "Borrador para que la revise"; section 6 -> "Respuestas en la sección 6"; ping 75 % -> "Dejarlo y explicarlo".
- L7 Structure follows the U1 recalificación audit (12 sections, 9.1 grupal + 9.2 per student, 12. Declaración IA with model + literal prompts). Findings: Miguel cited [5],[6] absent and [4]=G.652 on coax; OM4 550 m -> 400 m (Cisco); coax 1-3 GHz and lifetimes unsourced -> CableLabs/FTTH Council. Emilio said 0 % loss but capture shows 75 %; config table wrong (PC3-PC4, console). Royel's INEC/MINTEL figures verified exact; guide video (acortar.link/AnCrEJ -> BNZdLQZIwpE) is about Copérnico, not rural Ecuador. rubric reflexion max_words 950->1150 (9.1 added). Fecha = "16 al 20 de noviembre de 2026" (guide literal; weekday rule vs access dates).
- 2026-11-18 (user): sent teammates' parts from ~/Downloads: "02-miguel-medios-guiados.md", "04-reflexion-royel-jima.md", "04-royel-caso-de-estudio.md.md", "06-reflexion-individual.md" (Miguel; "(1)" copy identical), "06-reflexion-julian-vega.md", "redes ape.zip" (01-emilio-packet-tracer.md, APE2-F1-capa-fisica.pkt, pt-01..06 PNG). Copied to reports/redes-ape-2-fase-1-capa-fisica/inputs/partes/. All filled (0 COMPLETAR). Still missing: Julian's 03 medios no guiados part, Emilio's reflection. T5 resumed with what arrived.
