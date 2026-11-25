# Simulación expo: Métodos para generar variables aleatorias (Von Neumann)

Group talk (3 speakers, 20 min) for Simulación (UNL, cycle 5, unit 2), tomorrow 2026-11-23. Source draft: `/home/alejo/Downloads/Guia_Detallada_3_Expositores_Von_Neumann.pdf` (16 pages; text dump `/tmp/vn.txt`).
Deliverables: animated HTML deck + static PDF deck (skill `academic-slides-flow`, mode `deck`, theme `metro-deck`) and an A4 speaker guide. Destination: `~/Documents/Academicos/simulacion/unidad-2/exposicion-variables-aleatorias-von-neumann/` (precedent: `unidad-1/exposicion-semana-2-tipos-de-simulacion/`).

## Specs

- **S1** User request: "es un borrador, pero se me hace muy extenso y complicado de entender, ordena las ideas y planteame la estrucura, lo qur quiero es al final generar la diapos y el guion, somo 3 expositores"
- **S2** Duration: "osea unos 20 mins pero de contenido de calidad". Formats: "pdf y html". Script: "una mezcla de los 2" (key points per slide plus verbatim opening/transition phrases). Case h(x) unnormalized: "No, solo en el guion".
- **S3** Title correction: "veras que el titulo no es que planteaste es algo de variables aleatorias, revisa bien el guion que te pase". Draft title: "Métodos para generar variables aleatorias" with subtitle "Aceptación-Rechazo de Von Neumann".
- **S4** Live demo: "en tema practica quieisera que por detras corra el codigo de phyton y se vayan mostrando la data para exponer igual". Chosen: "Dentro de la diapo HTML (recomendado)": the slide shows the Python code and runs the same logic in the browser, offline, animating accepted/rejected points, live counters (aceptados, rechazados, intentos, eficiencia), a histogram converging to Beta(2,2) with mean→0.5 and variance→0.05, and a control to switch M (1.5, 2, 3, 6) showing efficiency → 1/M. The PDF shows static captures from a real Python run.
- **S5** Approved outline (17 slides, speaker, start time, message | visual):
  1. E1 0:00 Portada "Métodos para generar variables aleatorias: Aceptación-Rechazo de Von Neumann" + objetivo
  2. E1 0:30 "Simular es incorporar incertidumbre con la frecuencia correcta" | restaurante 4, 6, 11, 17 min
  3. E1 1:30 "Una variable aleatoria puede ser discreta o continua" | Σp(k)=1 vs ∫f(x)dx=1; P(X=a)=0
  4. E1 2:40 "Uniforme vs no uniforme: la altura dice dónde caen más valores" | U(0,1) vs Beta(2,2); f(0.5)=1.5>1 es válido
  5. E1 3:50 "Primer método: transformada inversa X=F⁻¹(U)" | exponencial X=−ln(1−U)/λ paso a paso
  6. E1 5:00 "No hay un método mejor; cada uno tiene su límite" | tabla inversa / transformación especial / rechazo
  7. E1 5:50 "¿Y si no puedo invertir F? Von Neumann: proponer y filtrar" | geometric accept/reject points; transition to E2
  8. E2 6:40 "Tres ingredientes: f, g y M, con f ≤ M·g" | curve + envelope + 3 labels
  9. E2 7:50 "El algoritmo en 4 pasos" | flowchart with rejection loop
  10. E2 9:00 "La g se cancela: por eso los aceptados siguen f" | 3-line proof
  11. E2 10:20 "Beta(2,2): M=1.5 y la regla queda 4Y(1−Y)" | derivative steps
  12. E2 11:40 "5 intentos a mano: se aceptan 3 (60 % vs 66.7 % teórico)" | table + audience question
  13. E3 13:20 "El código repite lo que hicimos a mano" | live demo (S4): Python code + running simulation
  14. E3 14:40 "El histograma confirma la forma" | live histogram vs curve, mean 0.5, var 0.05
  15. E3 16:00 "Correcto no es lo mismo que eficiente: aceptación = 1/M" | live M switch 1.5/2/3/6
  16. E3 17:20 "Dónde se usa y cuándo no conviene" | applications + common errors
  17. E3 18:40 "Lo que hay que llevarse" | closing on general methods + Von Neumann as a filter + 2 review questions
- **S6** Content facts to keep exact (from the draft): Beta(2,2) f(x)=6x(1−x); M=1.5; rule U ≤ 4Y(1−Y); trial table (Y,U,4Y(1−Y),result): (0.20,0.60,0.64,Aceptado) (0.80,0.90,0.64,Rechazado) (0.50,0.80,1.00,Aceptado) (0.10,0.50,0.36,Rechazado) (0.65,0.70,0.91,Aceptado); E[X]=0.5, Var=0.05, P(A)=1/M; M table 1.5→66.67 %/15 000, 2→50 %/20 000, 3→33.33 %/30 000, 6→16.67 %/60 000 for 10 000 samples; transitions from Anexo A; hard-question answers from Anexo B (including h(x), Z/M) go in the speaker guide only.
- **S7** 1-hour version (L10-L11): user asked "cuanto tiempo duraria la expo, en teoria?" then "hagamolo para 1h". Approved 39-slide outline minus h(x) slide ("No, sigue solo en el guion") and minus Práctica 09 ("No"); activity slide interactive ("Sí, interactiva"). Final 37 slides, ~18 min per speaker + 6 min question round:
  - E1 0:00–18:00: 1 Portada · 2 Objetivos de la clase · 3 Simular es incorporar incertidumbre (restaurante) · 4 Experimento aleatorio y variable aleatoria (X es una función) · 5 Discreta vs continua · 6 Uniforme vs no uniforme (densidad >1) · 7 Función acumulada F(x) · 8 Esperanza y varianza (sirven para validar; Beta 0.5 / 0.05) · 9 Pseudoaleatorios y semilla · 10 Transformada inversa: por qué funciona · 11 Ejemplo exponencial paso a paso · 12 Transformaciones especiales (Box-Muller, mención) · 13 Comparación de 3 métodos · 14 Von Neumann: candidato, filtro y muestra final · 15 Demostración visual con puntos + pase a E2
  - E2 18:00–36:00: 16 Tres ingredientes f, g, M · 17 Tres condiciones: normalización, cobertura, dominación · 18 M ≥ sup f/g y M ≥ 1 · 19 Algoritmo (flujo) · 20 ¿Por qué U, g y M en la regla? · 21 Pseudocódigo (intentos variables) · 22 Demostración pasos 1-2 (cancelación de g) · 23 Demostración pasos 3-4 (P(A)=1/M, f(y|A)=f) · 24 Beta(2,2): comprobar que es densidad (∫=1) · 25 Beta(2,2): M por derivada (f'=0, f''<0) · 26 Regla 4Y(1−Y) + tabla 5 intentos · 27 Actividad INTERACTIVA: el público dicta Y y U, se ingresan en la diapositiva y muestra umbral 4Y(1−Y), punto sobre la gráfica y Aceptado/Rechazado
  - E3 36:00–54:00: 28 Qué necesita la implementación · 29 Demo en vivo código + simulación · 30 Histograma y estadísticas · 31 Eficiencia observada vs teórica; geométrica E[T]=M · 32 Efecto de M (switch de la demo, tabla) · 33 Eficiencia no es solo el % de aceptación (costo de generar/evaluar) · 34 Aplicaciones · 35 Cuándo conviene / errores frecuentes · 36 Lo que aprendimos (current slide 17 text, no numbers)
  - Todos 54:00–60:00: 37 Preguntas (current interactive slide 18, 5 questions with reveal buttons)
  - h(x) stays guide-only. No Práctica 09 slide.

## Tasks

- T1 S1-S3,S5 Outline ordered and approved (inline, done in chat) — no commit
- T2 S2,S4-S6 Build deck HTML (animated, live demo) + PDF in destination; render + check_deck (worker) — commit: pending
- T3 S2,S5,S6 Build A4 speaker guide (mixed script, transitions, prepared answers incl. h(x)) (worker, after T2) — commit: pending
- T4 Gate 2: user visual review of PDF/HTML — pending
- T5 L8: add slide 18 "Preguntas" (closing round) with 5 very simple questions, each answer revealed by a button (worker) — commit: pending
- T6 S7: rebuild deck to 37 slides / 60 min, interactive activity slide 27, speaker guide retimed, zip (worker) — commit: pending

## Log

- L1 (2026-11-22) User: "/home/alejo/Downloads/Guia_Detallada_3_Expositores_Von_Neumann.pdf mira tengo una expo mañana sobre esto, es un borrador, pero se me hace muy extenso y complicado de entender, ordena las ideas y planteame la estrucura, lo qur quiero es al final generar la diapos y el guion, somo 3 expositores"
- L2 Answers: duration "osea unos 20 mins pero de contenido de calidad"; format "pdf y html"; script "una mezcla de los 2"; h(x) "No, solo en el guion"; theme metro-deck; destination "Carpeta del curso Simulación".
- L3 User: "veras que el titulo no es que planteaste es algo de variables aleatorias, revisa bien el guion que te pase" → outline rebuilt to 17 slides (S5).
- L4 User: "en tema practica quieisera que por detras corra el codigo de phyton y se vayan mostrando la data para exponer igual"; chose "Dentro de la diapo HTML (recomendado)" (S4). Outline treated as approved with this change.
- L7 User: "pero las preguntas al final, no entre diapos" → guide page 7 reframed as closing round after slide 17 (commit 449d44d).
- L8 User: "y agrega la tanda al final de una diapo, pero interactivo que con un bopton se muestre la respuestas, preguntas bien sencillas" → T5.
- L10 User: "cuanto tiempo duraria la expo, en teoria?" → answered ~22:30 (20:00 + question round).
- L11 User: "hagamolo para 1h" → outline approved; h(x) "No, sigue solo en el guion"; Práctica 09 "No"; activity "Sí, interactiva" (S7, T6). 20-min zip backed up as ~/Downloads/expo-variables-aleatorias-von-neumann-20min.zip.
