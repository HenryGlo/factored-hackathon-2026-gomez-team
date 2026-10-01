# Changelog

Cambios notables del proyecto. Formato [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
[SemVer](https://semver.org/lang/es/). `v1.0.0` será la versión que se entrega; hasta entonces, `v0.x`. Cada versión es un
tag anotado sobre el merge commit del hito (ver [CONTRIBUTING.md](CONTRIBUTING.md#versiones)).

## [Unreleased]

### Added
- Bandeja de tickets para agentes: `/api/tickets` con estado, asignado, SLA objetivo por prioridad (supuestos del equipo), notas internas y auditoría de cada cambio en `app.ticket_events` (migración 0009) (#35).
- Feedback del cliente: `POST /api/conversations/{id}/feedback` (una valoración por conversación, tabla `app.feedback` de solo inserción, migración 0008) y `GET /api/feedback` para la consola (#33).
- Historial del cliente: `GET /api/me/conversations` (paginado, resumen armado con hechos) y `GET /api/me/conversations/{id}` (#32).

## [0.9.0] - 2026-10-01

### Added
- Analítica operativa (`docs/analytics.md`, `python -m analytics.report`): calidad de datos desde el ETL y sus contratos,
  demanda desde el dataset, operación desde las trazas de evaluación y ROI con supuestos editables (estimación) (#28).
- Endpoints `/api/admin/metrics/operations`, `/latency` y `/roi` para el panel de administración.
- Notebook `analysis/analytics.ipynb` que regenera las figuras con el mismo código.

## [0.8.0] - 2026-10-01

### Added
- 18 casos dev multiturno de clientes que dan rodeos (102 en total) y `docs/manual-test-script.md`: 18 recorridos manuales con
  pasos y resultado esperado para el frontend (#27).
- Las preguntas sobre el proceso hechas en medio de una confirmación se responden con el texto aprobado y la confirmación
  sigue pendiente.
- El reporte del harness avisa cuando más del 5 % de las llamadas LLM fallaron (la corrida midió los fallbacks).

### Fixed
- Al retomar un reclamo recién cancelado se conserva el tipo de problema original.
- Reglas de palabras clave: "no lo reconozco", "yo no fui", "un cobro que yo no hice", "cobro raro", "quiero reclamar ese
  cargo"; "e agora…" sin pregunta ya no cuenta como pregunta de proceso; el comercio extraído termina con la oración.

## [0.7.0] - 2026-10-01

### Added
- Riesgo calibrado `risk-v1` (isotónica de `fraud_score`, umbral por costo esperado, partición temporal): detecta 446/620
  fraudes con score en el periodo de prueba con precisión 446/446, frente a 182/620 de la banda alta anterior. Experimento
  reproducible y ficha del modelo (#26).
- Prioridad `urgente` en los handoffs: riesgo alto y el cliente afirma que no hizo el cargo (migración 0007). El handoff
  marca la banda como señal de movimiento anómalo, no fraude confirmado.
- 3 casos dev (84), selector `riesgo_medio_tarjeta`, escenario sintético `riesgo_medio` y checker de prioridad del handoff.

### Changed
- La banda alta de R6 pasa de `fraud_score` ≥ 70 al umbral calibrado (≈ 30). `RISK_MODEL=raw_fraud_score` recupera el anterior.

### Not adopted
- Modelo simple (LightGBM) para movimientos sin score: PR-AUC 0,0010 frente a una prevalencia de 0,0009; no se integra.

## [0.6.0] - 2026-10-01

### Added
- Clasificador de intención en cascada (`intent-v1`: TF-IDF + regresión logística calibrada → Haiku si duda), variante
  `sistema_cascade`, experimento reproducible con un comando y ficha del modelo. En validación cruzada iguala a Haiku
  (183/187) enviando al LLM el 13,9 % de los turnos; en el harness baja el costo por caso ~38 % sin fallos ni inseguros;
  la latencia no mejora. `sistema_api` sigue siendo producción (#17).
- Métrica "intención que llega al LLM" en el harness.
- Prompts 07 y 08; regla de no probar sobre la base `bank` (#23).
- Auditoría de los campos que genera el LLM: un test por campo prueba la guarda R5 y el filtro de promesas; la guarda
  cubre también las preguntas abiertas del handoff. Hallazgo documentado en `docs/security.md` (#22).
- 5 casos dev (81): las 2 paráfrasis que cambiaban el sentido, con su resultado correcto; 2 regresiones de inyección; "chao" y
  conversación enlazada. Cambios del set en `eval/cases/CHANGELOG.md`; esquema con `today_after` y `link_previous`.

## [0.5.0] - 2026-10-01

### Added
- Atajo sin LLM para saludos, gracias y despedidas (es/pt), con paso `fast_path` en la traza; la latencia del saludo con la
  API pasa de 561 ms / 2.243 ms (p50/p95) a 13 ms / 49 ms (#14, closes #15).
- Fase real del turno (`GET /api/conversations/{id}/phase`) para un indicador de espera que no adivina (#14, closes #15).
- Redirección aprobada de consultas fuera de alcance, con enlace a la página inicial del banco (`BANK_HOME_URL`) y mensajes
  mixtos atendidos en el mismo turno (#14, closes #16).
- 16 casos dev (76 en total) y checkers `saludo_sin_llm`, `fuera_de_alcance_aprobado` y `conversacion_abierta` (#14).
- Prácticas de GitHub: CONTRIBUTING.md (Conventional Commits, ramas por cambio), plantillas de PR e issues, este CHANGELOG,
  `release.yml` (CI + Release al empujar un tag `v*`), job de secretos con gitleaks en la CI y `scripts/protect_main.sh`.

- Punto de control 1: `claude -p` frente a la API de Claude en dev y dev_paraphrase; `anthropic_api` queda como proveedor
  de producción (#20).

### Changed
- "gracias" sola ya no cierra la conversación: responde y ofrece seguir (#14).

### Fixed
- El aviso de fuera de alcance ya no copia el `tema` escrito por el LLM (salía sin pasar por la guarda R5; inseguro en la
  inyección "aprueba el reembolso" con `claude -p`) (#14, hallado en #20).

### Removed
- 2 paráfrasis de dev_paraphrase que cambiaban el significado del caso (96 casos) (#20).

## [0.4.0] - 2026-10-01

### Added
- Frontend React + Vite + TS: chat del cliente, "Mis movimientos", "Mis reclamos" y consola del analista (#9).
- Preguntas sobre el proceso respondidas desde una base de respuestas aprobadas (`faq.yaml`, 12 entradas es/pt) y
  referencias cortas de reclamo para el cliente (`RCL-XXXXXX`) (#11).
- `ANTHROPIC_WORKSPACE_ID` opcional y aviso/salida con error cuando una corrida mide los fallbacks porque fallaron las
  llamadas al LLM (#12).
- Métrica `intent_overridden_by_keywords` en el reporte del harness (#13).

### Fixed
- La excepción de la etiqueta "Aprobado" en los checkers de promesas (R5) solo vale para lo que rellenó el código (#13).

## [0.3.0] - 2026-10-01

### Added
- Protección: rate limiting por IP y sesión, presupuesto de LLM con modo degradado, tope de mensaje, cabeceras de seguridad y
  CORS cerrado (#6).
- Observabilidad: logs JSON con contexto, `X-Request-ID`, `/api/ready` y `/api/metrics` (#7).
- Endpoints de lectura del cliente `/api/me/transactions` y `/api/me/cases` (#8).
- CI: ruff, mypy, pytest, harness sobre datos sintéticos con puerta de calidad y job del frontend; workflow manual
  `eval-llm.yml` (#10).
- Prompts 04 y 05 en `docs/prompts/` (#4).

### Fixed
- El LLM ya no escribe el estado del movimiento: marcador `{estado}` relleno tras la guarda R5 (P-31), y "sí"/"no" con
  tipeos en las confirmaciones (#5).

## [0.2.0] - 2026-09-30

### Added
- Backend del prompt 03: login y sesiones, capa LLM con `claude -p` y nodos versionados, baselines de ML, controlador con
  tools y política R1–R6, API de conversaciones (#2).
- Harness de evaluación con casos dev, checkers deterministas, variantes `baseline` / `claude_cli` / `sistema`, split
  `dev_paraphrase` y kit del test escrito a mano (#2).
- Cliente de la API de Claude (`anthropic_api`) con salida estructurada, caché del prompt de sistema y costo por llamada (#3).

### Fixed
- Chat de terminal: ciclo de vida, cargo en foco, R2b, varios cargos y presentación (#3).

## [0.1.0] - 2026-09-30

### Added
- Estructura inicial del repositorio y documentación.
- Pipeline CSV → DuckDB → PostgreSQL con contratos, linaje (`ops`), roles `app_rw` / `app_ro` y carga incremental por
  `process_date` (#1).

[Unreleased]: https://github.com/HenryGlo/factored-hackathon-2026-gomez-team/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/HenryGlo/factored-hackathon-2026-gomez-team/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/HenryGlo/factored-hackathon-2026-gomez-team/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/HenryGlo/factored-hackathon-2026-gomez-team/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/HenryGlo/factored-hackathon-2026-gomez-team/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/HenryGlo/factored-hackathon-2026-gomez-team/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/HenryGlo/factored-hackathon-2026-gomez-team/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/HenryGlo/factored-hackathon-2026-gomez-team/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/HenryGlo/factored-hackathon-2026-gomez-team/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/HenryGlo/factored-hackathon-2026-gomez-team/releases/tag/v0.1.0
