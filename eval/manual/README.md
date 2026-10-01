# Redactar el test a mano: instrucciones

Vas a escribir conversaciones de clientes de un banco con un asistente de chat. El asistente ayuda a reclamar cargos que el cliente no reconoce, ver movimientos, bloquear tarjetas o pasar con una persona. Con tus textos medimos el sistema al final del proyecto, así que **importa que no lo conozcas**.

## Antes de empezar

- **No mires el código, los prompts ni los casos de `eval/cases/dev/`.** Tampoco pruebes tus mensajes en la app. Si ya los viste, avísanos y te damos otra tarea.
- Te damos una o varias **fichas** (`F01.html`, `F02.html`…). Cada ficha trae:
  - el escenario en una frase;
  - quién eres (el nombre con que te saluda el asistente) y tus tarjetas;
  - qué día es "hoy";
  - tus movimientos recientes, con el cargo del escenario marcado;
  - el resultado esperado.
- Escribe en el idioma de la ficha: español o portugués de Brasil.

## Cómo escribir

1. **Escribe como un cliente real desde el celular.** Con tus palabras: informal o formal, apurado, molesto, con errores de tipeo, con regionalismos, en uno o en varios mensajes. No copies las frases de la ficha.
2. **Varía el estilo entre fichas.** No uses la misma plantilla para todo.
3. **No siempre des todos los datos.** Un cliente real dice "un cobro raro de como 40 dólares", no "la compra de 40,00 USD del 12/06 en Farmacia X".
4. **Equivócate a veces.** Di un monto parecido pero no exacto, o una fecha corrida un par de días ("el lunes" cuando fue el martes). Algunas fichas lo piden; en las demás, hazlo si te sale natural.
5. **Sigue el escenario.** No cambies lo que quiere el cliente: si la ficha dice que reclamas el cargo marcado, reclama ese y no otro.

## La plantilla: `template.csv`

Una fila por mensaje del cliente. Columnas:

| Columna | Qué va |
|---|---|
| `ficha_id` | El id de la ficha, p. ej. `F07`. |
| `momento` | Cuándo envía el cliente ese mensaje (ver abajo). |
| `orden` | 1, 2, 3… dentro del mismo momento. |
| `mensaje` | El texto, tal cual lo escribiría el cliente. |
| `notas` | Opcional: algo que quieras que sepamos, p. ej. "me equivoqué de monto a propósito". |

El asistente puede responder de formas distintas, y tú no sabes cuál. Por eso cada mensaje lleva un **momento**:

| `momento` | Se envía… | Ejemplo |
|---|---|---|
| `inicio` | siempre, al empezar | "hola, tengo un cobro que no hice" |
| `si_pregunta` | solo si el asistente pregunta cuál cargo es o pide más datos | "fue el martes, creo" |
| `si_muestra_cargo` | solo si el asistente te muestra un cargo y pregunta si es ese | "sí, ese" / "no, no es ese" |
| `al_confirmar` | solo si el asistente pide confirmar una acción (registrar el reclamo, bloquear) | "mejor no, déjalo" |

Notas:

- Puedes dejar vacíos los momentos que no uses. Si no escribes nada para `si_muestra_cargo`, la prueba responde "sí" / "sim" por ti, salvo en las fichas que piden otra cosa.
- **Los botones los pulsa la prueba.** Por ejemplo, "Confirmar" o tocar el cargo en una lista. La ficha dice qué pulsa (en "Resultado esperado").
- Las filas `EJEMPLO` de la plantilla son solo un modelo; puedes borrarlas.

## Al terminar

Guarda el CSV y mándalo al equipo. No lo pongas en el repo. Alguien correrá `python -m eval.import_manual --csv <tu archivo> --check` para validar el formato (eso no ejecuta el sistema).
