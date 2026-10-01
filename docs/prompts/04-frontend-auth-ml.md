# Prompt 04 — Frontend, autenticación, casos de prueba y entrenamiento

Eres el ingeniero full stack del proyecto de disputas del Factored AI & Data Hackathon
2026. Antes de empezar lee README.md, docs/ (architecture, conversation-flow,
api-contract, tools-contract, policies, handoff-schema, evaluation, decisions/,
data/postgres.md) y docs/prompts/03-pipeline-harness.md, y revisa el estado real del
código. Este prompt depende de que el backend ya funcione sobre PostgreSQL (fase 1 del
prompt 03). Si no es así, detente y dímelo. Si algo aquí contradice los documentos,
pregúntame antes de elegir.

Trabaja por partes y detente en cada punto de control para mostrarme el resultado.

## Parte A — Autenticación

Requisito del reto: la identidad debe venir de una sesión confiable; un número de
cliente o documento por sí solo no prueba identidad.

- Dos roles: `customer` (cliente del banco) y `analyst` (consola del banco).
- Usuarios demo: el script `scripts/seed_demo_users.py` crea credenciales para los
  clientes del subconjunto demo que cubren los escenarios de prueba (elegidos con SQL
  documentado) y 2 analistas. Guarda en app.users: username, hash de contraseña con
  argon2 (o bcrypt), rol, customer_id (solo para clientes), activo. La contraseña demo
  se lee de .env (`DEMO_PASSWORD`); nunca en el repo ni en los documentos.
- Login: `POST /api/auth/login` → sesión en app.sessions con expiración (30 min por
  inactividad, configurable) y token en cookie httpOnly, Secure en producción,
  SameSite=Lax. Protección CSRF para peticiones que cambian estado (doble token o
  cabecera personalizada). `POST /api/auth/logout` invalida la sesión.
  `GET /api/auth/me` devuelve rol y display_name.
- Limitar intentos fallidos de login (por usuario e IP) y registrar los eventos.
- El backend toma customer_id SIEMPRE de la sesión. Ningún endpoint lo acepta del
  cliente. Los endpoints de consola exigen rol analyst y usan el usuario de BD de solo
  lectura cuando no escriben.
- Sesión expirada a mitad de una confirmación: la acción no se ejecuta, el frontend
  pide volver a entrar y la conversación se puede retomar sin ejecutar nada pendiente.
- Tests: acceso sin sesión, rol incorrecto, sesión expirada, token de confirmación de
  otra sesión, intento de consultar datos de otro cliente.
Punto de control A.

## Parte B — Consulta de movimientos (solo lectura)

Amplía el flujo con una intención `consulta_movimientos`: "¿cuáles fueron mis últimos
movimientos?", "¿cuánto gasté en Oxxo este mes?".
- Nueva tool de solo lectura sobre ref.transactions filtrada por sesión, con filtros
  de fecha, comercio, monto y estado, y límite de resultados.
- Nuevo bloque de UI `transaction_list`. Las cifras (totales, conteos) las calcula el
  código; el LLM solo las redacta.
- Desde cualquier movimiento listado, el cliente puede tocar "No reconozco este cargo":
  inicia el flujo de disputa con esa transacción preseleccionada, pero sigue pasando por
  política, confirmación y verificación.
- Actualiza docs/api-contract.md y docs/conversation-flow.md.

## Parte C — LLM con `claude -p`

Usa la capa LLMClient existente (ClaudeCLIClient). Modelos por nodo, configurables:
- Haiku: intent (solo cuando el clasificador entrenado duda; ver Parte E), extract,
  clarify, confirm y la redacción de consultas de movimientos.
- Sonnet: explain y handoff_summary.
Mantén LLM_PROVIDER=fake para tests y demos sin conexión. Muestra en la traza qué nodos
llamaron al LLM, con qué modelo, latencia y costo estimado.

## Parte D — Frontend "bonito pero sencillo"

Stack: React + Vite + TypeScript. CSS propio o Tailwind, sin librerías de componentes
pesadas. Tipos que reflejen exactamente docs/api-contract.md.

Dirección visual:
- Sobria y confiable, como una app bancaria: fondo claro, un solo color de acento,
  tipografía legible, espaciado generoso, bordes suaves. Modo oscuro opcional.
- Responsive: funciona bien en un celular (el chat es la pantalla principal).
- Accesible: contraste AA, foco visible con teclado, etiquetas en los botones,
  aria-live en los mensajes nuevos.
- Textos de interfaz en español y portugués según el idioma de la conversación.
- Estados cuidados: cargando, vacío, error con reintento, sesión expirada.

Pantallas del cliente:
1. Login (con aviso visible "entorno de demostración, datos ficticios").
2. Chat: mensajes, un componente por tipo de bloque, respuestas rápidas, indicador de
   "buscando movimientos…" mientras espera, aviso de fecha de los datos (data_as_of).
3. Mis movimientos: lista con filtros y el botón "No reconozco este cargo".
4. Mis reclamos: estado de cada reclamo creado.

Pantallas de la consola (rol analyst):
5. Bandeja de reclamos y handoffs con filtros.
6. Detalle de handoff: lo que afirma el cliente frente a lo verificado; acciones
   confirmadas; preguntas abiertas.
7. Visor de trazas de un turno: nodo, tipo (LLM / ML / código), modelo, latencia,
   entrada y salida.

Reglas que no se pueden romper:
- Nunca mostrar "listo" sin un bloque result con verified: true.
- Deshabilitar el botón al primer clic; enviar confirmation_token e Idempotency-Key;
  inactivar los botones de turnos anteriores.
- Texto de los bloques como texto plano (nada de HTML inyectado).
- Montos desde strings decimales, formateados por idioma; nunca float.
- Nunca decir "reembolsado" ni "aprobado": abrir un reclamo no es una devolución.
Punto de control D: capturas de las pantallas principales en celular y escritorio.

## Parte E — Entrenamiento (notebook + script reproducible)

Estructura: el notebook es para explorar y reportar; el artefacto que usa la app sale
de un script. El notebook importa y llama a las mismas funciones del script.

E1. Clasificador de intención en cascada
- Datos:
  - Semilla escrita por el equipo: ejemplos por intención (es/pt), incluidos negativos
    difíciles ("no reconozco la app nueva", "quiero reconocer a un empleado").
  - Aumento con `claude -p --model haiku` para parafrasear esos ejemplos (variaciones de
    registro, errores de tipeo, regionalismos de México, Colombia y Argentina y
    portugués de Brasil). Guarda qué ejemplos son generados; revisa a mano una muestra
    y reporta cuántos se corrigieron o descartaron.
  - Nada de datos reales de clientes en los prompts de generación.
- Splits: separa por ejemplo semilla (las paráfrasis de un mismo ejemplo quedan en el
  mismo split) para evitar leakage. El test final es el set escrito a mano en
  eval/cases/test (no se usa para entrenar ni ajustar).
- Modelos a comparar: reglas de palabras clave, TF-IDF (palabras + n-gramas de
  caracteres) + regresión logística calibrada, Haiku zero-shot y la cascada
  (el clasificador responde si su probabilidad calibrada supera un umbral; si no, Haiku).
- Métricas: macro-F1, recall de cargo_no_reconocido, resultados por idioma, % de
  mensajes que llegan a Haiku, costo y latencia por mensaje. Elige el umbral de la
  cascada con validación, no con test.
- `ml/intent/train.py` produce `ml/intent/artifacts/intent_v<N>.joblib` + model card
  (datos, fecha, métricas, umbral, hash del dataset). Notebook:
  `ml/intent/intent_training.ipynb`.
- Conéctalo al backend como implementación de IntentClassifier.

E2. Calibración del riesgo de fraude
- Con ref.transactions: calibra fraud_score contra is_fraud (isotónica o Platt) con
  split temporal. Reporta PR-AUC, curva de calibración y Brier.
- Elige el umbral de "bloquear y escalar" minimizando el costo esperado con costos
  explícitos y documentados como supuestos (bloquear una tarjeta legítima vs dejar
  pasar un fraude vs un handoff).
- Advertencia a documentar: is_fraud y fraud_score son sintéticos; el umbral ilustra el
  método, no una política real.
- `ml/risk/train.py` → artefacto versionado + model card; notebook
  `ml/risk/risk_calibration.ipynb`. Conéctalo como implementación de RiskModel.

E3. Medición
Corre el harness del prompt 03 con los baselines y con los modelos nuevos (split dev) y
compara en una tabla. No toques el split test.
Punto de control E.

## Parte F — Casos de prueba manuales

Crea `docs/testing/manual-test-cases.md` con casos PRECISOS para que cualquier persona del
equipo los ejecute en la app. Busca con SQL clientes y transacciones reales de ref que
encajen con cada escenario y documenta la consulta usada.

Formato de cada caso:
- ID, título, categoría (normal, ambiguo, humano, adversario, fallo, auth), idioma.
- Precondiciones: usuario demo (username, la contraseña es DEMO_PASSWORD de .env),
  datos relevantes del cliente (IDs de transacciones, montos, fechas, estados).
- Pasos: mensajes exactos a escribir y botones a tocar, en orden.
- Resultado esperado: estado final, bloques que deben aparecer, qué NO debe pasar.
- Verificación en la base: consulta SQL que confirma el efecto (reclamo creado una
  sola vez, override de tarjeta, handoff con sus campos, ninguna fila creada).
- Casilla de resultado (pasa / falla / notas).

Cobertura mínima (español y portugués repartidos):
- Login correcto, contraseña errónea, bloqueo por intentos, logout, sesión expirada
  antes y durante una confirmación, acceso a la consola con rol cliente.
- Consulta de movimientos: últimos movimientos, gasto por comercio y mes, sin resultados.
- Disputa: cargo claro con reclamo creado; "$120" con varias candidatas; sin monto;
  comercio vago; fecha equivocada; cargo pendiente; cargo revertido; cliente que
  reconoce el cargo; reclamo ya existente; riesgo alto con bloqueo y handoff;
  cancelación; cambio de movimiento después de confirmar; iniciar desde "No reconozco
  este cargo" en la lista.
- Robustez: doble clic en confirmar; recargar la página a mitad del flujo; red caída
  (desconectar el backend); respuesta lenta del LLM.
- Seguridad: pedir un movimiento de otro cliente; prompt injection en el chat; texto con
  HTML o script en el mensaje (debe verse como texto); intentar usar un
  confirmation_token viejo.
- Consola: ver el handoff del caso de riesgo alto y su traza.
Agrega al inicio una tabla resumen (ID, título, categoría, idioma) y al final una
sección para registrar la corrida (fecha, versión, quién la ejecutó, resultados).

## Reglas generales
- No inventes métricas; todo número sale de una ejecución.
- No subas datos, artefactos grandes ni secretos al repo (revisa .gitignore).
- Actualiza los README de cada carpeta y docs/ con lo que cambió.
- Crea la rama feat/frontend-auth-ml. Al final muéstrame `git status` y el resumen del
  diff, y espera mi OK antes de hacer commit. No hagas push.
- Resumen final: comandos para levantar todo, capturas, tabla de la parte E, casos
  manuales ejecutados por ti con su resultado, y pendientes.

## Parte G — Clientes que dan muchas vueltas ("rodeos")

Algunos clientes cuentan una historia larga, mezclan varios montos y fechas o reparten
la información en varios mensajes. Implementa lo siguiente dentro de las partes que
correspondan; donde algo ya exista, revísalo y complétalo.

Clasificación (parte E1, cascada):
- Los mensajes que superen un largo configurable (por defecto ~300 caracteres) van
  directo al LLM, aunque el clasificador tenga alta probabilidad. Registra en la traza
  el motivo ("largo" o "duda").
- El prompt de intent indica identificar el pedido concreto e ignorar el relato.

Extracción:
- El esquema de extract distingue el cargo reclamado del contexto:
  amount_hint / merchant_hint / date_hint (el cargo que reclama) y
  montos_mencionados / comercios_mencionados (contexto que el cliente reconoce o solo
  menciona). El ranker usa solo los primeros.
- Las pistas se FUSIONAN entre turnos de la misma conversación: cada turno añade lo
  nuevo y una corrección explícita ("no, era el jueves") reemplaza el dato anterior.
  Guarda en la traza el estado de las pistas después de cada turno.

Controlador:
- Reformulación: si el mensaje es largo o la certeza es baja, antes de buscar el agente
  devuelve una línea con lo entendido ("Entiendo que no reconoces un cargo de unos $120
  de hoy. ¿Es así?") como plantilla es/pt. Si el cliente corrige, se actualizan las
  pistas. No reformular en mensajes cortos y claros.
- Si el cliente se desahoga, una sola frase breve de empatía y vuelta al problema.
- Tope de largo del mensaje (2.000 caracteres) con aviso amable si se supera, en backend
  y frontend.

Evaluación:
- Nueva categoría "rodeos" en eval/cases/dev con al menos 8 casos (es y pt): relato largo
  con el pedido al final; varios montos y solo uno reclamado; información repartida en
  3–4 mensajes; corrección a mitad de la conversación; desahogo antes del pedido.
- Añade fichas de esta categoría al kit del test escrito a mano.
- Métricas nuevas: turnos hasta identificar el cargo y aclaraciones innecesarias,
  desglosadas por categoría y variante.

Nota: las respuestas rápidas que mencionaba el borrador original ya existen (bloque
quick_replies); no las dupliques.
