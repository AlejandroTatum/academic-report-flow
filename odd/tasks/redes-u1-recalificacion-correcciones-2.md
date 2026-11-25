# Reporte de Auditoría Técnica y de Formato — Recalificación APE 002 a APE 005

> **Instrucciones para el agente receptor:** Este documento contiene únicamente hallazgos de auditoría (errores de maquetación, inconsistencias de datos, fallos de formato IEEE y riesgos de transparencia en la declaración de IA) detectados en las versiones recalificadas de los informes APE 002, APE 003, APE 004 y APE 005. **No apliques correcciones automáticamente.** Muestra cada bloque al usuario indicando el ID del hallazgo, qué ocurre y qué decisión se requiere, para que él determine qué cambios son relevantes y cuáles descarta.

---

## 1. Hallazgos Críticos (Maquetación rota, inconsistencias de autoría y riesgo académico)

### [AUD-01] Maquetación rota en Tabla 7, encabezado 9.2 y Tabla 8 (APE 002)
* **Hallazgo:** Al continuar la **Tabla 7** tras el salto de página, el encabezado repetido (`Propuesta Propuesta de`) y las últimas tres filas pierden la estructura de tabla[cite: 1].
* **Hallazgo:** El título `9.2. Reflexión crítica personal por estudiante`, su párrafo introductorio y el título `Tabla 8. Parte, aprendizaje y compromiso de cada integrante.` quedaron fusionados y desordenados dentro de la fila de encabezado de la propia **Tabla 8**[cite: 1].
* **Hallazgo:** El subtítulo `9.2.1. Emilio Flores` quedó atrapado como la última fila vacía dentro de la **Tabla 8** en lugar de aparecer como encabezado independiente fuera de la tabla[cite: 1].
* **Decisión requerida:** Corregir los saltos de página y reconstruir el marcado de Tabla 7, sección 9.2, Tabla 8 y subsección 9.2.1 en APE 002[cite: 1].

### [AUD-02] Rastro de nombre ajeno a la lista de integrantes: «Sergio» / `partesergio` (APE 005)
* **Hallazgo:** En el **Anexo B (Tabla 15)**, el archivo entregado por **Julian Vega** figura con el nombre `partesergio (PDF)`[cite: 5] (en la versión anterior aparecía como `Partesergio (PDF)`[cite: 4]).
* **Hallazgo:** En la **Tabla 17 (Prompts literales)**, el Prompt Nro. 1 asigna explícitamente el Escenario 5 a **`Sergio`** (*«Sergio • Resolverá la Parte 2 (Escenario 5)...»*)[cite: 5], mientras que la **Tabla 1**, la **Tabla 12** y la **Tabla 15** asignan ese mismo escenario a **Julian Vega**[cite: 5].
* **Riesgo:** Si el docente no sabe que «Sergio» corresponde a Julian Vega (p. ej., primer nombre), puede interpretarlo como un error de autoría o reutilización de un archivo externo.
* **Decisión requerida:** Confirmar si el nombre completo del integrante es *Sergio Julian Vega* para unificarlo en las tablas, o agregar una nota aclaratoria / ajustar la referencia al nombre del archivo[cite: 5].

### [AUD-03] Tablas rotas y columnas fusionadas en APE 005 (Impacto ambiental, Tabla 15, Tabla 16 y Tabla 17)
* **Hallazgo (Tabla de impacto ambiental):** La tabla con columnas `Ámbito | Impacto identificado | Alternativa sostenible | Propuesta de` perdió sus bordes/rejilla y aparece cortada en su última fila (*«elegir la velocidad según la necesidad»*)[cite: 5].
* **Hallazgo (Tabla 15):** `Tabla 15. Aportes individuales y ajustes de la integración` se renderizó como una lista de viñetas separadas por punto y coma (`;`) en lugar de una tabla real[cite: 5], a diferencia de la versión anterior (`Tabla 10`) donde sí tenía 3 columnas[cite: 4] y de las tablas equivalentes de APE 002, 003 y 004[cite: 1, 2, 3]. Además, en el ítem de **Alejandro Padilla Espinoza** se omitió el segundo campo (archivo entregado), quedando solo 2 campos separados por punto y coma en vez de 3[cite: 5].
* **Hallazgo (Tabla 16 y Tabla A de APE 002):** En APE 005 (`Tabla 16`)[cite: 5] y APE 002 (`Tabla A`)[cite: 1], la fila `Trabajo delegado a la IA` se desprendió fuera de la estructura de tabla de 2 columnas[cite: 1, 5].
* **Hallazgo (Tabla 17):** Las columnas 2 y 3 quedaron fusionadas en una sola (`Tarea / Sección asistida Prompt textual utilizado`), mezclando el título de la tarea con el texto literal del prompt línea por línea[cite: 5]. Adicionalmente, la fila `5` se partió en tres filas separadas[cite: 5].
* **Decisión requerida:** Reconstruir la maquetación de las tablas afectadas en APE 005 y APE 002 para evitar cortes y fusión de columnas[cite: 1, 5].

### [AUD-04] Redacción en tiempo pendiente sobre reflexiones hechas por IA (APEs 002, 003, 004 y 005)
* **Hallazgo:** En la **Sección 12 (Declaración de uso de IA Generativa)** de los cuatro documentos recalificados se declara que la IA redactó borradores de las reflexiones personales y que estos aún están pendientes de revisión:
  * **APE 002:** *«los borradores de reflexión personal quedan sujetos a la revisión de cada integrante»*[cite: 1].
  * **APE 003:** *«redactar borradores de las reflexiones personales a partir de los aportes de cada integrante, para que cada uno los revise y apruebe»*[cite: 3].
  * **APE 004:** *«redactar los borradores de las reflexiones personales que cada integrante revisa»*[cite: 2].
  * **APE 005:** *«redactar borradores de los párrafos de aprendizajes de cada integrante, que cada uno revisa»*[cite: 5].
* **Riesgo:** Entregar el informe definitivo indicando que las reflexiones personales «quedan sujetas a revisión» sugiere que se está entregando un borrador no validado por los autores.
* **Decisión requerida:** Confirmar si los compañeros ya revisaron y aprobaron sus reflexiones; de ser así, cambiar la redacción a tiempo pasado verificado (p. ej., *«revisados, ajustados y aprobados por cada integrante»*).

### [AUD-05] Prompts literales sensibles frente a la evaluación docente (APEs 003, 004 y 005)
* **Hallazgo (APE 005, Tabla 17, Prompt 2):** Se incluye textualmente: *«no hay que pararle bola al guia del ape, mas es la guia de cisco»*[cite: 5].
* **Hallazgo (APE 005, Tabla 17, Prompt 1):** Se incluye textualmente: *«si falta algun punto lo completas tu»*[cite: 5].
* **Hallazgo (APE 004, Tabla 13, Prompt 4 y Trabajo delegado):** Se declara que se pidió a la IA *«completa la parte de emilio y arranca con el documento final»* y que la IA se encargó de *«completar la parte de Emilio con el escenario del correo y los ejemplos visuales de las capas 1 y 2»*[cite: 2].
* **Hallazgo (APE 003, Tabla 11, Prompt 5 y APE 005, Tabla 17, Prompt 5):** Se transcribe: *«tienes que ayudarme con reflexiones que sean similares a las que ya me pasaron mis compañeros»*[cite: 3, 5].
* **Decisión requerida:** Aunque la transparencia exige honestidad académica, el compañero debe evaluar si mantiene esos prompts exactamente así o si conviene contextualizarlos/aclarar el alcance de la validación humana para no perjudicar la calificación individual o grupal.

---

## 2. Hallazgos Moderados (Formato IEEE, jerarquía de títulos y metadatos)

### [AUD-06] Formato mixto e inconsistente en referencias bibliográficas IEEE (APE 002 y APE 005)
* **Hallazgo (APE 002):** La bibliografía alterna entre corchetes estilo IEEE (`[12]`, `[16]`, `[17]`, `[20]`, `[21]`) y listas numeradas con punto (`13.`, `14.`, `15.`, `18.`, `19.`)[cite: 1]. Este fallo ya venía arrastrándose en versiones previas de APE 002, APE 003 y APE 004[cite: 6, 7, 8].
* **Hallazgo (APE 002, Ref. 13):** El nombre del organismo aparece con mezcla de inglés y español: `National Institute of Standards y Technology`[cite: 1]. Además, en la sección `8. Recomendaciones` se cita `[13]` para respaldar la norma **`ANSI/TIA/EIA-606`**[cite: 1], pero la referencia `13.` apunta a **`NIST FIPS PUB 187` (1994)**[cite: 1] (conviene verificar si se mantiene FIPS 187 aclarando que adopta TIA/EIA-606 o si se cita directamente la norma ANSI/TIA-606).
* **Hallazgo (APE 005, Ref. [46]):** La referencia `[46]` de la IEA (*«Energy and AI»*) omite el año de publicación (`2025`) y la ciudad (`París`), usa punto tras el autor en lugar de coma y encierra el título entre comillas angulares en vez de cursiva[cite: 5], a diferencia de la misma referencia en APE 002 (`19.`) que sí incluye `París, 2025` y cursiva[cite: 1].
* **Decisión requerida:** Corregir la plantilla/motor de bibliografía para forzar corchetes `[n]` en todas las entradas y normalizar las referencias `13.` (APE 002) y `[46]` (APE 005)[cite: 1, 5].

### [AUD-07] Inconsistencia en numeración de tablas y jerarquía de la Sección 12 (APE 002 y APE 005)
* **Hallazgo (Numeración de tablas):** En **APE 002**, la tabla de registro de IA se denomina **`Tabla A`** (alfabética)[cite: 1], rompiendo la numeración arábiga continua del resto de APE 002 (`Tabla 1` a `Tabla 9`)[cite: 1] y la convención de APE 003 (`Tabla 11`)[cite: 3], APE 004 (`Tabla 13`)[cite: 2] y APE 005 (`Tabla 16`, `Tabla 17`)[cite: 5].
* **Hallazgo (Jerarquía de encabezados):** Tanto en **APE 002**[cite: 1] como en **APE 005**[cite: 5], el título `12. Declaración de uso de IA Generativa` aparece como nivel 4 (`####`, al mismo nivel que `11.1. Anexo A` o `11.2. Anexo B`) en lugar de nivel 3 (`###`, al nivel de `11. Anexos`)[cite: 1, 5].
* **Decisión requerida:** Renumerar `Tabla A` en APE 002 a numeración arábiga continua y subir la jerarquía de `12. Declaración de uso de IA Generativa` a nivel de sección principal[cite: 1, 5].

### [AUD-08] Diferencias en Datos de Identificación (APE 004)
* **Hallazgo:** En la sección `1. Datos de Identificación` de la versión recalificada de **APE 004**, desapareció la fila `Tipo | Actividad práctico-experimental`[cite: 2] que sí constaba en la versión anterior[cite: 6].
* **Hallazgo:** La fecha cambió de `2026-10-27` (versión anterior)[cite: 6] a `2026-10-30` (versión recalificada)[cite: 2]. Nota: el 30 de octubre de 2026 sí coincide con el horario `Viernes 09:30 – 11:30`[cite: 2], pero conviene confirmar que el cambio y la omisión de `Tipo` correspondan a la nueva plantilla oficial.
* **Decisión requerida:** Verificar contra la plantilla oficial si debe restituirse la fila `Tipo` y confirmar `2026-10-30` como fecha definitiva[cite: 2, 6].

### [AUD-09] Criterio inconsistente de anonimización de rutas en Prompts (APEs 002, 004 y 005)
* **Hallazgo:** El mismo archivo de auditoría aparece expuesto con su nombre literal `auditor_a_y_especificaci_n_de_correcciones_ape_002_a_005.md` en **APE 002**[cite: 1], mientras que en **APE 004** fue anonimizado como `[ruta del archivo de auditoría]`[cite: 2] y en **APE 005** se mezcla `[ruta]/LAB...` con `[rutas de...]`[cite: 5].
* **Decisión requerida:** Definir un único formato de anonimización (p. ej., `[ruta del archivo de auditoría]`) y aplicarlo uniformemente en los cuatro documentos[cite: 1, 2, 5].

### [AUD-10] Verificación de subcarpeta de Fase 5 en GitHub (APE 005, Tabla 12)
* **Hallazgo:** En la **Tabla 12**, las Fases 1 a 4 apuntan a subcarpetas específicas (`ape-1-conceptos-networking`, `ape-1-fase-2-hardware-redes`, `ape-1-fase-3-software-redes`, `ape-1-fase-4-osi-redes`), mientras que la **Fase 5** indica únicamente la carpeta padre `unidad-1`[cite: 5]. Además, los saltos de línea en la columna introducen espacios tras los guiones (ej. `ape-1-conceptos- networking`)[cite: 5].
* **Decisión requerida:** Confirmar si el PDF de la Fase 5 reside en la raíz de `unidad-1` o si tiene su propia subcarpeta, y verificar que el texto de las rutas en el PDF no inserte espacios al copiarse[cite: 5].

---

## 3. Hallazgos Menores (Estilo, precisión técnica y controles de verificación)

### [AUD-11] Posible omisión de sufijo técnico en reflexión de APE 004 (Sección 9.2.1)
* **Hallazgo:** En la reflexión de **Emilio Flores** (APE 004), al hablar de ahorro energético en enlaces, se indica: *«por eso propongo revisar el cableado y usar IEEE 802.3»*[cite: 2]. IEEE 802.3 corresponde a Ethernet general; para eficiencia energética el estándar específico citado en APE 002 es **IEEE 802.3az**[cite: 1].
* **Decisión requerida:** Confirmar si se mantiene `IEEE 802.3` o se precisa a `IEEE 802.3az`[cite: 1, 2].

### [AUD-12] Fila partida y comilla invertida en Tabla 11 (APE 003)
* **Hallazgo:** En **APE 003 (Tabla 11)**, el Prompt 4 abre con comilla de cierre (`”hagamos una modificacion...`) en lugar de comilla de apertura (`“`)[cite: 3].
* **Hallazgo:** La fila `5` de la **Tabla 11** se dividió en dos filas distintas de la tabla (*«Borradores de las reflexiones»* / *«personales»*)[cite: 3].
* **Decisión requerida:** Corregir la comilla de apertura del Prompt 4 y unir la fila `5` en una sola fila[cite: 3].

### [AUD-13] Inconsistencias menores de estilo en títulos y celdas de tablas (APEs 002–005)
* **Hallazgo (Títulos de tablas):** APE 003, APE 004 y APE 005 añaden entre paréntesis los nombres de columna en los títulos de tabla (ej. `Tabla 11. Archivos de los aportes individuales (integrante; archivo entregado; contenido).`)[cite: 2, 3, 5], mientras que APE 002 no utiliza ese formato (`Tabla 1. Distribución de tareas del equipo.`)[cite: 1].
* **Hallazgo (Mayúsculas en celdas):** En las nuevas versiones de APE 003 (`Tabla 1`, `Tabla 7`, `Tabla 9`)[cite: 3], APE 004 (`Tabla 11`)[cite: 2] y APE 005 (`Tabla 1`, `Tabla 12`)[cite: 5], varias celdas inician con minúscula (`paso 1`, `software de redes`, `menos equipos dados de baja`), mientras que en APE 002[cite: 1] y en las columnas 1–2 de `Tabla 7` en APE 003[cite: 3] inician con mayúscula.
* **Decisión requerida:** Decidir si se uniformizan los títulos de tablas y la capitalización inicial de las celdas en los 4 APEs, o si se deja como está.

### [AUD-14] Confirmación de corrección de roles en APE 002 (Versión anterior vs. nueva)
* **Hallazgo (verificación positiva):** En la versión anterior de APE 002 (`Tabla 7`), **Julian Vega** figuraba con el Paso 4 y **Royel Jima** con el Paso 5[cite: 8]. En la versión recalificada (`Tabla 1`, `Tabla 8` y `Tabla 9`), esto ya aparece corregido y consistente: **Royel Jima** (Paso 4) y **Julian Vega** (Paso 5)[cite: 1].
* **Decisión requerida:** Solo confirmar que la asignación actual de la versión recalificada es la correcta[cite: 1].

---

## 4. Matriz de Decisión para el Usuario

| ID | Documento(s) | Categoría | Prioridad | Decisión del usuario (Aplicar / Descartar / Ajustar) |
| :--- | :--- | :--- | :--- | :--- |
| **AUD-01** | APE 002[cite: 1] | Tabla 7 rota; 9.2 y Tabla 8 fusionados; 9.2.1 dentro de tabla[cite: 1] | Crítica | _Pendiente_ |
| **AUD-02** | APE 005[cite: 5] | Nombre «Sergio» en Prompt 1 y `partesergio (PDF)` vs. Julian Vega[cite: 5] | Crítica | _Pendiente_ |
| **AUD-03** | APE 002, 005[cite: 1, 5] | Tablas rotas/fusionadas (Tabla 15 como viñetas, Tabla 16/A, Tabla 17)[cite: 1, 5] | Crítica | _Pendiente_ |
| **AUD-04** | APE 002–005[cite: 1, 2, 3, 5] | Declaración de IA dice que reflexiones siguen «sujetas a revisión»[cite: 1, 2, 3, 5] | Crítica | _Pendiente_ |
| **AUD-05** | APE 003–005[cite: 2, 3, 5] | Prompts literales con riesgo académico frente al docente[cite: 2, 3, 5] | Crítica | _Pendiente_ |
| **AUD-06** | APE 002, 005[cite: 1, 5] | Bibliografía IEEE mixta (`[n]` vs `n.`), NIST/TIA-606 y Ref. `[46]` incompleta[cite: 1, 5] | Moderada | _Pendiente_ |
| **AUD-07** | APE 002, 005[cite: 1, 5] | `Tabla A` en APE 002 y nivel `####` en Sección 12[cite: 1, 5] | Moderada | _Pendiente_ |
| **AUD-08** | APE 004[cite: 2, 6] | Omisión de fila `Tipo` y confirmación de fecha `2026-10-30`[cite: 2, 6] | Moderada | _Pendiente_ |
| **AUD-09** | APE 002, 004, 005[cite: 1, 2, 5] | Anonimización inconsistente de rutas de archivos en prompts[cite: 1, 2, 5] | Moderada | _Pendiente_ |
| **AUD-10** | APE 005[cite: 5] | Ruta de carpeta `unidad-1` en Fase 5 y guiones partidos en Tabla 12[cite: 5] | Moderada | _Pendiente_ |
| **AUD-11** | APE 004[cite: 2] | Precisar `IEEE 802.3` vs `IEEE 802.3az` en reflexión 9.2.1[cite: 1, 2] | Menor | _Pendiente_ |
| **AUD-12** | APE 003[cite: 3] | Comilla invertida en Prompt 4 y fila 5 dividida en Tabla 11[cite: 3] | Menor | _Pendiente_ |
| **AUD-13** | APE 002–005[cite: 1, 2, 3, 5] | Paréntesis descriptivos en títulos y mayúsculas iniciales en tablas[cite: 1, 2, 3, 5] | Menor | _Pendiente_ |
| **AUD-14** | APE 002[cite: 1, 8] | Confirmar corrección definitiva de Paso 4 (Royel) y Paso 5 (Julian)[cite: 1, 8] | Control | _Pendiente_ |