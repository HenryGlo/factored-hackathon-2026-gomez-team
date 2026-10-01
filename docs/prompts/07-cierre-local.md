# Prompt 07 — Cierre en local (ML, evaluación, analítica) y luego frontend

Ejecuta los bloques EN ORDEN. Modo autónomo con estas reglas:
- Una rama y un PR por bloque, Conventional Commits en inglés, con su issue enlazado
  ("Closes #N").
- Antes de cada merge: suite completa, CI en verde y harness con 0 inseguros.
- El split test (el escrito a mano) NO se usa para entrenar, elegir umbrales ni ajustar
  nada. Solo se corre en la corrida final, con `--i-know-this-is-final`.
- Ningún número sin ejecución que lo respalde. Porcentajes siempre con n/N. Si algo no
  mejora, se dice tal cual.
- No se suben al repo datos del dataset, secretos ni modelos pesados.
- Al terminar cada bloque: tag (v0.6.0, v0.7.0, …), CHANGELOG y docs/STATUS.md.
- Nada de despliegue: Render va al final, con límite el sábado al mediodía.
- Detente SOLO donde se indica DETENTE.

---

## Bloque 1 — Clasificador de intención en cascada (issue #17)

Pregunta del experimento: ¿un clasificador pequeño puede atender los turnos rutinarios
y dejar el LLM solo para los difíciles, con menos costo y la misma calidad?

1. Datos
   - Fuentes: mensajes de dev y dev_paraphrase, más sintéticos generados para
     entrenamiento. Los sintéticos los genera Sonnet a partir de una plantilla
     documentada, se revisan con reglas y se marcan como `synthetic`.
   - Las paráfrasis de un mismo caso van al mismo fold, para que no haya fuga entre
     entrenamiento y validación. Se hace validación cruzada estratificada por intención.
   - Se publica la distribución de clases y se explica cómo se manejan las clases
     raras.
2. Modelos a comparar, todos con la misma interfaz `IntentClassifier`:
   - palabras clave (el baseline actual);
   - TF-IDF de palabras y de caracteres (3–5) + regresión logística;
   - lo mismo con calibración (CalibratedClassifierCV con isotónica o sigmoide, según
     el tamaño de los datos);
   - Haiku como única vía (el sistema actual);
   - cascada: si la probabilidad del modelo calibrado es mayor o igual a τ, se usa su
     respuesta; si no, se llama a Haiku.
3. Umbral τ: elegido por costo esperado en validación, con una curva de cobertura vs.
   error (qué fracción de turnos se resuelve sin LLM y con qué error). Los costos de
   cada tipo de error se documentan como supuesto del equipo; confundir
   `cargo_no_reconocido` con otra intención cuesta más.
4. Métricas:
   - macro-F1 y matriz de confusión;
   - Brier y diagrama de confiabilidad (ECE);
   - % de turnos que llegan al LLM;
   - costo por caso, comparado con `sistema_api` ($0.0079 por caso);
   - latencia p50/p95;
   - resultados inseguros del harness.
5. Integración:
   - la variante `sistema_cascade` se añade al harness y se corre sobre dev y
     dev_paraphrase con la API real;
   - el modelo se serializa en `models/intent/` con versión, hash de los datos de
     entrenamiento y fecha;
   - se escribe un model card con propósito, datos, métricas, límites y cuándo
     reentrenar;
   - si el archivo del modelo falta o falla al cargar, se vuelve a Haiku y la traza lo
     registra.
6. Seguimiento: MLflow local (`mlruns/`, en .gitignore) si no complica; si complica, un
   registro en `docs/experiments/` con hipótesis, configuración, métricas y conclusión.
   Cada corrida queda reproducible con un solo comando.

## Bloque 2 — Riesgo: calibración y política

1. Revisa en el data dictionary si existe una etiqueta de fraude o de contracargo. Si
   NO existe, DETENTE y explícame qué alternativas hay; no inventes etiquetas.
2. Si existe:
   - partición temporal: entrenamiento en lo antiguo, prueba en lo reciente;
   - compara tres opciones: el score crudo (bandas actuales), el score calibrado con
     isotónica y un modelo simple (regresión logística o LightGBM) con variables del
     movimiento, para el 20 % de movimientos sin score;
   - métricas: PR-AUC, Brier, confiabilidad y costo esperado por umbral.
3. Uso en la política: el riesgo SOLO cambia la ruta y la prioridad del caso (por
   ejemplo, riesgo alto + "no lo hice" → escalar a fraude con prioridad). El sistema
   nunca declara un fraude ni toma decisiones de dinero. "Movimiento anómalo" no es lo
   mismo que "fraude confirmado", y así se escribe en la UI y en el handoff.
4. Model card, experimento registrado y tests de la política.

## Bloque 3 — Clientes que dan rodeos (parte G) y pruebas manuales (parte F)

1. Casos multiturno de dev, en es/pt:
   - una historia larga antes del pedido real;
   - referencias indirectas ("el del súper de la semana pasada", "el que salió dos
     veces");
   - el cliente corrige el monto o la fecha a mitad del flujo;
   - cambia de movimiento después de confirmar;
   - cancela y retoma;
   - mezcla quejas con el pedido;
   - responde a una pregunta con otra pregunta;
   - mensajes muy cortos ("ese", "el otro", "no, el anterior").
2. Arregla en el controlador y en los prompts lo que falle. Cada arreglo lleva su test
   y su caso.
3. Parte F: `docs/manual-test-script.md`, un guion de 15–20 recorridos manuales con
   pasos y resultado esperado, para que cualquiera del equipo lo ejecute en el
   frontend.

## Bloque 4 — Analítica (Data Analytics, criterio de evaluación)

Solo preguntas operativas, nada decorativo. Cada gráfico responde una pregunta escrita
en su título.
1. Calidad de datos: reporte del ETL con nulos, duplicados, rangos, claves huérfanas,
   frescura y qué regla del contrato se aplicó a cada problema.
2. Demanda, desde el dataset:
   - ¿en qué categorías de comercio, canales y horarios se concentran los cargos que
     se parecen a los que se disputan?
   - ¿qué tan frecuentes son los montos repetidos o los cargos parecidos (lo que
     obliga a aclarar)?
   - ¿qué proporción de movimientos queda pendiente?
3. Operación, desde las trazas y los casos de evaluación:
   - resolución automática vs. aclaración vs. escalamiento, con n/N;
   - costo por caso correctamente atendido y por variante;
   - latencia por nodo.
4. ROI con supuestos explícitos y editables en config (costo por minuto de un agente
   humano, minutos por caso, % de casos automatizables): ahorro estimado y punto de
   equilibrio. Se presenta como estimación, no como resultado.
5. Endpoints `/api/admin/metrics/*` (rol analista o admin) para el panel futuro y un
   notebook en `analysis/` que regenera las figuras. Si el data analyst del equipo
   quiere hacerse cargo de este bloque, que lo haga desde su cuenta y con su propio PR.

## Bloque 5 — Cierre en local

1. Desde cero, `scripts/dev_up.sh --reset-demo` levanta todo sin pasos manuales.
2. Corrida completa del harness, con la API real, para todas las variantes (baseline,
   todo_llm, sistema_api, sistema_cascade) sobre dev y dev_paraphrase. Tabla final en
   `docs/evaluation.md`.
3. README: cómo correr todo en local en menos de 10 minutos.
4. Tag v0.9.0.
DETENTE y envíame la tabla final y las URL locales. Ahí empieza la fase de frontend.

---

## Bloque 6 — Frontend profesional (SOLO cuando yo lo indique)

Es el pase de diseño que ya te pasé: auditoría con capturas, tokens, chat, listas,
consola del analista, login, accesibilidad, y capturas antes/después con un PR por
pantalla.

## Bloque 7 — Lo que pedí ayer (SOLO cuando yo lo indique)

1. Landing del banco ficticio con Banky, la mascota animada:
   - estados idle, pensando, buscando y feliz, ligados a las fases reales del turno;
   - SVG o Lottie propio, nada que copie personajes existentes;
   - respeta prefers-reduced-motion.
2. Login separado para agentes humanos (rol analista) y bandeja de tickets: casos
   escalados con prioridad por riesgo, asignación, cambio de estado y nota interna,
   todo auditado en las trazas.
3. Panel admin con los endpoints del bloque 4: métricas de operación, costo de LLM por
   día, presupuesto consumido, latencia y la tabla de evaluación.
4. Opcional, si sobra tiempo: voz (entrada por micrófono y respuesta hablada), detrás de
   un feature flag y desactivada por defecto.
