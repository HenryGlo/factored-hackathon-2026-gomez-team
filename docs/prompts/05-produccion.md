# Prompt 05 — Listo para producción: API de Claude, CI, protección y despliegue

Eres el ingeniero responsable de llevar a producción el sistema de disputas del Factored
AI & Data Hackathon 2026. Antes de empezar lee README.md, docs/ (architecture,
api-contract, llm-data, evaluation, decisions/, open-questions) y el último reporte en
eval/results/. Revisa el estado real del código y de las ramas.

Requisitos previos (verifícalos y detente si no se cumplen):
- La fase 6 del prompt 03 está con commit (reporte de las tres variantes incluido).
- La rama del frontend (feat/frontend) está fusionada o lista para fusionarse; si hay
  conflictos con main, muéstramelos antes de resolverlos.

Trabaja por fases y DETENTE en cada punto de control. Si algo contradice los documentos,
pregúntame antes de elegir.

---

## Fase 1 — Cliente de la API de Claude

- `backend/app/llm/anthropic_api.py`: `AnthropicAPIClient` que implementa la misma
  interfaz `LLMClient.complete_json(...)` con el SDK oficial `anthropic` (asíncrono).
- Salida estructurada con `output_config.format` (json_schema) o `client.messages.parse()`
  con los modelos Pydantic existentes. Antes de escribirlo, consulta la documentación
  actual en https://platform.claude.com/docs/en/build-with-claude/structured-outputs y
  ajústate a lo que diga. Ten en cuenta: el casing de los enums no está garantizado
  (compara sin distinguir mayúsculas) y minLength/maximum/regex no se aplican en la API
  (Pydantic sigue validando después).
- IDs de modelo FIJOS por nodo en backend/config/llm.toml (usa los IDs reales medidos en
  las trazas de claude -p), nada de alias en producción.
- Prompt caching del prompt de sistema de cada nodo.
- Timeout y max_retries configurables; mapea los errores del SDK a los errores tipados
  existentes (timeout, unavailable, invalid_output).
- Costo por llamada calculado desde `usage` con una tabla de precios versionada en
  config (documenta la fuente y la fecha de los precios).
- `ANTHROPIC_API_KEY` solo por entorno; actualiza .env.example.
- Tests con un transporte HTTP simulado: éxito, esquema inválido, timeout, 429/529 y
  reintento.
- Comparación: corre el split dev con la variante sistema usando
  LLM_PROVIDER=anthropic_api (1 repetición) y compárala con la de claude -p: resolución,
  fallos, latencia (ahora sí representativa de producción) y costo. Si algún caso cambia
  de resultado, analízalo antes de seguir.
Punto de control 1: tabla claude -p vs API y diferencias.

## Fase 2 — Protección antes de exponer nada a internet

Con una URL pública y un LLM de pago detrás, el abuso es un riesgo de costo y de
seguridad. Implementa:
- Rate limiting por IP y por sesión en todos los endpoints (p. ej. slowapi; si usas
  Redis, que sea opcional y con fallback en memoria para local). Límites más estrictos
  en /api/auth/login y en POST de turnos. Respuesta 429 con Retry-After.
- Presupuesto de LLM: tope diario global y por sesión de llamadas y de costo
  (configurables). Si se supera, el sistema sigue funcionando en modo degradado
  (plantillas y baseline) y lo registra; nunca falla en silencio.
- Tope de largo del mensaje (2.000 caracteres) en backend.
- Cabeceras de seguridad (HSTS en producción, X-Content-Type-Options, Referrer-Policy,
  CSP básica para el frontend), CORS cerrado al dominio del frontend.
- Tests de cada límite.
Documenta en docs/security.md qué cubre la aplicación y qué debe cubrir la plataforma de
hosting o un CDN (protección DDoS de red).

## Fase 3 — Logging estructurado y observabilidad mínima

- Logs en JSON con request_id, session_id hasheado, conversation_id, turn_id, trace_id,
  ruta, estado, latencia y modelo/costo cuando hay LLM. Nunca contraseñas, tokens,
  cookies ni textos completos del cliente en los logs (las trazas en BD ya los guardan
  con su propio control de acceso).
- El request_id viaja en una cabecera de respuesta para poder cruzar frontend, logs y
  trazas.
- `GET /api/health` (vida) y `GET /api/ready` (BD y configuración del LLM).
- Métricas básicas expuestas para el panel admin futuro: latencia p50/p95 por endpoint,
  errores, llamadas y costo de LLM por día (pueden salir de app.traces con una vista SQL).
Punto de control 3: un recorrido completo y el extracto de logs que genera.

## Fase 4 — CI/CD en GitHub Actions

Workflow `ci.yml` en cada PR y push a main:
1. Lint y tipos (ruff, mypy o equivalente en backend; eslint y tsc en frontend).
2. Tests del backend y del pipeline contra un servicio PostgreSQL 17 del runner
   (migraciones + datos de fixture; NUNCA el dataset real).
3. Build del frontend.
4. Harness sobre el split dev con LLM_PROVIDER=fake y casos que no dependan del dataset
   real (usa los fixtures FXT- o un subconjunto sintético documentado). Puertas de
   calidad: 0 resultados inseguros y ninguna regresión en la tasa de aprobación respecto
   del último resultado guardado en main. El reporte se sube como artefacto del workflow.

Workflow `eval-llm.yml`, solo manual (workflow_dispatch), con el secreto
ANTHROPIC_API_KEY: corre el split dev con la variante sistema y la API real, 1
repetición, y sube el reporte. Nunca corre automáticamente en PRs (costo y secretos).

Nada de datos del dataset, secretos ni .env en el repositorio ni en los logs de CI.

## Fase 5 — Despliegue

Antes de desplegar, propónme DOS opciones de hosting con costo estimado y tiempo de
puesta en marcha para: backend FastAPI, PostgreSQL gestionado y frontend estático
(por ejemplo, Render o Railway como opción rápida, y AWS App Runner + RDS como opción más
cercana a un banco real). Espera mi elección.

Después de mi elección:
- Dockerfile del backend (multi-stage, usuario no root) y build del frontend estático.
- Base de datos de producción cargada con el subconjunto demo (`--customers-sample` con la
  regla versionada) y los usuarios demo; migraciones automáticas en el despliegue.
- Variables y secretos en la plataforma: DATABASE_URL (rol de la app, no superusuario),
  ANTHROPIC_API_KEY, DEMO_PASSWORD, límites y presupuesto de LLM.
- Modo demo para los jueces: la pantalla de login muestra un aviso "entorno de
  demostración con datos ficticios", lista los usuarios demo con el escenario que
  representa cada uno (cliente con cargo claro, con cargos parecidos, de riesgo alto,
  analista) y la contraseña de demo. Configurable con DEMO_MODE=true.
- Despliegue automático desde main solo si la CI pasa (o manual, según la plataforma),
  documentado.
- Prueba de humo en la URL pública: login, un recorrido de cargo claro, uno ambiguo, uno
  de riesgo alto y la consola del analista; y una prueba de que el rate limiting responde.
Punto de control 5: URL pública funcionando y resultado de la prueba de humo.

## Documentación
- docs/deployment.md: arquitectura desplegada, cómo desplegar, variables, cómo revertir.
- Actualiza README.md (cómo probar la app desplegada, usuarios demo), architecture.md
  (cliente de API y despliegue), ADR nuevo para el hosting elegido, y open-questions.md.

## Reglas generales
- No inventes resultados; todo número sale de una ejecución.
- No subas secretos, datos del dataset ni artefactos grandes.
- Una rama por fase (feat/api-client, feat/hardening, feat/observability, feat/ci,
  feat/deploy) o una sola feat/produccion con commits por fase; en ambos casos muéstrame
  el diff y espera mi OK antes de cada commit. No hagas push sin mi OK (para la CI y el
  despliegue sí hará falta push; pídemelo explícitamente).
