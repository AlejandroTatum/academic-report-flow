# Simulación APE 6: Chi-cuadrado and Kolmogorov-Smirnov validation

Full delivery like APE 5: Python and Java code, report through academic-report-flow, push to AlejandroTatum/simulacion-unl.
Course folder: ~/Documents/Academicos/simulacion/unidad-2/ape-6-validacion-chi-cuadrado-ks/.

## Specs

- S1. Guide activity 1: generate "10 000 números" with the LCG (seed, multiplier, increment, modulus), U = X/m.
- S2. Guide algorithm 2: Chi-cuadrado with "diez subintervalos de igual amplitud", "gl=10−1=9", p-value, "Si p≥0.05, no se rechaza la hipótesis nula."
- S3. Guide KS algorithm: sort, D+ and D−, "D" as the maximum, p-value, decision, and "Representar gráficamente la distribución acumulada empírica y la distribución acumulada teórica".
- S4. Guide results: "Obtener dos implementaciones funcionales que produzcan la misma secuencia cuando utilizan los mismos parámetros. El estudiante debe armar una tabla con los datos generados por ambos programas e ir comparando, ademas debe dar sus conclusiones". N = 1 000, 10 000, 100 000, 1 000 000 with "Tiempo Python" and "Tiempo Java".
- S5. Guide objective 5: "Comparar el comportamiento estadístico de diferentes configuraciones del generador pseudoaleatorio".
- S6. User decision: replace the "π estimado / Error" columns with χ², p, D, p (slide 18 model; first noted as 17 by mistake), add a note explaining the change, no runs test ("Sí, sin rachas").
- S7. Answer the five control questions and write conclusions; AI declaration included.
- S8. Report metadata: Alejandro Padilla, Individual, 06 de noviembre de 2026.
- S10. User: "en conclusiones no van citas". User: "tambien al generar el pdf final, trabaja bien los numeros para que no parezcan amontonados" (typeset: real tables, aligned numeric columns, thin-space thousands, display equations).
- S9. User: "pero el docente si le gsta division no le gusta todo en un solo archivo". Java mirrors the Python MVC (package ape6: model, view, controller, thin Main).

## Tasks

- [x] T1 (S1-S6) Python + Java code, tests, results, figures in the course folder. Route: inline. Java reopened for S9 (MVC split).
- [x] T2 (S4, S6-S10) Report through doc_status phases up to final review. Route: inline + gentle-ai-verify. Delivered: documento/...-v001.pdf, SHA 4c35c53e, doc_status done.
- [x] T3 (S4) Course repo README rows, commit docs(ape-6) to main and push. Route: inline. Commit 24626f4 pushed to AlejandroTatum/simulacion-unl main.

## Log

- L1. User: "/home/alejo/Downloads/ape_guia\ simulacion\ semana\ 6.pdf", then chose "Todo, como en la APE 5".
- L3. Verifier found: missing generated sequence, NumPy/Pandas not mentioned, wrong N = 200 claim (χ² rejects at N = 200, p = 0.025; KS does not, p = 0.356). Fixed in body.md.
- L4. User: "pero el docente si le gsta division no le gusta todo en un solo archivo" → S9.
- L2. Intake answers: Alejandro Padilla, Individual, 06 de noviembre de 2026. Slides received; π is never estimated; slide 18 table adopted (first misread as slide 17). User: "Sí, sin rachas".
- L5. User approved the draft, the bounded edits (se deduce -> hay evidencia de que; buenos -> que pasan; U(i) note; slide 18; p < 0.001) and the final PDF ("OK, publicar y subir").
