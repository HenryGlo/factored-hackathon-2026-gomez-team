# frontend/

Chat del cliente y consola del analista en una sola app: React 18, Vite 6 y TypeScript. La fuente de verdad es [docs/api-contract.md](../docs/api-contract.md); el frontend solo renderiza bloques y envía mensajes o acciones, nunca decide si se ejecuta algo.

## Cómo correrlo

Con un comando, desde la raíz del repo:

```bash
scripts/dev_up.sh                    # PostgreSQL, migraciones, backend :8000 (claude -p, configuración del sistema) y Vite :5173
LLM_PROVIDER=fake scripts/dev_up.sh  # sin LLM (plantillas y reglas)
scripts/dev_up.sh --seed             # además crea los usuarios demo (DEMO_PASSWORD de .env)
scripts/dev_up.sh --reset-demo       # borra conversaciones, reclamos, handoffs y bloqueos de los clientes demo
```

Abrir http://localhost:5173. En desarrollo la API va por el **proxy de Vite** (`/api` → `127.0.0.1:8000`), en el mismo origen: la cookie de sesión httpOnly y el CSRF de doble envío funcionan sin CORS.

Solo el frontend, con el backend ya levantado:

```bash
cd frontend
npm ci
npm run dev        # o VITE_API_PROXY=http://otro:8000 npm run dev
npm run lint && npm run typecheck && npm test && npm run build

# capturas de todas las pantallas (1440 y 390 px); necesita un backend con LLM_PROVIDER=fake sobre una base *_test
npx playwright install chromium
DEMO_PASSWORD=… BASE_URL=http://127.0.0.1:5173 npm run screenshots        # deja docs/screenshots/ (raíz del repo), para las diapositivas

# Lighthouse de la landing y del chat con sesión (sobre el build de producción servido con vite preview)
DEMO_PASSWORD=… BASE_URL=http://127.0.0.1:4173 node scripts/lighthouse.mjs
```

## Pruebas de punta a punta (Playwright)

```bash
# con la app levantada (backend LLM_PROVIDER=fake sobre una base *_test, usuarios demo y estado de demo limpio)
npx playwright install chromium
DEMO_PASSWORD=… BASE_URL=http://127.0.0.1:5173 npm run e2e
```

- [e2e/journeys.e2e.ts](e2e/journeys.e2e.ts): los tres recorridos contra el backend real.
  1. **Cliente con un cargo claro:** landing → login → Banky se presenta (voz apagada: explica por qué) → mensaje → confirma el movimiento → confirma con el botón → resultado verificado con `RCL-…` → valoración → aparece en Mis reclamos y en Mis conversaciones.
  2. **Agente que atiende un ticket:** un cliente pide una persona (crea el `ATN-…`) → el agente entra por su acceso, abre el ticket, lo toma, lo pasa a "En curso" y deja una nota; quedan los tres eventos en el historial.
  3. **Admin que revisa los SLO:** tres tarjetas con su presupuesto de error, resultados con n/N, costo frente al presupuesto, logs filtrados por ruta y acceso a la bandeja.
- [e2e/a11y.e2e.ts](e2e/a11y.e2e.ts): axe (WCAG 2.1 A y AA, sin violaciones serias ni críticas) en todas las pantallas, en escritorio y celular, más el enlace "Saltar al contenido" y el foco visible con teclado.
- No corre en la CI (necesita un backend con datos); en la CI corren lint, tipos, los tests de componentes y el build.
- Si se corre justo después de las capturas (muchos logins seguidos), el límite de intentos por IP puede responder 429: esperar un minuto.
- El recorrido del cliente crea un reclamo: para repetirlo hay que limpiar el estado de demo (`scripts/dev_up.sh --reset-demo`, o una base de prueba recién cargada).

## Recorrido del video

`npm run demo check | open | record` ([scripts/demo.mjs](scripts/demo.mjs)): revisa que el entorno esté listo, abre cinco ventanas con la sesión iniciada o graba solo los tres recorridos (cargo claro, caso ambiguo, riesgo alto → agente → admin). Guion de clics: [docs/demo-script.md](../docs/demo-script.md).

## Pantallas

| Ruta | Rol | Qué hace |
|---|---|---|
| `/` | — | Landing de BankyFicticious: "Tengo un reclamo" (abre el chat; sin sesión pasa por el login), acceso de agentes (`/login?perfil=agente`), cómo funciona, qué puede y qué no puede hacer Banky, aviso de datos ficticios. Lighthouse (build de producción, 2026-10-02): landing y chat con rendimiento 98–100 y accesibilidad 100 en celular y escritorio. |
| `/login` | — | Login en dos paneles. Con `DEMO_MODE` (`GET /api/demo/info`): aviso de entorno de demostración y tarjetas de usuarios demo con su escenario (clientes en `/login`, agentes y admin en `/login?perfil=agente`). La contraseña nunca está en el frontend: el aviso dice dónde está documentada. Con el modo apagado no hay aviso ni tarjetas. |
| `/chat` | customer | Chat con todos los bloques del contrato. Una sola bienvenida (Banky se presenta y dice qué puede hacer); la opción de voz solo aparece si `GET /api/voice/config` la habilita (apagada: ni botón ni aviso); fase real del turno; respuestas rápidas como lista de opciones cuando el asistente pide un dato, no encuentra coincidencias o propone temas (`start_topic`); sin contadores de intentos; RCL copiable; "¿Te ayudé?" al cerrar. |
| `/conversaciones` | customer | "Mis conversaciones": `GET /api/me/conversations` (paginado) con fecha, resumen, estado y referencias. El detalle (`/conversaciones/:id`) es de solo lectura y "Continuar sobre este tema" abre una conversación enlazada. |
| `/movimientos` | customer | `GET /api/me/transactions` con filtros. "No reconozco este cargo" abre el chat con esa disputa (`dispute_transaction_id`). |
| `/reclamos` | customer | `GET /api/me/cases`. |
| `/sistema` | — | Guía viva del sistema de diseño: tokens y botones ([docs/design-system.md](docs/design-system.md)). |
| `/admin` | admin | Panel: tarjetas de SLO con presupuesto de error y violaciones, resultados con n/N, costo de LLM y voz frente al presupuesto, latencia p50/p95 por endpoint y por nodo, conversaciones recientes, visor de logs con filtros, mejora continua (enlaces a los PR y reportes en GitHub; `VITE_REPO_URL`) y ROI etiquetado como estimación. |
| `/agentes` | analyst, admin | Portal de agentes: bandeja de tickets (`GET /api/tickets`) con filtros por estado, prioridad, SLA y asignado; pestaña de reclamos. Entrada por `/login?perfil=agente`. |
| `/agentes/tickets/:id` | analyst, admin | Detalle: lo que dice el cliente frente a los hechos verificados, preguntas pendientes, política aplicada, conversación, línea de tiempo de trazas (LLM / ML / código con latencia y costo), tomar el ticket, cambiar el estado y notas internas. |
| `/agentes/trazas/:turnId` | analyst, admin | Traza completa de un turno, con la entrada y la salida de cada paso. |

## Comportamiento que pide el contrato

- **Bloques:** un componente por tipo en [BlockView.tsx](src/components/blocks/BlockView.tsx).
  - Incluye `quick_replies` ("¿algo más?"), `candidate_list` con `multi_select` (sugeridos preseleccionados, "Todos estos" y "Ninguno") y `result` con `items[]`.
  - Montos, fechas y estados se muestran tal como vienen formateados del backend (`amount_label`, `date_label`, `status_label`).
- **"Listo" solo con un `result` con `verified: true`.** Los botones de turnos anteriores se desactivan y cada botón se deshabilita al primer clic. Cada turno lleva su `Idempotency-Key`, y un reintento reusa la misma.
- **Conversación cerrada:** si el 409 `conversation_closed` llega con un mensaje, se crea una conversación **enlazada** (`previous_conversation_id`) y se reenvía el mensaje, sin mostrar el error, igual que `scripts/chat_cli.py`.
- **Errores:**
  - `422 message_too_long`: aviso amable. El campo además corta en 2.000 caracteres y muestra los que quedan.
  - `429`: cuenta regresiva con `Retry-After`; el envío queda deshabilitado mientras corre.
  - `401`: vuelve al login con "tu sesión venció".
  - Todos los errores muestran el `X-Request-ID` como **código de referencia**.
- **Espera de cada turno:** [ThinkingIndicator.tsx](src/components/ThinkingIndicator.tsx) muestra la fase REAL que publica el backend (`GET /api/conversations/{id}/phase`); sin dato, el texto neutro. Nunca adivina por tiempo.
- **Banky** ([Banky.tsx](src/components/Banky.tsx)): mascota de diseño propio, SVG animado con CSS. Estados: saludo, escuchando, pensando (`understanding`), buscando (`searching_transactions`), revisando política (`checking_policy`), escribiendo (`writing`), feliz (resultado verificado), empático (aviso o resultado no verificado) y pasando a una persona (`handoff_notice`). El estado sale de la fase real o de los bloques del turno. Con `prefers-reduced-motion` queda estático; con `label` tiene nombre accesible.
- **Modo voz** ([VoiceComposer.tsx](src/components/VoiceComposer.tsx)), solo si `GET /api/voice/config` dice `enabled`: explicación antes de pedir el micrófono, pulsar o mantener para hablar, onda con el nivel real del micrófono, transcripción visible y editable antes de enviar (`via: "voice"`), respuesta leída en voz alta (`POST /api/voice/tts`) con el texto en pantalla como subtítulos. Las confirmaciones siguen siendo tarjetas con botón. Permiso rechazado o cualquier error de voz: aviso y vuelta al texto.
- **Accesibilidad:**
  - Contraste AA verificado por test sobre los tokens (`src/styles/__tests__/tokens.test.ts`).
  - Foco visible; botones de al menos 44 px; "saltar al contenido".
  - `role="log"` con `aria-live="polite"` en el chat.
  - Etiquetas en todos los controles y movimiento reducido si el sistema lo pide.
- **Seguridad:** el texto de los bloques es texto plano (React escapa; no se usa `dangerouslySetInnerHTML`). No hay HTML del backend.

## Estructura

```
src/api/        types.ts (contrato), client.ts (fetch, CSRF, errores, conversación enlazada)
src/components/ BlockView, ThinkingIndicator, ErrorNote
src/pages/      Landing, Login, Chat, Conversations, Movements, Cases, Tickets, Ticket, Trace, StyleGuide
src/lib/        i18n (es/pt, usuarios demo), session (sesión y sesión vencida)
```

Tests (Vitest + Testing Library): cliente HTTP (CSRF, Idempotency-Key, errores, 409 enlazado) y bloques (selección múltiple, botones inactivos, "Verificado" solo con `verified`, sin HTML).
