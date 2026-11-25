# Especificación de Auditoría y Correcciones para Agente de IA (APE 002, 003, 004 y 005)

**Asignatura:** Fundamentos de Redes de Comunicaciones (5to Ciclo - UNL)  
**Integrantes del equipo (Grupo A):** Miguel Veintimilla, Emilio Flores, Royel Jima, Julian Vega, Alejandro Padilla Espinoza  
**Propósito de este documento:** Este archivo contiene las instrucciones de corrección obligatorias derivadas de la auditoría académica contra la **Plantilla Oficial de Reporte Técnico de APE**, las **Rúbricas de Evaluación (APE 2 a 5)** y las **disposiciones directas del docente/tutor**. El agente de IA que opera sobre el repositorio debe ejecutar cada punto de forma secuencial en los cuatro informes.

---

## 1. Reglas Globales Obligatorias (Aplicables a APE 002, 003, 004 y 005)

El agente de IA debe garantizar que los **cuatro informes** cumplan estrictamente la siguiente estructura numerada de la plantilla oficial:

1. **1. Datos de Identificación del Estudiante y la Práctica**
   * Mantener únicamente los **12 campos oficiales** de la plantilla: `Nombre del estudiante(s)`, `Asignatura`, `Ciclo`, `Unidad`, `Resultado de aprendizaje de la unidad`, `Práctica Nro.`, `Título de la Práctica`, `Nombre del Docente`, `Fecha`, `Horario`, `Lugar`, `Tiempo planificado en el Sílabo`.
   * **Eliminar** la fila adicional `Tipo | Actividad práctico-experimental` que no existe en la plantilla oficial.
   * Verificar que la `Fecha` coincida con el día de la semana declarado en `Horario` (`Viernes 09:30 – 11:30`) y que ninguna referencia bibliográfica tenga fecha de consulta posterior a la fecha de entrega del informe.
2. **2. Objetivo(s) de la Práctica**
   * Redactar todos los objetivos en infinitivo (`Comprender...`, `Identificar...`, `Investigar...`) y alinearlos estrictamente con lo que se ejecuta y concluye en esa fase específica.
3. **3. Materiales, Reactivos, Equipos y Herramientas**
   * Incluir la totalidad del hardware, simuladores (Cisco Packet Tracer), plataformas académicas (EVA, Netacad), repositorios/fuentes de datos y herramientas colaborativas/gráficas empleadas (Google Drive, Canva, Discord, GitHub).
4. **4. Procedimiento / Metodología Ejecutada**
   * Describir los pasos ejecutados y mantener/incorporar una subsección explícita **`Trabajo colaborativo, equidad e inclusión`** junto con la tabla de distribución de tareas, evidenciando cómo se promovió la participación equitativa, el respeto a la diversidad de horarios/capacidades y la revisión cruzada entre pares (criterio de 2 puntos en la rúbrica).
5. **5. Resultados**
   * Incluir exclusivamente las evidencias técnicas, tablas, figuras, simulaciones y cuestionarios de la práctica. **No esconder la reflexión crítica ni la reflexión ambiental dentro de Resultados**.
6. **6. Preguntas de Control**
   * **Disposición del tutor:** Mantener la sección `6. Preguntas de Control`, pero **únicamente con los enunciados planteados (sin respuestas desarrolladas)**. *(Ver nota de verificación en el Módulo 4 para el APE 005).*
7. **7. Conclusiones**
   * Redactar conclusiones puntuales vinculadas directamente uno a uno con los objetivos declarados en la sección `2`.
8. **8. Recomendaciones**
   * Sección obligatoria de la plantilla oficial en **todos** los informes. Incluir sugerencias técnicas concretas para mejorar la práctica o su aplicación en casos reales.
9. **9. Reflexión crítica**
   * Sección principal obligatoria de la plantilla oficial en **todos** los informes. Debe dividirse en:
     * **9.1. Responsabilidad ambiental, huella digital y ética profesional (Síntesis grupal y propuestas sostenibles concretas).**
     * **9.2. Reflexión crítica personal por estudiante (5 subapartados individuales):** uno por cada integrante (*Emilio Flores, Miguel Veintimilla, Royel Jima, Julian Vega y Alejandro Padilla Espinoza*). Cada estudiante debe redactar en primera persona: **(a) Aprendizajes y conocimientos técnicos adquiridos en la práctica** y **(b) Compromiso de responsabilidad ambiental y ética profesional**.
10. **10. Bibliografía / Referencias**
    * Numerar la sección como `10. Bibliografía / Referencias`.
    * Unificar el estilo **IEEE en un solo idioma (español)** en todas las entradas (evitar mezclar `and`, `[Online]. Available:`, `Accessed:` con `Consultado el`, `Boletín`). Asegurar que los corchetes `[1]`, `[2]`, etc., se mantengan consistentes.
11. **11. Anexos**
    * Tablas de archivos de aportes individuales y registros de verificación.
12. **12. Declaración de uso de IA Generativa**
    * Obligatoria al cierre de **todos los informes (APE 002, 003, 004 y 005)**. Debe contener explícitamente tres elementos:
      1. **Trabajo delegado a la IA** (tareas específicas asistidas en esa práctica).
      2. **Modelo exacto utilizado** (nombre del entorno y versión exacta del modelo, ej. *Claude 3.5 Sonnet / Claude 3.7 Sonnet de Anthropic en entorno Pi - el Gentleman*).
      3. **Prompt(s) utilizado(s)** (transcripción literal de los prompts empleados, no solo un resumen del propósito).

---

## 2. Resultado de la Auditoría del APE 005 (Fase 05)

Antes de listar las instrucciones de modificación por archivo, se registran los hallazgos específicos detectados en el **APE 005**:

1. **Incumplimiento del orden y títulos de la Plantilla Oficial (Secciones 7 a 10):**
   * En el APE 005 se insertaron las secciones `7. Informe Integrador de la Unidad 1` y `8. Responsabilidad Ambiental y Ética Profesional` **antes** de `9. Conclusiones` y `10. Recomendaciones`, alterando la estructura oficial de la plantilla.
   * **No existe la sección `Reflexión crítica`** con el título exigido por la plantilla oficial; su contenido quedó fragmentado entre `7.2` (grupal) y `8.2` (ambiental/ético individual).
2. **Reflexiones individuales incompletas respecto a la plantilla (`8.2.1` a `8.2.5`):**
   * Los 5 integrantes tienen su subapartado individual en `8.2`, pero solo reflexionan sobre consumo energético y ética de su escenario de banda ancha. La plantilla oficial exige en **`Reflexión crítica`**: *"Indique los detalles de aprendizaje y conocimientos adquiridos. Indique lo que aprendió"*. Debe integrarse en cada bloque individual lo aprendido técnicamente (simulación TCP/IP en Packet Tracer y tecnologías de acceso) junto con la reflexión ambiental y ética.
3. **Sección `6. Preguntas de Control` con respuestas desarrolladas:**
   * A diferencia de APE 002, 003 y 004, el APE 005 desarrolla extensamente las respuestas de las 3 preguntas en las páginas 17 a 19. Según la regla indicada (*"deja la sección pero detalla que deben estar solo los enunciados planteados"*), las respuestas deben retirarse de la sección `6` (dejando solo los enunciados) y su contenido teórico clave (comparativa OSI vs. TCP/IP y TCP vs. UDP) debe reubicarse en la subsección `5.1` o `5.4` para no perder el puntaje del criterio **Conocimiento teórico** de la rúbrica.
4. **Defectos de redacción en `2. Objetivo(s) de la Práctica`:**
   * Las viñetas 4 y 5 dicen literalmente: `Parte 1: Investigue la distribución de banda ancha.` y `Parte 2: Investigue las opciones de acceso por banda ancha para situaciones específicas.` (copiadas en modo imperativo de la guía de laboratorio en lugar de redactarse como objetivos en infinitivo, e ignorando mencionar el hardware y software de red que pide la rúbrica de APE 5).
5. **Inconsistencia de fecha en `1. Datos de Identificación`:**
   * Declara `Fecha: 2026-11-12` (jueves) junto con `Horario: Viernes 09:30 – 11:30`, mientras que las capturas de Packet Tracer (`Figura 13`) muestran fecha de ejecución `2026-11-06` (viernes).
6. **Declaración de uso de IA Generativa incompleta y con tabla rota:**
   * En la página 27 del APE 005, el encabezado `Tabla B. Instrucciones dadas` quedó incrustado por error dentro de una fila de la `Tabla A`.
   * No especifica la **versión exacta del modelo** Claude de Anthropic.
   * En `Tabla B` solo describe un resumen de una línea (`Instrucción` / `Propósito`) en lugar de incluir el **prompt textual utilizado**.

---

## 3. Instrucciones Detalladas de Modificación por Informe para el Agente de IA

### MÓDULO 1: Modificaciones en APE 002 (`ape-1-fase-2-hardware-redes`)

1. **Sección `1. Datos de Identificación`:**
   * Eliminar la fila `Tipo | Actividad práctico-experimental`.
   * Añadir `Viernes` en el campo `Horario` (`Viernes 09:30 – 11:30`) para uniformidad con las demás fases.
   * Ajustar la fecha del informe o las fechas de acceso de las referencias `[16]`, `[17]` y `[18]` (actualmente dicen `Oct. 20, 2026` mientras la práctica tiene fecha `2026-10-16`) para eliminar la incongruencia cronológica.
2. **Sección `2. Objetivo(s) de la Práctica`:**
   * Ajustar o acotar los objetivos generales para que reflejen con precisión el alcance de la Fase 2 (conceptos de networking, identificación y clasificación de hardware NIC/switches/routers/cables en capas OSI y su correspondencia con TCP/IP y estándares IEEE 802.3/802.11, trabajo colaborativo e impacto ambiental/ético).
3. **Sección `3. Materiales, Reactivos, Equipos y Herramientas`:**
   * Detallar el uso de hojas de datos técnicas (*datasheets*) de fabricantes (Cisco, D-Link, 3Com, HP, Linksys), herramientas de edición colaborativa en Google Drive y plataforma EVA.
4. **Sección `4. Procedimiento / Metodología Ejecutada`:**
   * Añadir la subsección **`4.1. Trabajo colaborativo, equidad e inclusión`** explicando cómo el equipo distribuyó equitativamente el inventario y el estudio de mercado entre los 5 integrantes considerando sus capacidades y disponibilidad horaria, y cómo se realizó la revisión cruzada de datos técnicos y consumos energéticos en Google Drive antes de integrar el documento.
5. **Sección `5. Resultados`:**
   * En la `Tabla 2` (Inventario del laboratorio), añadir la referencia explícita a la capa equivalente del modelo **TCP/IP** (`Acceso a la red` o `Internet`) y el estándar aplicable (`IEEE 802.3`, `IEEE 802.11g/n`) para conectar rigurosamente teoría y práctica según la rúbrica.
   * **Extraer** las subsecciones `5.5. Reflexión sobre el impacto ambiental` y `5.6. Análisis individual de los integrantes` fuera de `5. Resultados` y trasladarlas a la nueva sección **`9. Reflexión crítica`**.
6. **Sección `6. Preguntas de Control`:**
   * Mantener únicamente los 3 enunciados planteados sin respuestas.
7. **Sección `7. Conclusiones`:**
   * Retirar la excusa *"la comparación de los modelos OSI y TCP/IP se completa en la última APE"* y concluir directamente sobre la correspondencia de capas OSI y TCP/IP observada en los equipos de capa 1, 2 y 3 del laboratorio.
8. **CREAR Sección `8. Recomendaciones` (Faltante en APE 002):**
   * Insertar entre `7. Conclusiones` y `9. Reflexión crítica` al menos 4 recomendaciones técnicas vinculadas a la práctica (ej. verificación de soporte IEEE 802.3az Energy-Efficient Ethernet en la adquisición de switches de campus, etiquetado estructurado TIA/EIA-606 en el rack del laboratorio, uso de cableado con chaqueta LSZH en espacios cerrados y entrega de hardware dado de baja a gestores calificados por el MAATE).
9. **CREAR Sección `9. Reflexión crítica` (Reestructuración de `5.5` y `5.6`):**
   * **`9.1. Responsabilidad ambiental, huella digital y ética profesional (Síntesis y propuestas sostenibles)`:** Conservar el análisis de ciclo de vida y RAEE de `5.5`, y **añadir un párrafo sobre ética profesional y huella digital** (honestidad técnica al dimensionar redes sin sobreaprovisionar equipos, transparencia en especificaciones y reducción del consumo energético en operación 24/7), incluyendo una tabla o lista de propuestas sostenibles concretas.
   * **`9.2. Reflexión crítica personal por estudiante`:** Conservar los 5 bloques individuales (`9.2.1. Emilio Flores`, `9.2.2. Alejandro Padilla Espinoza`, `9.2.3. Miguel Veintimilla`, `9.2.4. Royel Jima`, `9.2.5. Julian Vega`).
     * **Corrección en `9.2.1. Emilio Flores`:** Añadir la etiqueta en negrita **`Reflexión personal (Emilio Flores):`** que faltaba antes de su último párrafo.
     * En los **5 integrantes**, asegurar que el apartado **`Reflexión personal:`** declare explícitamente: (1) qué aprendió técnicamente al analizar sus equipos de red, y (2) su reflexión ética y ambiental personal.
10. **Sección `10. Bibliografía / Referencias` y `11. Anexos`:**
    * Numerar `10. Bibliografía / Referencias` y estandarizar todas las citas IEEE al español (cambiar `[Online]. Available:` y `Accessed:` por `[En línea]. Disponible en:` y `Consultado el...`).
    * Renumerar Anexos como `11. Anexos`.
11. **CREAR Sección `12. Declaración de uso de IA Generativa` (Faltante en APE 002):**
    * Añadir al final del informe siguiendo la plantilla de la Sección 4 de este documento.

---

### MÓDULO 2: Modificaciones en APE 003 (`ape-1-fase-3-software-redes`)

1. **Sección `1. Datos de Identificación`:**
   * Eliminar la fila `Tipo | Actividad práctico-experimental`.
   * Corregir la inconsistencia de la fecha: `2026-10-20` es martes, mientras que `Horario` indica `Viernes 09:30 – 11:30` y las referencias `[12]`–`[15]` dicen `Consultado el 22 de octubre de 2026`. Alinear la fecha del informe al viernes correspondiente (ej. `2026-10-23`) para que sea consistente con el horario y sea igual o posterior a las fechas de consulta bibliográfica.
2. **Sección `2. Objetivo(s) de la Práctica`:**
   * Adecuar los objetivos al alcance real de la Fase 3 (software de redes, protocolos, organismos de estandarización IEEE/IETF/ISO/ITU-T, evolución de IEEE 802.3/802.11/802.15, relación con las capas de los modelos OSI y TCP/IP, brecha digital y responsabilidad ambiental/ética).
3. **Sección `3. Materiales, Reactivos, Equipos y Herramientas`:**
   * Añadir las herramientas digitales empleadas para elaborar las gráficas de líneas de tiempo (`Figuras 1, 2 y 3`), los repositorios oficiales de estándares consultados (IEEE SA, IETF RFC Editor, ITU-T, W3C) y los portales estadísticos (INEC, ARCOTEL).
4. **Sección `4. Procedimiento / Metodología Ejecutada`:**
   * Ampliar el párrafo de coordinación grupal creando la subsección **`4.1. Trabajo colaborativo, equidad e inclusión`**, detallando cómo se promovió la inclusión de los 5 miembros, el acuerdo equitativo de los 5 pasos de la guía, el apoyo mutuo en la verificación de las 20 preguntas contra fuentes oficiales y la revisión cruzada en Google Drive.
5. **Sección `5. Resultados`:**
   * En `5.4.1` (cuestionario de 20 preguntas), añadir las citas bibliográficas `[x]` faltantes en las respuestas de las preguntas `1, 3, 4, 5, 6, 7, 9, 10, 12, 15, 16 y 20`.
   * **Extraer** la subsección `5.6. Reflexión ambiental y ética` (junto con su `Tabla 7. Propuestas de responsabilidad ambiental y ética profesional`) y trasladarla a la nueva sección **`9. Reflexión crítica`**.
6. **Sección `6. Preguntas de Control`:**
   * Mantener únicamente los 3 enunciados planteados sin respuestas.
7. **Secciones `7. Conclusiones` y `8. Recomendaciones`:**
   * Mantener ambas secciones en su orden oficial y verificar que cada objetivo de la sección `2` tenga su conclusión correspondiente en `7`.
8. **CREAR Sección `9. Reflexión crítica` (Faltante en APE 003):**
   * Insertar después de `8. Recomendaciones` con dos subsecciones:
     * **`9.1. Responsabilidad ambiental, huella digital y ética profesional`:** Ubicar aquí el desarrollo de `5.6` y la `Tabla 7` (propuestas `P1` a `P6`), ampliando la explicación del impacto de la huella digital del software/protocolos y la ética de los estándares abiertos frente al *vendor lock-in* y la brecha digital rural en Ecuador.
     * **`9.2. Reflexión crítica personal por estudiante (FALTANTE CRÍTICO EN APE 003)`:** Crear los **5 subapartados individuales** (`9.2.1. Emilio Flores`, `9.2.2. Miguel Veintimilla`, `9.2.3. Royel Jima`, `9.2.4. Julian Vega`, `9.2.5. Alejandro Padilla Espinoza`). En cada uno, el estudiante debe redactar en primera persona:
       1. **Aprendizajes adquiridos** en su parte asignada de la práctica (Emilio: software de red y organismos; Miguel: evolución y líneas de tiempo IEEE 802.3/802.11/802.15; Royel: investigación de pioneros y RFCs en la práctica de estándares; Julian: estándares abiertos vs. propietarios y brecha digital en Ecuador; Alejandro: síntesis normativa e integración).
       2. **Reflexión personal ambiental y ética** vinculada al uso de estándares eficientes y reducción de la brecha digital.
9. **Sección `10. Bibliografía / Referencias` y `11. Anexos`:**
   * Numerar `10. Bibliografía / Referencias` y unificar todas las referencias IEEE al español.
   * Renumerar Anexos como `11. Anexos` (actualizando la numeración de tablas).
10. **CREAR Sección `12. Declaración de uso de IA Generativa` (Faltante en APE 003):**
    * Añadir al final del documento siguiendo la estructura obligatoria de la Sección 4 de este archivo.

---

### MÓDULO 3: Modificaciones en APE 004 (`ape-1-fase-4-osi-redes`)

1. **Sección `1. Datos de Identificación`:**
   * Eliminar la fila `Tipo | Actividad práctico-experimental`.
   * Corregir la inconsistencia entre `Fecha: 2026-10-27` (martes) y `Horario: Viernes 09:30 – 11:30`, ajustando la fecha al viernes correspondiente (ej. `2026-10-30`).
2. **Sección `2. Objetivo(s) de la Práctica`:**
   * Ajustar los objetivos para que correspondan a la Fase 4 (análisis de las 7 capas del modelo OSI, mapeo de protocolos reales y PDUs en escenarios de comunicación, diseño colaborativo de la infografía digital, comparación rigurosa entre el modelo teórico OSI y la suite práctica TCP/IP, y responsabilidad ambiental/ética).
3. **Sección `3. Materiales, Reactivos, Equipos y Herramientas`:**
   * Reemplazar la frase genérica *"Editor gráfico para diseñar la infografía digital"* por la herramienta real utilizada (**Canva**, trabajando sobre lienzo colaborativo compartido), además de Google Drive, navegadores para consulta de RFCs/IEEE y la plataforma EVA.
4. **Sección `4. Procedimiento / Metodología Ejecutada`:**
   * Añadir la subsección **`4.1. Trabajo colaborativo, equidad e inclusión`** detallando cómo se repartieron equitativamente los 5 escenarios de mapeo y las 7 capas de la infografía (considerando la carga visual y teórica de cada integrante), cómo se realizó la edición colaborativa en Canva y la retroalimentación cruzada documentada en la revisión formativa.
5. **Sección `5. Resultados`:**
   * En **`5.3. Revisión y retroalimentación`**, añadir la síntesis o evidencia de los aportes preparados para el foro de discusión del EVA mencionado en el Paso 5 de la metodología.
   * En **`5.4. Modelo OSI frente a las implementaciones reales`**, ampliar el único párrafo actual de 7 líneas a un análisis riguroso de 2 a 3 párrafos (con tabla comparativa opcional) que contraste la granularidad pedagógica y de diagnóstico (*troubleshooting*) de las 7 capas de OSI (ISO/IEC 7498-1) frente a la eficiencia práctica de las 4 capas de TCP/IP, explicando por qué TLS 1.3 y el protocolo Noise abarcan funciones de sesión, presentación y transporte/aplicación en los escenarios mapeados por el equipo.
   * **Extraer** `5.5. Reflexión ambiental` fuera de `5. Resultados` y trasladarla a la nueva sección **`9. Reflexión crítica`**.
6. **Sección `6. Preguntas de Control`:**
   * Mantener únicamente los 3 enunciados planteados sin respuestas.
7. **Sección `7. Conclusiones`:**
   * Verificar que exista una conclusión clara por cada objetivo de la sección `2`.
8. **CREAR Sección `8. Recomendaciones` (Faltante en APE 004):**
   * Insertar después de `7. Conclusiones` con al menos 4 recomendaciones prácticas (ej. uso de la metodología ascendente/descendente de capas OSI para aislar fallas en redes reales, adopción de TLS 1.3 con handshake de 1-RTT para reducir latencia y consumo energético en servidores, exclusión de tecnologías legadas como Token Ring/Token Bus en el diseño curricular/operativo, y uso de compresión HTTP/gzip en capa de presentación/aplicación).
9. **CREAR Sección `9. Reflexión crítica` (Faltante en APE 004):**
   * **`9.1. Responsabilidad ambiental, huella digital y ética profesional (Síntesis y alternativas sostenibles)`:** Ampliar sustancialmente las 5 líneas actuales de `5.5`. Desarrollar:
     1. El impacto energético de las capas superiores (transferencia innecesaria de datos sin comprimir, handshakes criptográficos repetidos, retransmisiones TCP por mala calidad en capas inferiores) y proponer **alternativas sostenibles concretas** (compresión Brotli/gzip, caché local, TLS 1.3, dimensionamiento eficiente).
     2. La **ética profesional en las capas del modelo OSI**: deber de proteger la privacidad y confidencialidad del usuario mediante cifrado extremo a extremo (TLS 1.3, Noise) en capas 6 y 7, no inspeccionar tráfico privado sin autorización legal y documentar arquitecturas con veracidad.
   * **`9.2. Reflexión crítica personal por estudiante (FALTANTE CRÍTICO EN APE 004)`:** Crear los **5 subapartados individuales** (`9.2.1. Emilio Flores`, `9.2.2. Miguel Veintimilla`, `9.2.3. Royel Jima`, `9.2.4. Julian Vega`, `9.2.5. Alejandro Padilla Espinoza`). Cada estudiante debe exponer en primera persona:
     1. **Aprendizajes y conocimientos adquiridos** al realizar su mapeo de 7 capas y diseñar sus capas en la infografía (Emilio: correo electrónico y capas 1-2 Física/Enlace; Miguel: consulta HTTPS y capa 3 Red; Royel: videollamada UDP/TCP y capa 4 Transporte; Julian: descarga de archivos y capas 5-6 Sesión/Presentación; Alejandro: mensaje de WhatsApp con protocolo Noise, capa 7 Aplicación e integración).
     2. **Reflexión personal sobre huella digital, sostenibilidad y ética profesional**.
10. **Sección `10. Bibliografía / Referencias` y `11. Anexos`:**
    * Numerar `10. Bibliografía / Referencias` y completar el formato IEEE en `[8]` (WhatsApp) y `[12]` (ITU-T X.200) añadiendo `[En línea]. Disponible en:` y fecha de consulta previa o igual a la fecha del informe.
    * Renumerar Anexos como `11. Anexos`.
11. **CREAR Sección `12. Declaración de uso de IA Generativa` (Faltante en APE 004):**
    * Añadir al final del documento siguiendo la estructura obligatoria de la Sección 4 de este archivo.

---

### MÓDULO 4: Modificaciones en APE 005 (`ape-1-fase-5-tcpip-banda-ancha`)

1. **Sección `1. Datos de Identificación`:**
   * Eliminar la fila `Tipo | Actividad práctico-experimental`.
   * Corregir la inconsistencia entre `Fecha: 2026-11-12` (jueves) y `Horario: Viernes 09:30 – 11:30` (ajustar la fecha al viernes correspondiente, ej. `2026-11-13` o `2026-11-06`).
2. **Sección `2. Objetivo(s) de la Práctica`:**
   * Corregir las viñetas 4 y 5 que están en modo imperativo (`Parte 1: Investigue...`, `Parte 2: Investigue...`) redactándolas en infinitivo formal:
     * *"Investigar la distribución y las estadísticas nacionales e internacionales de acceso a Internet de banda ancha."*
     * *"Evaluar y seleccionar opciones de acceso por banda ancha (fibra óptica, cable, DSL, celular 5G, satélite LEO y circuitos dedicados) para escenarios específicos residenciales y empresariales."*
   * Asegurar que el primer objetivo mencione explícitamente la integración de los conceptos de **Networking, hardware, software y modelos OSI/TCP-IP** tal como lo evalúa el primer criterio de la rúbrica del APE 5.
3. **Sección `3. Materiales, Reactivos, Equipos y Herramientas`:**
   * Añadir **Discord** (usado para las reuniones nocturnas de coordinación), **GitHub** (usado para el repositorio integrador de la Unidad 1) y el software empleado para generar los diagramas de arquitectura y gráficos estadísticos (`Figuras 14 a 18`).
4. **Sección `6. Preguntas de Control`:**
   * **ACCIÓN CRÍTICA:** En cumplimiento de la instrucción (*"deja la sección pero detalla que deben estar solo los enunciados planteados"*):
     1. Dejar en la sección `6. Preguntas de Control` únicamente los 3 enunciados numerados (1, 2 y 3) sin las respuestas debajo.
     2. **Para no perder puntaje en el criterio de Conocimiento Teórico de la rúbrica**, trasladar el contenido técnico valioso de esas respuestas (la tabla/análisis comparativo OSI vs. TCP/IP y la comparativa de confiabilidad TCP vs. UDP con sus referencias `[8]`, `[9]`, `[10]`, `[35]`–`[39]`) hacia la subsección **`5.1. Relación entre los modelos OSI y TCP/IP, el transporte TCP/UDP y las tecnologías de acceso`**.
     3. *[NOTA PARA EL OPERADOR HUMANO]: Si el tutor indicó que el APE 005 es el único informe donde las preguntas de control SÍ deben entregarse respondidas, indícaselo al agente antes de compilar para que conserve las respuestas en la sección 6 del APE 005 y solo deje los enunciados vacíos en APE 002, 003 y 004.*
5. **Reordenamiento Estructural de las Secciones `7, 8, 9, 10 y 11` según la Plantilla Oficial:**
   * Actualmente el APE 005 tiene: `7. Informe Integrador`, `8. Responsabilidad Ambiental y Ética`, `9. Conclusiones`, `10. Recomendaciones`, `Bibliografía`, `11. Anexos`.
   * Reordenar y renumerar exactamente así para cumplir la plantilla oficial:
     * **`7. Conclusiones`** (mover desde la antigua sección 9).
     * **`8. Recomendaciones`** (mover desde la antigua sección 10).
     * **`9. Reflexión crítica`** (sección oficial de la plantilla que agrupa los bloques reflexivos e integradores):
       * **`9.1. Informe técnico integrador y reflexión sobre los aprendizajes de la Unidad 1`** (contiene las antiguas `7.1. Productos de las cinco fases` con el enlace a GitHub y `7.2. Reflexión sobre los aprendizajes de la unidad`).
       * **`9.2. Responsabilidad ambiental, huella digital y ética profesional: síntesis y alternativas sostenibles`** (contiene la antigua `8.1` y la `Tabla 14`).
       * **`9.3. Reflexión crítica personal por estudiante`** (contiene los 5 bloques individuales `9.3.1. Emilio Flores`, `9.3.2. Miguel Veintimilla`, `9.3.3. Royel Jima`, `9.3.4. Julian Vega`, `9.3.5. Alejandro Padilla Espinoza`).
         * **Mejora obligatoria en `9.3.1` a `9.3.5`:** Añadir al inicio de cada uno de los 5 bloques individuales un párrafo breve en primera persona titulado **`Aprendizajes adquiridos en la práctica:`** donde cada integrante explique qué aprendió técnicamente en la simulación de Packet Tracer y en su investigación de banda ancha, seguido de su bloque actual de **`Responsabilidad ambiental y ética profesional:`**.
     * **`10. Bibliografía / Referencias`** (añadir el número `10.` al título).
     * **`11. Anexos`** (`11.1. Anexo A. Aportes individuales del equipo` y `11.2. Anexo B. Ajustes de la revisión e integración`).
     * **`12. Declaración de uso de IA Generativa`** (separarla de `11.2` como sección propia al final y corregir su contenido según la Sección 4 de este documento).

---

## 4. Plantilla Estandarizada para la `12. Declaración de uso de IA Generativa` (Para APE 002, 003, 004 y 005)

El agente de IA debe insertar al final de **cada uno de los cuatro informes** la sección `12. Declaración de uso de IA Generativa` corrigiendo el error de tabla fusionada que existía en el APE 005 y asegurando los **3 campos obligatorios** exigidos por el tutor: **(1) Trabajo delegado a la IA**, **(2) Modelo exacto utilizado** y **(3) Prompt(s) utilizado(s)**.

> **[ACCIÓN REQUERIDA DEL OPERADOR HUMANO ANTES DE COMPILAR]:**  
> Para cada informe (`APE 002`, `APE 003`, `APE 004` y `APE 005`), proporciona al agente de IA o reemplaza directamente en los marcadores `[INSERTAR AQUÍ...]` la versión exacta del modelo y los prompts textuales empleados en cada sesión.

### Estructura Markdown/LaTeX que debe generar el agente en cada informe:

```markdown
### 12. Declaración de uso de IA Generativa

En cumplimiento de los principios de transparencia y honestidad académica de la asignatura, se declara el uso de herramientas de Inteligencia Artificial Generativa como apoyo durante la elaboración de este informe técnico. Todo el contenido técnico, datos, evidencias y referencias fue verificado, contrastado y validado por los cinco integrantes del equipo.

**Tabla X. Registro de modelo de IA y trabajo delegado.**

| Parámetro | Detalle |
| :--- | :--- |
| **Entorno / Herramienta** | el Gentleman (entorno Pi) / `[ACCIÓN OPERADOR: confirmar o añadir otra herramienta si aplica]` |
| **Modelo exacto utilizado** | `[ACCIÓN OPERADOR: indicar versión exacta, ej. Claude 3.5 Sonnet / Claude 3.7 Sonnet / Claude Opus 4 de Anthropic]` |
| **Trabajo delegado a la IA** | `[ACCIÓN OPERADOR: detallar las tareas delegadas en esta APE específica, ej. revisión de redacción técnica, verificación de formato de referencias IEEE, estructuración de tablas comparativas y maquetación del documento]` |

**Tabla Y. Prompts literales utilizados durante la práctica.**

| Nro. | Tarea / Sección asistida | Prompt textual utilizado |
| :--- | :--- | :--- |
| 1 | `[ACCIÓN OPERADOR: Sección/Tarea 1]` | `"[ACCIÓN OPERADOR: Pegar aquí el prompt textual 1 empleado con el agente]"` |
| 2 | `[ACCIÓN OPERADOR: Sección/Tarea 2]` | `"[ACCIÓN OPERADOR: Pegar aquí el prompt textual 2 empleado con el agente]"` |
```

---

## 5. Checklist de Verificación Final para el Agente de IA

Antes de dar por finalizada la edición de los 4 archivos fuente y compilar los PDFs, el agente debe comprobar que se cumplan los siguientes 10 puntos de control:

- [ ] **1. Títulos y orden de plantilla:** Los 4 informes tienen exactamente el orden: `1. Datos de Identificación`, `2. Objetivo(s)`, `3. Materiales, Reactivos, Equipos y Herramientas`, `4. Procedimiento / Metodología Ejecutada`, `5. Resultados`, `6. Preguntas de Control`, `7. Conclusiones`, `8. Recomendaciones`, `9. Reflexión crítica`, `10. Bibliografía / Referencias`, `11. Anexos` y `12. Declaración de uso de IA Generativa`.
- [ ] **2. Sin fila extra en portada:** Se eliminó la fila `Tipo | Actividad práctico-experimental` de la tabla de la sección `1` en los 4 informes.
- [ ] **3. Coherencia de fechas:** En los 4 informes, la fecha de la práctica en la sección `1` coincide con el día viernes declarado en `Horario` y ninguna cita bibliográfica tiene fecha de consulta posterior a la fecha del informe.
- [ ] **4. Trabajo colaborativo e inclusión explícito:** Los 4 informes cuentan en la sección `4` con el subapartado que documenta la distribución equitativa, la inclusión de capacidades/horarios diversos y la revisión cruzada entre pares.
- [ ] **5. Preguntas de control solo con enunciados:** En `6. Preguntas de Control` aparecen únicamente los enunciados planteados (previa confirmación del operador humano para el caso del APE 005).
- [ ] **6. Sección `8. Recomendaciones` presente en todos:** Se añadió en APE 002 y APE 004, y se mantuvo en la posición `8` en APE 003 y APE 005.
- [ ] **7. Sección `9. Reflexión crítica` completa:** Existe en los 4 informes e incluye tanto la reflexión profunda de responsabilidad ambiental/ética con **propuestas sostenibles concretas** como las **5 reflexiones personales individuales** identificadas con el nombre de cada uno de los 5 estudiantes.
- [ ] **8. Voz personal en las 5 reflexiones:** Cada uno de los 5 integrantes (*Emilio Flores, Miguel Veintimilla, Royel Jima, Julian Vega y Alejandro Padilla Espinoza*) expresa en primera persona qué aprendió en la práctica y su compromiso ético/ambiental en APE 002, APE 003, APE 004 y APE 005.
- [ ] **9. Bibliografía IEEE unificada:** Todas las referencias están numeradas en la sección `10`, siguen formato IEEE uniforme en español y todas las preguntas/afirmaciones técnicas tienen su cita `[x]` correspondiente.
- [ ] **10. Declaración de IA en los 4 informes:** Presente en APE 002, 003, 004 y 005 con tablas separadas y válidas que especifican trabajo delegado, modelo exacto y prompts textuales completados por el operador.