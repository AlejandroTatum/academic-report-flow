# Portal de documentación

La documentación del repositorio se publica como un sitio web de [Quarto](https://quarto.org) en
[GitHub Pages](https://alejandrotatum.github.io/academic-report-flow/). El workflow `.github/workflows/docs.yml`
renderiza el portal en cada pull request y lo publica en cada push a `main`.

## Cómo leerlo

| Dónde | Cómo |
|---|---|
| Mientras escribes | `quarto preview` desde la raíz del repo: sirve el sitio en `localhost` y recarga al guardar |
| Build completo | `quarto render`: escribe el sitio en `_site/` (ignorado por git); abre `_site/index.html` |

Se necesita Quarto 1.11.9 o compatible. No hace falta el entorno Python ni LaTeX para renderizar el portal.

## Qué es una página

`_quarto.yml` lista en `render:` los archivos que se vuelven páginas (lista blanca) y define la barra lateral.
Las páginas escritas a mano viven en `docs/portal/*.qmd`; un `.qmd` nuevo en esa carpeta se renderiza solo, pero hay que
añadirlo a la barra lateral. Se reutilizan tal cual `docs/skill-style-guide.md` y las dos especificaciones de
`openspec/specs/`.

No se publican: `skills/**/profiles/` (perfiles de cursos reales), `outputs/`, `openspec/changes/archive/**`, `odd/`
ni los diagramas históricos de `docs/diagrams/`.

## Secciones

La barra lateral sigue el orden de los demás portales (gymKad, prácticas preprofesionales UNL). Las secciones sin
contenido se omiten.

| Sección | Páginas |
|---|---|
| Contexto | `docs/portal/contexto.qmd`: problema que resuelve, capacidades y qué pipeline usar |
| Especificación | las dos especificaciones de `openspec/specs/` y las decisiones del usuario del flujo documental |
| Modelado | `docs/portal/flujo.qmd`: el diagrama del flujo vigente |
| Arquitectura | pipelines, catálogo de herramientas, skills y la guía de estilo de skills |
| Calidad | cómo se organizan y ejecutan las pruebas |
| Operación | instalación, builds de informes y portadas, sincronización de skills |
| Equipo | propuesta de mejoras de la skill, cómo contribuir y esta página |

## Diagramas

Las páginas dibujan diagramas con fences ```` ```mermaid ```` simples. Quarto solo dibuja celdas `{mermaid}`, así que la
extensión `mermaid-fence` (`_extensions/mermaid-fence/`, registrada en `filters:` de `_quarto.yml`) convierte cada fence
en el marcado que espera el runtime de diagramas de Quarto. Funciona sin red: usa los archivos de mermaid que trae la
instalación de Quarto. Los demás fences (`bash`, `yaml`) no se tocan.

La fuente del diagrama del flujo es `docs/diagrams/report-flow.es.mmd`; `docs/portal/flujo.qmd` contiene una copia
embebida, así que al cambiar el flujo hay que actualizar ambos.
