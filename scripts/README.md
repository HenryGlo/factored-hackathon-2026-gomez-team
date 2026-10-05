# scripts/

## Propósito

Utilidades de desarrollo que no pertenecen a un componente.

## Scripts

- `chat_cli.py`: chat de terminal contra la API local: usuarios demo, bloques legibles, opciones numeradas (también varias, "1,3"), `/traza` y `/nuevo`. Si la conversación se cerró, abre una enlazada sin mostrar el error.
- `compare_api.sh`: comparación `claude -p` frente a la API de Claude sobre dev (variante `sistema_api`, 1 repetición). Uso: `ANTHROPIC_API_KEY=... scripts/compare_api.sh`.
- `eval_generated.sh`: flujos de conversación generados a escala con un comando. Por defecto gratis (lote de 5.000 si no hay, muestra de 200 con LLM falso); `--llm` usa `claude -p` y `--api` la API. Guarda flujos y resultados en el esquema `eval` de la base local ([eval/generated/README.md](../eval/generated/README.md)).
- `seed_synthetic_history.py`: siembra conversaciones **sintéticas** (marcadas con `origin = 'synthetic'`) en la base local para dar volumen a la analítica del administrador y al panel del agente: corre flujos generados contra el sistema real, reparte las fechas en 30 días y agrega valoraciones. `--reset` las borra. Nunca usa los clientes demo ni una base que no sea local.
- `make_writer_kit.py`: fichas de escenario para redactar a mano el split test ([eval/manual/README.md](../eval/manual/README.md)).

## Qué irá aquí

**[Propuesta]**

- Descarga del dataset desde el bucket a `RAW_DATA_DIR`, leyendo credenciales del entorno.
- Preparación del entorno local: crear la base, correr el ETL con el subconjunto de demo, cargar artefactos de modelos.
- Selección de clientes de demo por escenario (normal, ambiguo, requiere humano).
- Verificación de enlaces relativos en la documentación.
- Chequeo previo a publicar: que no haya datos, `.env` ni credenciales en el árbol de git.

## Entradas y salidas

Variables de [.env.example](../.env.example). Salida según el script.

## Dependencias

[data_pipeline/](../data_pipeline/README.md), [backend/](../backend/README.md).

## Responsable sugerido

Software developer.
