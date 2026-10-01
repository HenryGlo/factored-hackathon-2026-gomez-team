# Changelog

Cambios notables del proyecto. Formato [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
[SemVer](https://semver.org/lang/es/). `v1.0.0` será la versión que se entrega; hasta entonces, `v0.x`. Cada versión es un
tag anotado sobre el merge commit del hito (ver [CONTRIBUTING.md](CONTRIBUTING.md#versiones)).

## [Unreleased]

### Added
- Auditoría de los campos que genera el LLM: un test por campo prueba la guarda R5 y el filtro de promesas; la guarda
  cubre también las preguntas abiertas del handoff. Hallazgo documentado en `docs/security.md`.
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

[Unreleased]: https://github.com/HenryGlo/factored-hackathon-2026-gomez-team/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/HenryGlo/factored-hackathon-2026-gomez-team/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/HenryGlo/factored-hackathon-2026-gomez-team/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/HenryGlo/factored-hackathon-2026-gomez-team/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/HenryGlo/factored-hackathon-2026-gomez-team/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/HenryGlo/factored-hackathon-2026-gomez-team/releases/tag/v0.1.0
