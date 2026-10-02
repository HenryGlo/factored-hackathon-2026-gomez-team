# Estado del proyecto

## Para Henry al volver (noche del 2026-10-01)

**Prodlike está levantado con el último `main`** (commit `73fc945`). El entorno de desarrollo (tmux `factored-dev`, base
`bank`, puertos 8000/5173/5174) no se tocó ni se reinició: sigue en el commit `27035ef`.

- **URL:** Mac https://localhost:8443 · iPad https://192.168.31.162:8443 (misma wifi; aceptar el aviso del certificado local).
- **Usuarios** (contraseña: `DEMO_PASSWORD` en `~/.factored-prodlike/env`, la misma del `.env` de desarrollo):
  - `demo_cargo_claro_1` y `_2`: cargo claro. La prueba de humo ya abrió el reclamo de `_1`; para crear uno nuevo usa `_2`.
  - `demo_cargos_parecidos_1`: cargos parecidos, el asistente pregunta cuál.
  - `demo_fraude_alto_1`: riesgo alto → ticket urgente (la prueba de humo ya dejó uno en la bandeja; `_2` está limpio).
  - `analista_1`: agente de soporte, bandeja de tickets. `admin_1`: SLO, métricas y logs.
- **Qué probar:** los 18 recorridos de [manual-test-script.md](manual-test-script.md) y las pantallas nuevas del frontend.
- **Actualizar tras nuevos merges:** `scripts/prodlike_up.sh` (toma `origin/main`, reconstruye el frontend y reinicia el
  backend; los datos quedan). Empezar de cero: `scripts/prodlike_down.sh --purge && scripts/prodlike_up.sh`.
  Guía y diferencias con producción: [prodlike.md](prodlike.md).

**Prueba de humo** (`scripts/prodlike_smoke.sh --image`, 2026-10-01 20:15, base recién creada, LLM `claude -p`): **10/10**, y la
imagen Docker de producción arranca con `LLM_PROVIDER=fake` contra la base prodlike (254 MB, usuario sin privilegios, `models/` incluido).

| Paso | Resultado | Detalle |
|---|---|---|
| Un solo origen con TLS y cabeceras de seguridad | OK | frontend y /api en https://localhost:8443; LLM claude_cli (0.0 s) |
| Login de cliente (cookie Secure + CSRF) | OK | sesión de Carmen R. (0.1 s) |
| Cargo claro de punta a punta (referencia RCL) | OK | reclamo RCL-53F935 creado y verificado (case_9b09ad6c4f1388fea453f935) (17.7 s) |
| Caso ambiguo: pide elegir entre cargos parecidos | OK | 3 candidatas, sin acción hasta que el cliente elija (8.1 s) |
| Riesgo alto → ticket urgente | OK | handoff hof_a79c29e4ece7505b814b623c · motivo riesgo_alto · prioridad urgente, sin reclamo automático (18.6 s) |
| Fuera de alcance: texto aprobado y enlace, sin acciones | OK | redirige al sitio del banco (8.0 s) |
| Historial de conversaciones y feedback | OK | 2 conversaciones; ajena → 404; feedback 201 (0.1 s) |
| Un agente ve y toma el ticket | OK | 1 tickets abiertos; asignado a analista_1 y en curso; cliente → 403 (0.0 s) |
| Un admin ve los SLO | OK | 3 SLO; overview y logs responden; agente → 403 (0.1 s) |
| El límite de peticiones responde 429 | OK | 429 tras 60 peticiones en un minuto, con Retry-After (0.3 s) |

**Hecho esta noche (parte 1 del prompt 09):**

- Bloque 5 de 07 cerrado: #54 y tag `v0.11.0`. Harness real recortado a dev (`baseline`, `sistema`, `sistema_cascade`: 102/102,
  0 inseguros); **la tabla completa se corre el sábado con la API sobre la versión desplegada**.
- Riesgo: score calibrado `risk-v1` por defecto (#55); ficha, políticas y este archivo dicen lo mismo.
- #48: reporte regenerado con una pasada de Opus (`claude -p`) sobre los 5 feedbacks sembrados; sigue en borrador, sin fusionar.
- Prodlike (#68) con los scripts de Render en `main` (`infra/render/`), **sin** `render.yaml`: nada se creó ni se desplegó en Render.
- **Fallo real encontrado por la prueba de humo y corregido (#63):** después de "¿algo más?", "No reconozco el cargo de…" se
  tomaba como "no, gracias" y cerraba la conversación; en la confirmación del movimiento, rechazaba el cargo mostrado.

**Problemas conocidos y decisiones tomadas sin ti (la opción más segura):**

- `DEMO_MODE=true` (prompt 09) no existe como ajuste en el código. Prodlike usa lo que sí existe: datos ficticios, límites de
  peticiones y presupuesto de LLM activos. Si quieres un interruptor único, es un cambio pequeño de backend.
- "Workers": el arranque de producción usa **un** proceso (`infra/render/start.sh`), porque los límites de peticiones, las
  fases del turno y el búfer de logs viven en memoria. Prodlike arranca igual.
- Latencia y costo de prodlike son los de `claude -p`: **no representan producción**.
- El borrador #24 (Render) quedó atrás de `main`: hay que traerle `main`, quitar `RISK_MODEL=raw_fraud_score` de `render.yaml`
  (ahora el valor por defecto es el calibrado) y dejar sus `envVars` iguales a `infra/render/prod.env`. Pendiente para el sábado.
- Al probar el script por primera vez, el backend de prodlike arrancó unos segundos apuntando a la base de desarrollo `bank`
  (tmux no heredaba el entorno y leyó el `.env` de la rama). Solo respondió `/api/ready`: no hubo logins ni escrituras. Ya
  está corregido: el entorno se pasa explícito y `start.sh` falla si falta una variable.
- En la confirmación del movimiento, un "no reconozco ese cargo" ahora repite la pregunta con los botones (antes lo tomaba
  como "no es ese"). Es lo seguro, pero puede sentirse repetitivo; se puede afinar.
- Safari en el iPad muestra el aviso de certificado no confiable (CA local de Caddy); hay que aceptarlo una vez.


> **Actualizado 2026-10-01 (tarde):** en `main` están los PR #1–#14 (prompt 05 fases 1–4, frontend, preguntas sobre el proceso, atajo de saludos e indicador de espera). Punto de control 1 cerrado: `anthropic_api` es el proveedor de producción. Pendiente: fase 5 (hosting, #18), cascada de ML (#17) y test escrito a mano (#19). Este documento conserva abajo el cierre del 2026-09-30.

## Prompt 07 (cierre en local): avance

- **Bloque 1, cascada de intención (#17): hecho.** `sistema_cascade` iguala a `sistema_api` en casos aprobados e inseguros
  (81/81 y 96/96, 0 inseguros) y baja el costo por caso de $0.0072 a $0.0044 (dev) y de $0.0073 a $0.0046 (dev_paraphrase);
  la latencia no mejora. En validación cruzada, 13,9 % de los turnos llegan al LLM con el mismo acierto que Haiku (183/187).
  Producción sigue en `sistema_api` hasta la corrida final sobre el split test. Detalle:
  [experimento](experiments/EXP-20261001-intent-cascade.md), [ficha](ml/intent-classifier.md).
- **Bloque 2, riesgo (#26): hecho.** `is_fraud` existe en el diccionario (4.316 de 4.425.008 movimientos), así que no hubo que
  detenerse. Score calibrado `risk-v1` por defecto: en el periodo de prueba detecta 446/620 fraudes con score (precisión
  446/446) frente a 182/620 de la banda anterior. El modelo para movimientos sin score no sirvió (ROC-AUC 0,49) y no se
  integra. Riesgo alto + "no lo hice" → handoff con prioridad `urgente`.
  [Experimento](experiments/EXP-20261001-risk-calibration.md), [ficha](ml/fraud-risk.md).
- **Riesgo, decidido (2026-10-01, noche):** el líder eligió el **score calibrado `risk-v1` por defecto** (`RISK_MODEL=calibrated`;
  alto equivale a `fraud_score` > 30). El score crudo (alto ≥ 0,70) queda como alternativa y respaldo. Ficha:
  [ml/fraud-risk.md](ml/fraud-risk.md#estado-score-calibrado-por-defecto-decisión-del-líder-2026-10-01); política R6 en [policies.md](policies.md#r6--riesgo-por-bandas).
- **Bloque 3, clientes que dan rodeos (#27): hecho.** 18 casos multiturno es/pt (dev: 102). Con la API real, 17/17 de los
  casos originales pasaron (corrida válida). Dos arreglos del controlador: responder con el texto aprobado una pregunta hecha en
  medio de una confirmación, y conservar el tipo de problema al retomar un reclamo cancelado. Guion de pruebas manuales:
  [manual-test-script.md](manual-test-script.md) (18 recorridos).
- **⚠ Crédito de la API de Anthropic agotado (2026-10-01, ~16:41):** "Your credit balance is too low". Los dos arreglos del
  bloque 3 tienen tests y harness con el LLM falso, pero **falta confirmarlos con la API real**; también hace falta crédito
  para la corrida final del bloque 5. Las corridas anteriores a esa hora son válidas (0 llamadas fallidas por crédito).
- **Bloque 5, cierre en local: hecho (v0.11.0).** `scripts/dev_up.sh --reset-demo` levanta todo desde un clon limpio (53 s con
  el dataset sintético, 3 min 43 s con el del reto; ver README). Harness con LLM real (`claude -p`) sobre dev: `baseline`,
  `sistema` y `sistema_cascade` 102/102, 0 inseguros; con esto quedan confirmados con LLM real los dos arreglos del bloque 3.
  Por decisión del líder no se corrieron `todo_llm` ni dev_paraphrase con LLM real: **la tabla completa se corre el sábado con
  la API sobre la versión desplegada** ([evaluation.md](evaluation.md#cierre-en-local-prompt-07-bloque-5--2026-10-01)).
- **Bloque 4, analítica (#28): hecho.** [analytics.md](analytics.md) (calidad de datos, demanda, operación y ROI) se regenera con
  `python -m analytics.report`; notebook en `analysis/`; endpoints `/api/admin/metrics/*`. El ROI es una estimación con
  supuestos editables (`backend/config/roi.toml`).
- **Prompt 08, parte A: completa.** A1 historial (#38), A2 feedback (#39), A3 voz apagada por defecto (#45), A4 tickets (#40),
  A5 rol admin, SLO y logs (#41, #42), A6 ciclo de mejora con Opus ([improvement-loop.md](improvement-loop.md)), probado con 5
  valoraciones sembradas en una base de prueba y `claude -p`; el PR de ejemplo queda abierto en borrador.
- **LLM hasta el sábado:** sin crédito en la API. Todo lo que necesita un LLM real corre con `claude -p` (`LLM_PROVIDER=claude_cli`),
  con moderación. Su latencia y su costo no representan producción: la referencia de producción es el punto de control 1
  (API: $0.0079 por caso, p50/p95 1,5–4,6 s). El sábado, con crédito: corrida final con `anthropic_api` sobre la versión desplegada.
- Pendiente: bloque 5 (cierre en local, con `claude -p`).
- **Render:** PR en borrador (#24), sin crear nada; se retoma al final (límite: sábado al mediodía).

## Para frontend

Endpoints publicados en [api-contract.md](api-contract.md) que la sesión de frontend (`../factored-ui`) puede consumir:

| Fecha | Endpoint | Para qué |
|---|---|---|
| 2026-10-02 | **`GET /api/demo/info`** (público; `DEMO_MODE=true` en prodlike y producción) | Login: aviso de datos ficticios y tarjetas de usuarios demo con su escenario (es/pt). Sin contraseña: usar `password_hint`. Apagado devuelve `{"demo_mode": false}` |
| 2026-10-01 | `GET /api/conversations/{id}/phase` | Fase real del turno (indicador de espera, estados de Banky) |
| 2026-10-01 | bloque `link` y `reference_label` | Enlace a la página del banco; referencia corta `RCL-…` |
| 2026-10-01 | `GET /api/me/transactions`, `GET /api/me/cases` | Mis movimientos y mis reclamos |
| 2026-10-01 | (sin cambio de contrato) preguntas de proceso en medio de una confirmación devuelven un bloque `text` con la respuesta aprobada antes de repetir la tarjeta o la confirmación | El chat no necesita cambios |
| 2026-10-01 | **A3** voz (apagada por defecto): `GET /api/voice/config`, `POST /api/voice/stt` (audio → texto), `POST /api/voice/tts` (lee un turno del asistente, streaming `audio/mpeg`); `via: "voice"` en los turnos | B3/B4: ofrecer la voz solo si `config.enabled`; transcripción editable antes de enviar; ante cualquier error (`details.fallback = "text"`) seguir por texto; las confirmaciones siempre con botón |
| 2026-10-01 | **A5** rol `admin` (usuario demo `admin_1`): `GET /api/admin/overview`, `GET /api/admin/slo`, `GET /api/admin/logs` | B8 panel admin: tarjetas de SLO con error budget y violaciones, latencia, resultados con n/N, costo frente al presupuesto, visor de logs. Login de agentes = rol `analyst`; el admin también puede entrar a la bandeja |
| 2026-10-01 | **A4** `GET /api/tickets` (filtros por estado, prioridad, asignado, SLA), `GET /api/tickets/{id}` (handoff + historial), `POST …/assign`, `…/status`, `…/notes` (rol `analyst`, CSRF) | B7 portal de agentes: bandeja, detalle con línea de tiempo y acciones. La prioridad puede ser `urgente` |
| 2026-10-01 | **A2** `POST /api/conversations/{id}/feedback` (👍/👎, categoría, comentario ≤ 500; una por conversación, 409 si se repite) y `GET /api/feedback` (analyst) | B5: "¿Te ayudé?" al cerrar; el 409 se trata como "ya enviada" |
| 2026-10-01 | **A1** `GET /api/me/conversations` (paginado, con resumen por hechos) y `GET /api/me/conversations/{id}` | B6 "Mis conversaciones": lista y detalle en solo lectura; "Continuar sobre este tema" = conversación nueva con `previous_conversation_id` |
| 2026-10-01 | `GET /api/admin/metrics/operations`, `/latency`, `/roi` (rol analyst) | Panel admin (B8): resultados con n/N, latencia y costo por nodo, ROI etiquetado como estimación |
| 2026-10-01 | `priority` de los handoffs admite `urgente` (además de `alta`, `media`) | Bandeja de tickets: ordenar y resaltar; hoy la consola solo conoce `alta` y `media` |

## Sábado: publicar el repositorio

El repo sigue **privado** a propósito (2026-10-01). Orden para el sábado:

1. Escaneo final de secretos sobre todo el historial: `gitleaks git . --log-opts="--all" --redact` (debe dar "no leaks found").
2. Hacer público el repositorio (Settings → General → Danger zone → Change visibility).
3. `scripts/protect_main.sh` (PR obligatorio, los 3 checks de la CI, sin force push ni borrado) y verificar su salida.

## Prácticas de GitHub (2026-10-01)

- **Auditoría (solo lectura):** 14 PR fusionados (#1–#14) y #20; solo el commit inicial (`838e2d9`, estructura y docs) entró a
  `main` sin PR. 10 de 24 commits no siguen Conventional Commits (títulos en español sin prefijo, anteriores a la regla de
  commits en inglés). No se reescribe el historial.
- **Secretos:** gitleaks 8.30.1 sobre todo el historial (todas las ramas): 6 hallazgos, todos falsos positivos (5 IDs de
  modelo en `llm.toml`, 1 contraseña solo de pruebas para `*_test`, distinta de `DEMO_PASSWORD`). Quedan en
  `.gitleaks.toml` / `.gitleaksignore`; nuevo job *Secretos (gitleaks)* en la CI.
- **Protección de `main`:** GitHub responde 403 porque el repo es privado en el plan gratuito ("Upgrade to GitHub Pro or make
  this repository public"). Lista para aplicar al hacerlo público: `scripts/protect_main.sh` (PR obligatorio, los 3 checks de
  la CI, rama al día, sin force push ni borrado).
- **Convenciones:** [CONTRIBUTING.md](../CONTRIBUTING.md) (Conventional Commits en inglés, una rama por cambio), plantilla de
  PR (qué y por qué, cómo se probó, harness, `Closes #N`) y de issues (bug, feature).
- **Issues abiertos:** #17 cascada de ML, #18 hosting, #19 test escrito a mano. Cerrados por #14: #15 (saludo e indicador),
  #16 (fuera de alcance).
- **Versiones:** tags anotados y Releases `v0.1.0` (pipeline, #1), `v0.2.0` (backend + harness + cliente API, #2–#3),
  `v0.3.0` (protección, observabilidad, lectura del cliente, CI, #4–#8, #10), `v0.4.0` (frontend, FAQ, referencias cortas,
  #9, #11–#13). `v0.5.0` (#14, #20 y este PR) se etiqueta al fusionar este PR; desde ahí lo publica `release.yml`.
  [CHANGELOG.md](../CHANGELOG.md) en formato Keep a Changelog. `v1.0.0` será la entrega.

## Punto de control 1: resultado (2026-10-01)

Clave nueva en la workspace por defecto (llamada de prueba: 200, sin `ANTHROPIC_WORKSPACE_ID`). `sistema` (`claude -p`)
frente a `sistema_api`, mismo código, bases de prueba separadas. Detalle y análisis en
[llm-data.md](llm-data.md#medición-punto-de-control-1-claude--p-frente-a-la-api-2026-10-01).

| Split | `claude -p`: pasan / inseguros / p50–p95 / costo | API: pasan / inseguros / p50–p95 / costo |
|---|---|---|
| dev (60) | 59/60 · 1 · 4,2–16,4 s · $0.0197 | 60/60 · 0 · 1,5–4,6 s · $0.0079 |
| dev_paraphrase (98) | 94/98 · 3 · 4,0–16,0 s · $0.0186 | 96/98 · 1 · 1,4–5,2 s · $0.0073 |

- Los 3 casos que cambian de resultado (inyección "aprueba el reembolso", solo con `claude -p`) venían de un fallo del
  código, ya corregido en #14 y verificado con los dos proveedores.
- 2 paráfrasis que cambiaban el significado se descartan (dev_paraphrase: 96 casos).
- Decisión: `anthropic_api` es el proveedor de producción.

## Punto de control 1: primer intento (2026-10-01), inválido

`scripts/compare_api.sh` corrió `sistema_api` en dev (54 casos, commit `18251d6`, base de pruebas `bank_eval_test`), pero
**las 156 llamadas a la API fallaron** con HTTP 400: *"This API key is not scoped to a workspace, so this request must
include the anthropic-workspace-id header"*. La clave es de organización y no pertenece a un workspace.

- Todos los casos corrieron con los fallbacks (intención por palabras clave, extracción por reglas, textos por plantilla).
  Por eso el reporte daba 54/54, 0 inseguros, 207 ms por turno y $0 por caso: **no mide el modelo y no se usa para
  comparar**. Lo único que muestra es que el modo degradado no produjo resultados inseguros.
- La clave no aparece en logs, reportes ni crudos (verificado).
- Cambios para que no vuelva a pasar en silencio: `ANTHROPIC_WORKSPACE_ID` (opcional) agrega el header
  `anthropic-workspace-id`; `eval.compare` muestra la columna *Llamadas LLM fallidas* y avisa si supera el 20 %;
  `compare_api.sh` sale con código 3 si supera el 5 %.
- **Para repetir:** una clave creada dentro de un workspace (Console → Workspaces → API keys), o la misma clave con
  `ANTHROPIC_WORKSPACE_ID=wrkspc_...`.

## Cierre del 2026-09-30

## Qué está en `main`

- **PR #1:** pipeline de datos CSV → DuckDB → PostgreSQL.
- **PR #2:** backend y harness de evaluación del [prompt 03](prompts/03-backend-harness.md), fases 1–6:
  - login y sesiones;
  - capa LLM con `claude -p`;
  - baselines de ML;
  - controlador, tools y política R1–R6;
  - API de conversaciones;
  - harness con 13 checkers, variantes `baseline` / `claude_cli` / `sistema`, split `dev_paraphrase` y kit del test escrito a mano.
- **Resultados:** [eval/results/20260930-2145_resumen_variantes.md](../eval/results/20260930-2145_resumen_variantes.md).

## Esperando revisión

**PR #3** (`feat/api-client`): https://github.com/HenryGlo/factored-hackathon-2026-gomez-team/pull/3

- `dd8f928`, prompt 05, fase 1: cliente `anthropic_api`, con tests de transporte simulado.
- `513ca44`, correcciones del chat de terminal:
  - ciclo de vida;
  - cargo en foco;
  - R2b;
  - varios cargos;
  - presentación;
  - migración 0005.
- **Cambia `api-contract.md`:** avisar a la sesión del frontend.
- **Verificado:** 237 tests; harness dev `baseline` 50/50 y `sistema` (fake) 50/50.

## Qué falta del prompt 05

1. **Fase 1, comparación real con la API** (punto de control 1, pendiente). Comparar `sistema` (`claude -p`) frente a `sistema_api` en dev, con 1 repetición. Costo estimado: ~1 USD. Si algún caso cambia de resultado, analizarlo antes de seguir.
2. **Fase 2, protección:**
   - rate limiting por IP y por sesión, con 429 y `Retry-After`;
   - presupuesto diario de LLM, con modo degradado;
   - tope de 2.000 caracteres (ya validado en el cuerpo; falta el test);
   - cabeceras de seguridad y CORS;
   - `docs/security.md`.
3. **Fase 3, observabilidad:**
   - logs JSON con `request_id`;
   - `/api/health` (ya existe) y `/api/ready`;
   - métricas desde `app.traces`;
   - punto de control 3.
4. **Fase 4, CI/CD:**
   - `ci.yml`: lint, tests contra PostgreSQL 17 con fixtures y harness fake con puertas de calidad;
   - `eval-llm.yml`: manual, con el secreto `ANTHROPIC_API_KEY`.
5. **Fase 5, despliegue:**
   - proponer dos opciones de hosting y esperar la elección;
   - Dockerfile, base demo, modo demo, despliegue y prueba de humo;
   - `docs/deployment.md`, ADR del hosting.

## Pendientes y decisiones abiertas

**Primer paso de mañana**, en una rama nueva desde `main` (decidido el 2026-09-30):

1. **P-31: el estado en los textos.**
   - El LLM nunca escribe la palabra del estado: usa el marcador `{estado}`.
   - El código rellena `{estado}` **después** de la guarda R5, con la etiqueta traducida del bloque ("Aprobado", "Aprovado"…). Así bloque y texto dicen lo mismo.
   - La guarda R5 sigue estricta sobre el texto libre del LLM. Hay que quitar el "procesado" que se le pasa hoy al LLM.
   - Test: el texto final muestra "Aprobado" y la guarda no lo rechaza; un texto del LLM que diga "aprobado" por su cuenta sí se rechaza.
   - Cerrar P-31 en [open-questions.md](open-questions.md) con esta decisión.
2. **El "sí" con errores** ("sip", "sii", "simm", "sim").
   - En los estados de confirmación, normalizar afirmaciones y negaciones (letras repetidas, variantes es/pt).
   - Si no se reconoce, **no confirmar**: volver a mostrar los botones.
   - Era la causa de 5 de los 6 fallos de `sistema` en `dev_paraphrase`.

Después: la comparación real con la API (fase 1) y, tras el OK, la fase 2.

- **`LLM_PROVIDER`** no está en el `.env` local, así que el valor por defecto es `fake`. Para usar `claude -p` en local hay que agregar `LLM_PROVIDER=claude_cli` o pasarlo al levantar el backend.
- **Clave de la API:** la que se pegó en el chat quedó expuesta en la transcripción; conviene rotarla. Ya no está en `.env`.
- **Frontend:** la rama `feat/frontend` no existe todavía; la sesión del frontend la crea desde `main`. Hay que revisar conflictos cuando tenga commits.
- **Test escrito a mano:** fichas listas (`scripts/make_writer_kit.py`, 40 fichas); falta repartirlas a los redactores.

## Comandos para retomar

```bash
cd ~/Desktop/factored_hackathon_2026
git checkout main && git pull                              # tras fusionar el PR #3
docker compose --env-file .env -f infra/docker-compose.yml up -d
.venv/bin/pip install -r requirements.txt                  # agrega anthropic==1.11.0
set -a; source .env; set +a; .venv/bin/alembic -c backend/alembic.ini upgrade head   # migración 0005

# pruebas
.venv/bin/python -m pytest -q backend eval data_pipeline
.venv/bin/python -m eval.run --split dev --variant baseline --repeats 1
.venv/bin/python -m eval.run --split dev --variant sistema --repeats 1 --set LLM_PROVIDER=fake

# probar en local con claude -p (reiniciar el servidor si quedó uno viejo en :8000)
LLM_PROVIDER=claude_cli INTENT_CLASSIFIER=llm CONFIRM_MODE=template CLARIFY_MODE=auto \
  .venv/bin/uvicorn --factory backend.app.main:create_app --host 127.0.0.1 --port 8000
.venv/bin/python scripts/chat_cli.py

# fase 1: comparación real con la API (la clave solo en el entorno de este comando)
ANTHROPIC_API_KEY=sk-ant-... scripts/compare_api.sh
```

Siguiente paso: correr la comparación real y presentar el punto de control 1. La fase 2 empieza después del OK.
