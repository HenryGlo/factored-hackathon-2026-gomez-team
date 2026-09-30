# Prompt 03 — Backend, capa LLM y harness de evaluación

Eres el ingeniero responsable de construir el backend del sistema de disputas del
Factored AI & Data Hackathon 2026 sobre la base PostgreSQL que ya existe, y el harness
que lo mide. Antes de empezar lee README.md, docs/ (architecture, conversation-flow,
api-contract, tools-contract, policies, handoff-schema, evaluation, decisions/,
data/postgres.md, data/postgres-schema.md) y revisa el código real de backend/,
data_pipeline/ y eval/.

Estado de partida (verificado en main f103fac):
- Existe: pipeline CSV → DuckDB → PostgreSQL 17, esquemas ref, app y ops, modelos
  SQLAlchemy, migraciones 0001 y 0002, roles bank_app y bank_console, app.sessions,
  ref.demo_customers y `--customers-sample`.
- No existe: API, controlador, tools, capa LLM, interfaces de ML, harness ni casos.

Si algo de este prompt contradice los documentos, pregúntame antes de elegir. Trabaja por
fases y DETENTE en cada punto de control para mostrarme el resultado.

Decisiones ya tomadas:
- El rol humano de la consola se llama `analyst` (no `agent`, para no confundirlo con el
  agente de IA en código y trazas). Renómbralo en docs, en el CHECK de app.sessions
  (migración nueva) y en P-12.
- Autenticación con usuario y contraseña (ver fase 1). Reemplaza la sesión de prueba sin
  contraseña de api-contract.md; actualiza el contrato.

---

## Fase 1 — Autenticación y sesión

Requisito del reto: la identidad sale de una sesión confiable; un número de cliente o
documento por sí solo no prueba identidad.

- app.users (migración nueva): username único, hash de contraseña con argon2, rol
  (`customer` | `analyst`), customer_id (obligatorio solo para customer), activo,
  timestamps.
- `scripts/seed_demo_users.py`: crea usuarios para los clientes de ref.demo_customers que
  cubren los escenarios (elegidos con SQL documentado) y 2 analistas. La contraseña se
  lee de `DEMO_PASSWORD` en .env; nunca en el repo ni en docs. Idempotente.
- Endpoints:
  - `POST /api/auth/login` → crea fila en app.sessions con expiración por inactividad
    (30 min, configurable) y devuelve el token en cookie httpOnly, SameSite=Lax, Secure
    en producción.
  - `POST /api/auth/logout` invalida la sesión.
  - `GET /api/auth/me` → rol y display_name.
- CSRF para peticiones que cambian estado (cookie + cabecera con doble token).
- Límite de intentos fallidos por usuario e IP; eventos de login registrados.
- Dependencia de FastAPI que resuelve la sesión: el customer_id SIEMPRE sale de ahí.
  Ningún endpoint lo acepta en el cuerpo ni en la URL.
- Los endpoints de consola exigen rol analyst y leen con el usuario de solo lectura.
- Tests: sin sesión, rol incorrecto, sesión expirada, sesión revocada, fuerza bruta.

## Fase 2 — Capa LLM con `claude -p`

`backend/app/llm/`:
- `client.py`: interfaz `LLMClient.complete_json(node, system_prompt, user_content,
  schema, model) -> LLMResult` con data (validada con Pydantic), model, prompt_version,
  latency_ms, cost_usd y raw.
- `claude_cli.py`: `ClaudeCLIClient` con `asyncio.create_subprocess_exec` (lista de
  argumentos, NUNCA shell=True), equivalente a:
    claude -p --model <haiku|sonnet> --output-format json --json-schema '<schema>'
      --system-prompt-file prompts/<nodo>.md --tools "" --disallowedTools "mcp__*"
      --no-session-persistence --max-turns 3
  El contenido del usuario va por stdin. El directorio de trabajo es una carpeta temporal
  vacía (para no cargar CLAUDE.md del repo). NO uses --bare: exige API key y no usa la
  suscripción. Lee `structured_output`, registra total_cost_usd y duration_ms.
  Timeout configurable (60 s), un reintento y luego error tipado para el fallback seguro.
  Antes de escribirlo, ejecuta `claude --version` y
  `claude -p "di hola" --output-format json` y adapta el parseo a la salida real.
- `fake.py`: `FakeLLMClient` con respuestas fijas por nodo para tests y demos.
- `LLM_PROVIDER=claude_cli|fake` y `MODEL_<NODO>=haiku|sonnet`.
- La interfaz debe permitir añadir después un cliente de la API de Claude sin tocar
  los nodos (lo necesitaremos para el despliegue).

Nodos (prompt versionado en backend/prompts/, esquema JSON y modelo Pydantic):
1. intent (haiku): cargo_no_reconocido, cobro_indebido, consulta_movimientos,
   estado_reclamo, otro_tema_tarjeta, solicitud_no_soportada, sin_contenido; idioma
   (es|pt); certeza (alta|baja); sospecha_manipulacion; multiples_intenciones.
   NO pidas un número de confianza al LLM.
2. extract (haiku): merchant_hint, amount_hint {value, currency|null, approx},
   date_hint literal, card_hint, n_charges. El LLM no calcula fechas:
   `backend/app/dates.py` convierte date_hint en rango contra la fecha de la sesión
   (hoy, ayer, anteayer, la semana pasada, este mes, el mes pasado, hace N días, días
   de la semana, fechas explícitas; es y pt). Las fechas se resuelven contra
   transaction_date (ver H16).
3. clarify (haiku): UNA pregunta con las candidatas y el atributo discriminante que le
   pasa el código.
4. confirm (haiku): redacta; los datos del movimiento los inserta el código.
5. explain (sonnet): solo hechos verificados y reglas activadas; nunca promete
   devoluciones.
6. handoff_summary (sonnet): solo resumen y preguntas_abiertas.
Reglas: el texto del cliente va delimitado y se trata como dato; responde en el idioma
detectado; ningún prompt recibe datos de otros clientes.
Punto de control 2: un ejemplo de cada nodo con claude -p real y su latencia.

## Fase 3 — Interfaces de ML con baselines (sin entrenar nada)

Cada componente detrás de una interfaz, seleccionable por configuración, registrando en
la traza implementación y versión:
- `IntentClassifier`: `KeywordIntentClassifier` (reglas es/pt) y `LLMIntentClassifier`.
- `Ranker`: `RuleRanker` (monto, distancia a la ventana de fechas, similitud de comercio
  con rapidfuzz, softmax por lista). Ver el ADR del ranker.
- `RiskModel`: `RawFraudScoreRisk` (fraud_score/100, umbral 0.70 configurable).
- `ClarifyPolicy`: pregunta si no hay monto ni comercio, si hay más de una candidata
  dentro de la tolerancia de monto, o si top1/margen quedan bajo el umbral.
Umbrales en configuración. Tests unitarios de cada baseline.

## Fase 4 — Controlador, tools y política

- Máquina de estados: inicio, aclarando, confirmando_movimiento, confirmando_accion,
  ejecutando, cerrado, escalado; estado persistido por conversación. Aclaración máximo
  3 vueltas, luego handoff.
- Tools según docs/tools-contract.md, todas filtrando por el customer_id de la sesión:
  search_transactions (incluye pendientes y revertidas), get_transaction,
  list_transactions (consulta de movimientos, solo lectura, con filtros y límite),
  get_existing_case, fraud_risk, create_dispute_case, get_case, lock_card,
  get_card_status (usa app.card_status_effective), create_handoff.
  Una transacción ajena devuelve NOT_FOUND sin revelar si existe.
- Política R1–R6 como funciones puras con id; cada decisión registra las reglas
  activadas. Son supuestos del equipo: indícalo en el código y en docs.
- confirmation_token ligado a (sesión, conversación, acción, transacción), guardado en
  app.confirmation_tokens; se invalida al cambiar de movimiento, al expirar la sesión o al
  usarse. Al confirmar se revalidan permisos y reglas.
- Acciones con efecto idempotentes (Idempotency-Key en app.idempotency_keys) y
  verificadas leyendo lo escrito antes de devolver un bloque result con verified: true.
- Fallos de tool o del LLM: un reintento acotado y luego bloque error o handoff seguro.
- Trazas en app.traces por turno: nodo, tipo (llm|ml|code), implementación, modelo,
  versión de prompt, entrada, salida, reglas activadas, latencia y costo.

## Fase 5 — API

Implementa docs/api-contract.md (actualizado con la fase 1): conversaciones, turnos,
casos, handoffs y trazas. La respuesta de cada turno trae state, language, blocks (text,
candidate_list, transaction_card, transaction_list, action_confirmation, result,
handoff_notice, notice, error), input, data_as_of (de ops.etl_runs; el aviso al cliente
usa max_transaction_date) y trace_id. Documenta si usas respuesta única o SSE con
eventos de progreso.
Punto de control 5: con LLM_PROVIDER=fake, recorre por API (curl o httpie) un caso de
cargo claro, uno ambiguo y uno de riesgo alto con clientes reales de ref.demo_customers,
y muéstrame las respuestas y las filas creadas en app.

## Fase 6 — Harness de evaluación (eval/)

Formato de caso (YAML o JSONL con esquema validado): case_id, split (dev|test), language,
category (normal, ambiguo, humano, adversario, fallo, auth), username demo (el
customer_id sale de su sesión), fecha de sesión simulada, turns (guion fijo de mensajes y
clics; sin usuario simulado por LLM en esta versión), expected (resultado final:
resolved_case, resolved_info, recognized, clarified_then_resolved, abstained, escalated;
transaction_id esperado; acciones permitidas y PROHIBIDAS; tools obligatorias; campos
obligatorios del handoff).

Runner: `python -m eval.run --split dev --variant <config> --repeats N`
- Ejecuta contra el sistema real (API o controlador, sin mocks de tools), cada caso
  aislado en una base de pruebas (su nombre debe contener "_test").
- Guarda por caso turnos, traza, versiones de prompts y modelos, latencia y costo.

Checkers deterministas (sin LLM juez por ahora): resultado final, transacción correcta,
ninguna acción prohibida, ningún dato de otro cliente, ninguna afirmación de éxito sin
result verificado, sin reclamos duplicados, handoff completo con hechos existentes en ref,
número de vueltas de aclaración. Un test por checker con un caso que debe fallarlo.

Métricas del reto, SIEMPRE con numerador y denominador: resolución automática segura
(y % de casos con automatización intentada), contención, escalamientos correctos /
perdidos / innecesarios, resultados inseguros, latencia p50/p95 por turno y por caso,
costo por caso intentado y por resolución automática exitosa ("no definido" si no hay),
desglose por idioma, categoría y segmento, y variabilidad entre repeticiones.
Reporte en eval/results/<fecha>_<variant>.md + JSON crudo con la configuración exacta.

Casos iniciales en eval/cases/dev/ (~40, la mitad en portugués), con clientes reales
encontrados por SQL documentado: cargo claro; varios cargos parecidos; sin monto;
comercio vago; fecha equivocada; pendiente; revertido; reconocido; reclamo existente;
riesgo alto con bloqueo; cancelación; cambio de movimiento tras confirmar; consulta de
movimientos; transacción de otro cliente; prompt injection; solicitud no soportada; fallo
de tool inyectado; sesión expirada durante una confirmación.
eval/cases/test/ queda VACÍO (lo escribe el equipo a mano). El runner se niega a correr
--split test sin `--i-know-this-is-final` y registra cada ejecución en
eval/results/test_runs.log.

Primera medición (split dev):
1. baseline: KeywordIntentClassifier + RuleRanker + RawFraudScoreRisk, LLM fake;
2. sistema con claude -p (modelos por nodo como arriba), 3 repeticiones.
Tabla comparativa y los 5 fallos más frecuentes clasificados (extracción, aclaración,
política, escalamiento, idioma, tool). No ajustes nada para mejorar el número todavía.

---

## Reglas generales
- No inventes resultados; todo número sale de una ejecución.
- Actualiza docs/ y los README afectados (api-contract, tools-contract, conversation-flow,
  evaluation, open-questions).
- No subas datos, artefactos ni secretos (revisa .gitignore).
- Rama feat/backend-harness. Al final muéstrame `git status` y el resumen del diff y
  espera mi OK antes de hacer commit. No hagas push.
- Resumen final: comandos exactos para levantar todo, resultados de los puntos de
  control, tabla de la primera medición y pendientes.
