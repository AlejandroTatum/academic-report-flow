# Auditoría de Cierre — Versiones NUEVO (APE 002 a APE 005)

## Estado general
Las correcciones de fondo de la auditoría previa fueron aplicadas correctamente en los cuatro informes (roles, limpieza de archivos en anexos, formato IEEE en español, tiempos verbales en la declaración de IA, concisión general y ampliación de evidencias). Solo restan ajustes puntuales de maquetación, jerarquía de títulos y consistencia menor antes de la entrega definitiva.

---

## 1. Decisión transversal obligatoria (APE 002 a APE 005)

- [ ] **Verificar requisito de prompts en la Declaración de IA:** Confirmar si la plantilla/rúbrica oficial exige *prompts literales* o permite *síntesis de instrucciones* (formato aplicado en las versiones NUEVO de APE 004 y APE 005).
  - Si permite síntesis: asegurar que **los cuatro APE** usen exactamente el mismo criterio (síntesis).
  - Si exige prompts literales: restaurar los prompts textuales conservando solo el acortamiento de rutas de archivo, pero manteniendo uniformidad en los cuatro documentos.

---

## 2. Correcciones por documento

### APE 002 — Hardware de Redes
- [ ] **Revisar formato de numeración en Bibliografía:** Verificar visualmente en el PDF que las referencias `13`, `14` y `15` aparezcan entre corchetes (`[13]`, `[14]`, `[15]`) igual que `[12]` y `[19]`–`[21]`.
- [ ] **Verificar Declaración de IA:** Confirmar que figure `El Gentleman (entorno Pi)` con mayúscula inicial, verbos en pasado para la revisión de reflexiones (*«fueron revisados, ajustados y aprobados»*) y el mismo criterio de tabla de prompts que los demás APE.

### APE 003 — Software y Estándares de Redes
- [ ] **Pulir redacción en `Trabajo delegado a la IA`:** Evitar la repetición cercana de *«de cada integrante»* / *«por cada integrante»* y el doble conector *«; y, en la...»*.
  - *Sugerencia:* «...ayudar a preparar borradores de las reflexiones personales a partir de los aportes individuales, los cuales fueron revisados, ajustados y aprobados por cada integrante; finalmente, recortar el texto y generar los diagramas de las Figuras 1, 2 y 6 con base en el contenido del equipo.»
- [ ] **Verificar consistencia de tabla de prompts:** Confirmar que coincida con el criterio adoptado en APE 004 y APE 005.

### APE 004 — Modelo OSI e Infografía
- [ ] **[CRÍTICO - Maquetación] Reparar quiebre de la `Tabla 12` (Registro de IA):** La fila `Trabajo delegado a la IA` se desprendió de la tabla tras el salto de página y renderizó `Detalle` como encabezado suelto. Ajustar el entorno de tabla o insertar un salto de página previo para que la `Tabla 12` se muestre íntegra y con bordes consistentes.
- [ ] **Alinear narrativa sobre el aporte de Emilio Flores:** Unificar la redacción de la Sección `5.3` (*«se completó la parte de Emilio con el escenario del correo»*) y la `Tabla 10` (*«completados con el correo»*) con la formulación de la `Tabla 12` (*«se complementó e integró el escenario del correo con base en el aporte de Emilio Flores»*).
- [ ] **[Opcional - Precisión técnica en `Figura 2`]:** Evaluar cambiar la PDU de la Capa 4 de `Segmento` a `Segmento / Datagrama` para reflejar tanto TCP como UDP, ambos mencionados en el ejemplo de esa fila.

### APE 005 — Práctica TCP/IP, Banda Ancha e Informe Integrador
- [ ] **[CRÍTICO - Estructura] Corregir niveles de encabezado en Secciones 11 y 12:**
  - `11. Anexos` y `12. Declaración de uso de IA Generativa` deben tener el mismo nivel de sección principal que `9. Reflexión crítica` (`#` / `\section`).
  - `11.1. Anexo A` y `11.2. Anexo B` deben quedar ambos como subsecciones (`##` / `\subsection`).
  - Recompilar y revisar la Tabla de Contenidos para confirmar la jerarquía.
- [ ] **Revisar fila final de `Tabla 13` (Anexo B):** Verificar que la fila de `Alejandro Padilla Espinoza` (`Informe integrado (DOCX/Markdown)`) no aparezca dividida en dos filas separadas por un borde horizontal.
- [ ] **Validar enlace/carpeta de GitHub (`Tabla 10`):** Confirmar que en el repositorio exista exactamente la carpeta `ape-1-fase-5-tcpip-redes` dentro de `unidad-1` con el PDF final.
- [ ] **Revisar texto del paso 3c (`Figura 18`):** Asegurar que la explicación aclare si la cabecera `Host` está ausente en la PDU del simulador o simplemente queda fuera del campo visible por la barra de desplazamiento del panel `HTTP REQUEST`.

---

## 3. Verificación final antes de subir
- [ ] Revisar visualmente página por página los 4 PDF compilados (sin tablas partidas, sin títulos huérfanos y con índices actualizados).
- [ ] Confirmar que los 4 informes usen el mismo formato en la Declaración de IA y en las tablas de aportes individuales.