# Guion del video de demostración

Tres recorridos, en este orden: **cargo claro**, **caso ambiguo** y **riesgo alto → un agente atiende el ticket → el admin ve
los SLO**. El script `frontend/scripts/demo.mjs` deja todo listo para grabar sin pasos manuales: revisa que el entorno esté
limpio, abre las ventanas con la sesión ya iniciada o graba los recorridos solo.

La contraseña demo llega solo por la variable de entorno `DEMO_PASSWORD`: **no se teclea frente a la cámara** ni está en el
repo. Los mensajes del cliente se arman con un movimiento real de "Mis movimientos" de ese usuario; no hay datos inventados.

## Preparación

```bash
scripts/prodlike_up.sh                         # toma lo último de main (URL: https://localhost:8443)
cd frontend && npm ci && npx playwright install chromium
export DEMO_PASSWORD=…                         # la de ~/.factored-prodlike/env; no la escribas en un archivo del repo
export BASE_URL=https://localhost:8443

npm run demo check                             # ¿está todo listo para grabar?
```

`check` debe terminar en **"LISTO para grabar"**. Revisa que el backend responda, que el modo demostración esté encendido y
que los tres clientes del video tengan movimientos y **ningún reclamo previo**.

Si dice que un usuario ya tiene reclamos, hay que limpiar la demo. Borra todo lo que creó la app en ese entorno:

- Prodlike: `scripts/prodlike_down.sh --purge && scripts/prodlike_up.sh` (vuelve a cargar los datos demo; tarda unos minutos).
- Desarrollo: `scripts/dev_up.sh --reset-demo`.

Usuarios del video (los `_2`, porque la prueba de humo usa los `_1`). Se pueden cambiar con `DEMO_CLARO`, `DEMO_AMBIGUO` y
`DEMO_RIESGO`.

| Papel | Usuario | Entra por |
|---|---|---|
| Cliente con un cargo claro | `demo_cargo_claro_2` | "Tengo un reclamo" |
| Cliente con cargos parecidos | `demo_cargos_parecidos_2` | "Tengo un reclamo" |
| Cliente con un cargo de riesgo alto | `demo_fraude_alto_2` | "Tengo un reclamo" |
| Agente de soporte | `analista_1` | "Inicio de sesión de agentes de soporte" |
| Administrador | `admin_1` | "Inicio de sesión de agentes de soporte" |

## Dos formas de grabar

**A. Grabación automática** (sirve de respaldo y para los cortes de las diapositivas):

```bash
npm run demo record        # deja frontend/demo-videos/*.webm (1440×900), uno por recorrido
```

Escribe a ritmo humano, espera cada turno real (no hay tiempos fijos) y se detiene unos segundos en cada pantalla que hay que
mostrar. Con el LLM real cada turno tarda lo que tarde: el indicador y Banky muestran la fase verdadera.

**B. Grabación a mano** (para narrar encima):

```bash
npm run demo open          # abre 5 ventanas con la sesión ya iniciada, cada una en su pantalla de partida
```

Graba la pantalla con la herramienta que prefieras y sigue el guion de clics de abajo. Cada ventana es una sesión distinta:
no hace falta cerrar sesión entre recorridos.

## Guion de clics

En los tres recorridos del cliente, Banky se presenta y pregunta si quieres escribir o hablar. Con la voz apagada, el botón
de voz aparece deshabilitado y explica el motivo: es parte de lo que se muestra.

### 1. Cargo claro (`demo_cargo_claro_2`)

Con `npm run demo open` la sesión ya está iniciada y la ventana está en el chat: empieza en el paso 3. Los pasos 1 y 2 son
para mostrar la entrada desde la landing (la grabación automática los incluye y rellena la contraseña sola).

| # | Clic o texto | Qué se ve | Qué decir |
|---|---|---|---|
| 1 | Landing → **Tengo un reclamo** | La landing de BankyFicticious y el login | Qué puede y qué no puede hacer Banky; datos ficticios |
| 2 | Tarjeta del usuario demo → contraseña → **Entrar** | El chat: Banky se presenta | La identidad sale de la sesión, no de lo que el cliente escriba |
| 3 | **Escribir** | Queda el modo texto | — |
| 4 | Escribir: "No reconozco el cargo de *(monto)* del *(fecha)* en *(comercio)*" (un movimiento de "Movimientos") | Banky pasa por sus fases reales (pensando, buscando) y muestra **ese** movimiento | La búsqueda la hace el código sobre los datos; el LLM no inventa movimientos |
| 5 | **Sí, es este** | Tarjeta de confirmación con "no es una devolución" | Nada se ejecuta sin el botón: escribir "sí" no basta |
| 6 | **Confirmar** | Resultado verde **Verificado** con la referencia `RCL-…`; Banky feliz | "Verificado" solo aparece cuando el sistema comprobó que el reclamo existe |
| 7 | **No, gracias** → 👍 **Sí, me ayudó** → **Enviar valoración** | "¿Te ayudé?" y el agradecimiento | La valoración alimenta el ciclo de mejora |
| 8 | **Reclamos** | El reclamo con su avance (registrado → en revisión → resuelto) | — |
| 9 | **Conversaciones** | La conversación con su resumen y la `RCL-…` | El resumen se arma con hechos, no con texto libre del LLM |

### 2. Caso ambiguo (`demo_cargos_parecidos_2`)

| # | Clic o texto | Qué se ve | Qué decir |
|---|---|---|---|
| 1 | Escribir: "No reconozco un cargo en mi tarjeta" | La tarjeta **"pide un dato"**: el asistente no muestra movimientos; pregunta por el monto, el comercio o la fecha | Si falta un dato, lo pide: no adivina ni llama "parecidos" a movimientos cualquiera |
| 2 | Escribir: "Es uno de como *(monto)*" (el monto de un cargo de "Movimientos") | Los cargos que coinciden con ese monto y la pregunta "¿cuál es?" (con uno solo, pregunta si es ese) | Solo muestra lo que coincide con lo que dijo el cliente, y dice con qué coincidió |
| 3 | Elegir el cargo → **Sí, es este** → **Confirmar** | Resultado verificado con su `RCL-…` | El mismo control que en el recorrido 1 |
| 4 | (Opcional, en otra conversación) Escribir: "Tengo un cargo no reconocido en Facebook" | La tarjeta **"sin coincidencias"**: dice que no encontró cargos de Facebook hasta la fecha de los datos y ofrece dar otro dato, ver los movimientos o hablar con una persona | Nunca afirma algo que los datos no respaldan |

### 3. Riesgo alto → agente → admin

**3a. Cliente (`demo_fraude_alto_2`)**

| # | Clic o texto | Qué se ve | Qué decir |
|---|---|---|---|
| 1 | Escribir: "No reconozco el cargo de *(monto)* del *(fecha)*, yo no lo hice" (el movimiento más reciente) | Banky revisa la política y muestra el aviso **"Te pasamos con una persona"** con la referencia `ATN-…` | Riesgo alto y "no lo hice": no se abre un reclamo automático, pasa al equipo de fraude |
| 2 | Copiar la referencia `ATN-…` | — | Es la que verá el agente |

**3b. Agente (`analista_1`)**

| # | Clic o texto | Qué se ve | Qué decir |
|---|---|---|---|
| 1 | Landing → **Inicio de sesión de agentes de soporte** → entrar | La bandeja: contadores por estado y el ticket **Urgente** arriba, con su SLA | El orden es por prioridad y antigüedad |
| 2 | Abrir el ticket `ATN-…` | **Lo que dice el cliente** junto a **Hechos verificados**; preguntas pendientes; política aplicada | El agente no relee la conversación: recibe hechos verificados y lo que falta resolver |
| 3 | Bajar a **Línea de tiempo de trazas** | Cada paso del turno: LLM, ML o código, con latencia y costo | Todo queda trazado |
| 4 | **Tomar el ticket** → estado **En curso** → **Guardar** | Asignado al agente; estado nuevo | — |
| 5 | Escribir una nota interna → **Agregar nota** | El historial con la asignación, el cambio de estado y la nota | Cada cambio queda auditado; la nota nunca llega al cliente |

**3c. Admin (`admin_1`)**

| # | Clic o texto | Qué se ve | Qué decir |
|---|---|---|---|
| 1 | Entrar por el acceso de agentes | El panel: tres tarjetas de SLO con "Cumple / No cumple" y el presupuesto de error | Objetivos y ventanas son supuestos del equipo |
| 2 | Bajar a **¿Cómo terminan las conversaciones?** y **¿Cuánto gastamos hoy frente al presupuesto?** | Resultados con n/N y el costo del día | Cada bloque responde la pregunta de su título |
| 3 | Bajar a latencia, conversaciones recientes y **¿Qué registró el sistema?** | p50/p95 por endpoint y por nodo; logs sin textos del cliente | — |
| 4 | **Mejora continua** | Qué hace el ciclo con Opus y los enlaces a los PR propuestos | Nunca fusiona solo: decide una persona |

## Antes de publicar el video

- En prodlike el LLM es `claude -p`: **la latencia y el costo que se ven no son los de producción**. Si el video muestra
  tiempos, grábalo sobre la versión desplegada con la API o dilo en la narración.
- Si en el recorrido 3 el script avisa *"en este entorno el cargo no escaló por riesgo alto"*, ese usuario no tiene un cargo
  con señal de riesgo alta en esa base (pasa con el dataset sintético de pruebas). El script pide una persona para poder
  seguir, pero **esa toma no sirve para el video**: grábalo en prodlike, donde la prueba de humo confirma el ticket urgente.
- Revisa que no aparezca ninguna contraseña, ni la barra de direcciones con datos personales, ni otra pestaña.
