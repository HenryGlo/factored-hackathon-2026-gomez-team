# Entrega

## Requisitos oficiales

**[Oficial]** Del kickoff (sección *Submission Details*): enviar todo a **hackathon.admin@factored.ai**. "Submit your tool no matter what."

- [ ] **Repositorio público en GitHub** con el nombre `factored-hackathon-2026-gomez-team` (creado como privado; hacerlo público antes de entregar).
- [ ] **Enlace a la app desplegada.** Pendiente: plataforma (P-06).
- [ ] **Presentación de 4–6 diapositivas** con detalles de la herramienta.
- [ ] **Video pitch corto y obligatorio** que muestre la solución funcionando y explique las decisiones de arquitectura. Pendiente: duración máxima y formato (P-02).

**[Oficial]** Fechas conocidas: kickoff el 25 de septiembre; el reto se describe como un sprint de 10 días. Pendiente: fecha y hora límite exacta y zona horaria (P-01).

## Criterios de evaluación

**[Oficial]** Del kickoff: primero, que la solución funcione. Luego:

| Criterio | Dónde se demuestra |
|---|---|
| Justificación y documentación del proyecto | [README](../README.md), [docs/](README.md), ADR |
| AI Engineering: backend, frontend, despliegue | [backend/](../backend/README.md), [frontend/](../frontend/README.md), [infra/](../infra/README.md) |
| Data Analytics: calidad y hallazgos relevantes | [analytics/](../analytics/README.md), [data/quality-report.md](data/quality-report.md) |
| Data Engineering: extracción y transformación | [data_pipeline/](../data_pipeline/README.md) |
| Machine Learning: selección, optimización, implementación y seguimiento | [ml/](../ml/README.md), [docs/ml/](ml/README.md), [evaluation.md](evaluation.md) |

## Checklist del repositorio

- [ ] README raíz con instrucciones de ejecución reproducibles (hoy: Pendiente).
- [ ] Sin datos del dataset, sin `.env`, sin credenciales (el diccionario trae credenciales del bucket). Revisar historial de git antes de hacer público.
- [ ] Declaración de qué inputs son sintéticos o generados por el equipo ([data/usage.md](data/usage.md)).
- [ ] Resultados de evaluación con n y denominadores, incluidas fallas ([evaluation.md](evaluation.md)).
- [ ] Limitaciones honestas: capacidad, datos, idioma, trabajo de despliegue pendiente, riesgos.
- [ ] Mediciones offline, simulaciones y ahorros proyectados etiquetados por separado.

## Checklist de la demo (app desplegada)

- [ ] Camino de resolución en español: "Tengo un cobro de $120 que no reconozco".
- [ ] Camino ambiguo: aclaración y abstención.
- [ ] Camino de escalamiento con handoff visible en la consola.
- [ ] Al menos un camino completo en portugués.
- [ ] Consola del banco mostrando reclamos, handoffs y trazas.

## Slides (4–6)

Borrador del contenido (en inglés, con la fuente de cada número): [presentation/slides.md](presentation/slides.md). Guion del video: [presentation/video-script.md](presentation/video-script.md).

**[Propuesta]** Estructura:

1. Problema y evidencia de datos (con limitaciones).
2. Solución y arquitectura: LLM vs ML vs código determinista.
3. Control de automatización: estados, políticas, confirmación, handoff.
4. Datos y ML: ETL, ranker vs baseline, riesgo calibrado.
5. Evaluación: resultados con n, ablaciones, fallas.
6. Camino a producción y lo que falta.

## Video

**[Propuesta]** Demo de los tres caminos (uno en portugués) + recorrido por la arquitectura y los resultados. Pendiente: duración (P-02).
