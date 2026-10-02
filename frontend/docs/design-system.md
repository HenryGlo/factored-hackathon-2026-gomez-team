# Sistema de diseño y auditoría (prompt 08, B0)

Dirección: **cálido y cercano** (elegida el 2026-10-02 entre tres propuestas). Tonos crema y verde profundo, un acento de sol
(mango) para Banky y los momentos que celebran, formas orgánicas, botones que se hunden y sombras "de tinta" (desplazadas, sin
desenfoque). Banky es el protagonista. Guía viva: `/sistema` ([StyleGuidePage.tsx](../src/pages/StyleGuidePage.tsx)).

## Auditoría de las pantallas (2026-10-01)

Capturas con Playwright en escritorio (1440 px) y celular (390 px): `scripts/screenshots.mjs`. Antes y después en
`docs/screenshots/` (raíz del repo).

| # | Pantalla | Problema | Dónde se arregla |
|---|---|---|---|
| 1 | Mis movimientos (celular) | El nombre del comercio se parte letra por letra: el botón "No reconozco este cargo" le quita el ancho. | **B0** (corregido) |
| 2 | Todas | Tipografía del sistema, sin jerarquía ni personalidad; títulos y texto iguales. | **B0** (Space Grotesk + Inter) |
| 3 | Todas | Botones poco claros: el fantasma y el secundario se parecen, sin estado hover/active propio y el deshabilitado solo baja la opacidad. | **B0** |
| 4 | Todas | Bordes de campos casi invisibles (1,3:1 contra el fondo). | **B0** (`--line-strong`, 3:1) |
| 5 | Todas | Colores sueltos en el CSS (morado, azul, ámbar) sin tokens ni verificación de contraste. | **B0** (tokens + test) |
| 6 | Entrada | No hay landing: la app abre en un login sin explicar qué es ni qué hace el asistente. | B1 |
| 7 | Login | La lista de usuarios demo ocupa más que el formulario; mezcla clientes y agentes. | B1 / B7 |
| 8 | Todas | La marca es "Banco Demo" con una "B": sin identidad. | B1 (BankyFicticious), B2 (Banky) |
| 9 | Chat | El asistente no tiene presencia: tres puntos como única señal de espera. | B2, B5 |
| 10 | Chat | La lista de candidatos muestra "1/3" (ronda de aclaración) sin explicar qué es. | B5 |
| 11 | Chat | Sin valoración al cerrar ni RCL copiable. | B5 |
| 12 | Chat (escritorio) | Mucho espacio vacío; la conversación queda en una columna angosta sin contexto. | B5 |
| 13 | Mis movimientos | El período se muestra como `2026-05-19 → 2026-06-18` (formato técnico). | B6 |
| 14 | Mis reclamos | Lista plana, sin línea de tiempo ni enlace a la conversación. | B6 |
| 15 | Consola | Estado vacío con un guion ("—"); solo conoce prioridades `alta` y `media`; no hay tickets, SLA ni asignación. | B7 |
| 16 | Consola | No existe el panel admin (SLO, costos, logs). | B8 |
| 17 | Todas | "Saltar al contenido" solo en español; textos pt por revisar. | B9 |

## Tokens

Fuente única: [src/styles/tokens.css](../src/styles/tokens.css). Los componentes no usan valores sueltos.

- **Color.** Claras (crema): `--paper`, `--surface`, `--surface-2`, `--text` (verde profundo), `--muted`, `--line`, `--line-strong`.
  Oscuras (verde): `--ink-900…600`, `--on-dark`, `--on-dark-muted`. Acento: `--accent` (verde, acciones y enlaces), `--accent-soft`,
  `--sun` / `--accent-bright` (mango: Banky, números, lo que celebra) y `--on-accent`. Semánticos: `--ok`, `--warn`, `--err`, `--info`.
- **Contraste AA verificado por test** ([tokens.test.ts](../src/styles/__tests__/tokens.test.ts)): pares de texto a 4,5:1 o más y
  bordes de controles y foco a 3:1 o más. Además, axe en todas las pantallas (`npm run e2e`).
- **Banky** se viste con `--banky-ink`, `--banky-edge`, `--banky-visor` y `--banky-glow` (sobre verde, `.on-dark` lo vuelve crema).
- **Tipografía.** Bricolage Grotesque (títulos) e Inter (texto), variables y autoalojadas (`@fontsource-variable`).
- **Radios** grandes (`--r-md` 18 px … `--r-xl` 40 px). **Sombras** `--shadow-1` y `--shadow-2` de tinta; `--shadow-3` suave.
- **Movimiento.** `--dur-fast` 120 ms, `--dur-base` 200 ms, `--dur-slow` 360 ms; curvas `--ease-out`, `--ease-in-out` y
  `--ease-spring` (rebote corto). Qué se mueve: Banky flota y saluda, la forma del hero respira, la ola se desplaza, los bloques
  de la landing aparecen al entrar en pantalla, los mensajes y las tarjetas hacen un pequeño rebote, el resultado verificado
  celebra una vez, los botones se hunden al pulsarlos. **Con `prefers-reduced-motion` todo queda en su pose final**, sin
  animaciones ni transiciones.

## Botones

| Clase | Uso | Estados |
|---|---|---|
| `.btn.primary` | La acción de la pantalla. Una por vista. | hover (más oscuro y sombra), active (baja 1 px), focus-visible (anillo), disabled |
| `.btn.secondary` | La alternativa a la primaria. | borde del acento; hover con fondo suave |
| `.btn.ghost` | Acciones menores en barras y listas. | sin borde; hover con fondo suave |
| `.btn` | Neutro (dentro de tarjetas). | borde `--line-strong` |

Tamaños: normal (44 px mínimo, área táctil), `.small` (34 px, solo en barras densas de escritorio) y `.large` (52 px, llamadas a la
acción). El deshabilitado cambia fondo, borde y texto: no depende solo de la opacidad.
