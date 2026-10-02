# Despliegue

**[Decisión]** Render ([ADR-0006](decisions/0006-hosting-en-render.md)). Estado: **Blueprint listo, nada creado todavía** (PR en
borrador; el despliegue va al final, con límite el sábado al mediodía). Precios y comportamiento verificados el 2026-10-01
en las páginas oficiales citadas abajo.

## Qué se despliega

| Pieza | Servicio de Render | Plan | Costo |
|---|---|---|---|
| Backend FastAPI (Docker, [backend.Dockerfile](../infra/render/backend.Dockerfile)) | Web service `disputas-api` | Starter: 0,5 CPU, 512 MB | $7/mes |
| PostgreSQL 17 | Render Postgres `disputas-db` | Basic-256mb | $6/mes + $0,30 por GB de disco |
| Frontend (Vite, estático) | Static site `disputas-web` | — | $0 |
| Workspace | Hobby | — | $0/mes + cómputo; 5 GB de ancho de banda incluidos, luego $0,15/GB |

- **Total:** ≈ **$13,30/mes** con 1 GB de disco. Dos semanas de demo ≈ **$7** (Render prorratea).
- **Memoria del backend (medida, `docker stats`, 2026-10-01):** 99 MiB en reposo y 113 MiB de pico con 8 conversaciones
  simultáneas de 6 turnos contra la API real (48 turnos, todos 200). Con los modelos en la imagen (2026-10-01, sobre una base `*_test`): 99 MiB en reposo con la configuración de producción (`sistema_api`) y 200 MiB si se activa la cascada (carga scikit-learn). Muy por debajo de ~400 MB: Starter alcanza; si creciera,
  el plan siguiente es Standard (2 GB, $25/mes).
- Fuentes: [render.com/pricing](https://render.com/pricing), [planes de cómputo](https://render.com/docs/compute-plans),
  [Blueprint spec](https://render.com/docs/blueprint-spec), [rewrites](https://render.com/docs/redirects-rewrites),
  [plan gratuito](https://render.com/docs/free) (no se usa: el web gratuito se duerme tras 15 min y la base gratuita vence a
  los 30 días).

## Cómo funciona

- **Mismo origen.** `disputas-web` reescribe `/api/*` al backend. La cookie de sesión `httpOnly` + `Secure` y el CSRF de doble
  envío funcionan sin CORS (`CORS_ALLOW_ORIGINS` vacío). El resto de rutas va a `index.html` (SPA).
- **Fases del turno.** El indicador de espera usa sondeo corto (`GET /api/conversations/{id}/phase`), no SSE: no hay
  conexiones largas que el proxy pueda cortar. La fase vive en la memoria del proceso; con una sola instancia (Starter) es
  exacta. Con más de una instancia podría devolver `null` y el frontend se queda con el texto neutro.
- **Base de datos.** Render entrega una sola connection string, la del dueño. La app no la usa para atender:
  [predeploy.sh](../infra/render/predeploy.sh) crea (idempotente) los grupos `app_rw` / `app_ro` y sus usuarios de login con
  contraseñas generadas por Render, y [start.sh](../infra/render/start.sh) deriva `DATABASE_URL` y `CONSOLE_DATABASE_URL` y
  quita la URL del dueño del proceso web. La base no acepta conexiones externas (`ipAllowList: []`).
- **Migraciones automáticas** en cada despliegue (`preDeployCommand`). Si fallan, Render deja la versión anterior.
- **Despliegue automático desde `main` solo con la CI en verde** (`autoDeployTrigger: checksPass`).
- **Protección activa** ([security.md](security.md)): rate limiting (con `TRUST_PROXY=true`, la IP sale de `X-Forwarded-For`),
  presupuesto de LLM ($5/día y $0,40 por sesión; al superarlo, modo degradado), tope de 2.000 caracteres, cabeceras de seguridad
  en la API y en el sitio estático (CSP, HSTS, nosniff).
- **LLM:** `anthropic_api` con la configuración evaluada como `sistema_api` ([llm-data.md](llm-data.md)).
- **Modo demo:** la pantalla de login muestra los usuarios demo por escenario y el aviso de datos ficticios. La contraseña
  demo (`DEMO_PASSWORD`) no está en el repo: se entrega a los jueces por el canal de la entrega.

## Secretos

| Variable | Quién la carga | Dónde |
|---|---|---|
| `ANTHROPIC_API_KEY` | el líder del equipo | panel de Render, al crear el Blueprint (`sync: false`) |
| `DEMO_PASSWORD` | el líder del equipo | igual |
| `ANTHROPIC_WORKSPACE_ID` | solo si la clave no pertenece a una workspace | agregar a mano en el panel (hoy no hace falta) |
| `APP_DB_PASSWORD`, `CONSOLE_DB_PASSWORD` | Render (`generateValue`) | nadie las ve |

Ningún secreto está en el repo, en la imagen ni en los logs. `gitleaks` corre en la CI sobre todo el historial.

### Variables no secretas del backend

Están en [infra/render/prod.env](../infra/render/prod.env) y, con los mismos valores, en `envVars` de `render.yaml`
(`scripts/predeploy_check.sh` falla si difieren). El entorno prodlike usa el mismo archivo.

| Variable | Valor | Para qué |
|---|---|---|
| `APP_ENV` | `production` | Cookies `Secure` |
| `TRUST_PROXY` | `true` | La IP del cliente viene en `X-Forwarded-For` (proxy de Render) |
| `LOG_FORMAT`, `LOG_LEVEL` | `json`, `INFO` | Logs estructurados |
| `BANK_HOME_URL` | sitio ficticio | Enlace de las consultas fuera de alcance |
| `LLM_PROVIDER` | `anthropic_api` | API de Claude con IDs de modelo fijos |
| `INTENT_CLASSIFIER`, `RANKER`, `CONFIRM_MODE`, `CLARIFY_MODE` | `llm`, `rule`, `template`, `auto` | La configuración evaluada como `sistema_api` |
| `VOICE_ENABLED` | `false` | Voz apagada |
| `DEMO_MODE` | `true` | El login muestra el aviso de datos ficticios y los usuarios demo (`GET /api/demo/info`, sin contraseña) |
| `RATE_LIMITS_ENABLED` | `true` | Límites de peticiones |
| `LLM_BUDGET_DAILY_COST_USD`, `LLM_BUDGET_DAILY_CALLS`, `LLM_BUDGET_SESSION_COST_USD`, `LLM_BUDGET_SESSION_CALLS` | 5, 3000, 0.40, 80 | Presupuesto de LLM; al agotarse, modo degradado |
| `RISK_MODEL` | no se fija | Vale el de `backend/config/ml.toml`: score calibrado `risk-v1` |
| `ADMIN_DATABASE_URL`, `APP_DB_USER`, `CONSOLE_DB_USER` | los pone Render / el Blueprint | Base y usuarios de la app (las contraseñas, arriba) |

## Checklist del sábado (orden exacto)

Quién: **H** = Henry (líder), **C** = sesión de Claude Code. Nada de esto se ha ejecutado todavía.

| # | Paso | Quién | Cómo | Listo cuando |
|---|---|---|---|---|
| 0 | Verificación previa | C | Fusionar el PR del despliegue a `main` con la CI en verde y correr `scripts/predeploy_check.sh` en `main` | Termina en "LISTO para desplegar" |
| 1 | **Crédito** de la API de Anthropic | H | Consola de Anthropic: cargar crédito y poner un límite de gasto mensual. Una llamada de prueba local con la clave de `~/.anthropic_key` | La llamada de prueba responde 200 |
| 2 | **Blueprint** | H | Render → *New* → *Blueprint* → este repositorio, rama `main` | Render muestra `disputas-db`, `disputas-api` y `disputas-web` |
| 3 | **Secretos** | H | En el formulario del Blueprint: `ANTHROPIC_API_KEY` y `DEMO_PASSWORD`. Nadie más los ve | Primer despliegue en verde: el `preDeployCommand` creó roles y migraciones. Si falla por `CREATEROLE`, ver el paso 2 de "Detalle" |
| 3b | Nombre del backend | C | Si Render no asignó `disputas-api.onrender.com`, cambiar el destino del rewrite `/api/*` en `render.yaml` (PR, CI, merge) | `https://<web>/api/ready` responde `ready` con `llm_provider: anthropic_api` |
| 4 | **Carga demo** | H + C | Paso 4 de "Detalle": IP temporal en *Access Control*, `scripts/render_load_demo.sh`, quitar la IP y borrar el archivo con la URL. Luego *Manual Deploy* (el predeploy crea los usuarios demo si no se crearon en la carga) | `GET /api/demo/info` lista 12 clientes demo, 2 agentes y 1 admin |
| 5 | **Humo público** | C | `DEMO_PASSWORD=… scripts/prodlike_smoke.sh --url https://<web>` (los mismos 10 pasos que en prodlike, con la API real) | 10/10. La tabla va a este documento y a `docs/STATUS.md` |
| 6 | **Corrida final con la API** | C | `scripts/final_eval.sh --final` (split `test` congelado, una sola vez, `anthropic_api`, mismo commit que el desplegado, base de evaluación separada). Antes: `scripts/final_eval.sh` sin `--final` para el ensayo en dev | Tabla para las diapositivas en `eval/results/` y en `docs/evaluation.md`; llamadas LLM fallidas < 5 % |
| 7 | **Repo público** | H | Antes: `scripts/predeploy_check.sh` otra vez (secretos y datos). Luego GitHub → *Settings* → *Change visibility* | El repo abre sin sesión |
| 8 | **Proteger `main`** | C | `scripts/protect_main.sh` | `gh api repos/<owner>/<repo>/branches/main/protection` responde con las reglas |
| 9 | **Tag `v1.0.0-rc`** | C | CHANGELOG, tag anotado sobre el merge commit, push del tag (el workflow de release publica la versión) | La versión aparece en *Releases* |

Si un paso falla, se detiene ahí: los pasos 7–9 no se hacen con el humo o la corrida final en rojo.

## Detalle de los pasos

1. **Crear el Blueprint** (líder del equipo): Render → *New* → *Blueprint* → este repositorio, rama `main`. Render lee
   [render.yaml](../render.yaml) y pide `ANTHROPIC_API_KEY` y `DEMO_PASSWORD`.
2. **Primer despliegue.** El `preDeployCommand` crea los roles y aplica las migraciones. Si el usuario dueño no pudiera crear
   roles (`CREATEROLE`), el paso falla con ese mensaje y no se publica nada: avisar para aplicar la alternativa (crear los
   roles una vez desde el panel SQL de Render, o usar el usuario dueño para la app y anotar la excepción en security.md).
3. **Nombre del backend.** Si Render no asigna `disputas-api.onrender.com` (nombre ocupado), copiar la URL real al destino del
   rewrite `/api/*` en `render.yaml` y fusionar ese cambio.
4. **Carga del subconjunto demo** (manual, desde un equipo con el dataset; el dataset no está en el repo ni en la imagen):
   1. En el panel de la base → *Access Control*: agregar la IP del equipo.
   2. Guardar la *External Database URL* en un archivo fuera del repo (p. ej. `~/.render_db_url`, permisos 600).
   3. `RENDER_ADMIN_DATABASE_URL="$(cat ~/.render_db_url)" scripts/render_load_demo.sh` (200 clientes deterministas, con los
      clientes demo de cada escenario; crea también los usuarios demo si hay `DEMO_PASSWORD` local).
   4. Quitar la IP del *Access Control* y borrar el archivo.
5. **Prueba de humo en la URL pública:** login; cargo claro; cargo ambiguo; riesgo alto; fuera de alcance; consola del
   analista; y una ráfaga que demuestre el 429 del rate limiting. Resultados en este documento.
6. Cerrar el issue #18, README y tag `v0.6.0`… (la versión que corresponda al fusionar).

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Una sola instancia y sin alta disponibilidad | Aceptado para la demo; `/api/ready` y el health check de Render reinician el servicio |
| Arranque en frío | No aplica en Starter (no se duerme). El plan gratuito sí se duerme: no se usa |
| El rate limiting y las fases viven en memoria del proceso | Correcto con una instancia; con varias haría falta Redis (documentado en security.md) |
| `X-Forwarded-For` lo arma el proxy de Render | El límite por sesión no depende de la IP; el de IP es una segunda capa |
| Costo de LLM por abuso | Presupuesto diario y por sesión, modo degradado y límite de gasto en la consola de Anthropic |
| Base de 256 MB | El subconjunto demo es de cientos de clientes, no los 150.000 del dataset completo (1,9 GB en local) |

## Alternativa de "banco real" (no desplegada)

AWS con ECS Express Mode + RDS en VPC privada: ver el [ADR-0006](decisions/0006-hosting-en-render.md), con el costo estimado.
