# backend/llm/

## Propósito

Cliente único para la API de Claude, con prompts versionados y salidas estructuradas. Decisión de modelos: [ADR-0004](../../docs/decisions/0004-modelo-por-nodo.md).

## Qué irá aquí

**[Propuesta]**

- Cliente con reintentos acotados, timeout y registro de tokens, latencia y costo por llamada.
- Selección de modelo por nodo desde `LLM_MODEL_FAST` y `LLM_MODEL_REASONING`.
- Prompts en archivos Markdown versionados (por ejemplo `intent@v1`), en español y portugués cuando aplique; cada traza guarda la versión usada.
- Esquemas de salida para intención, extracción y confirmación.
- Separación estricta entre instrucciones del sistema y texto del cliente (defensa contra prompt injection).

## Entradas y salidas

Entrada: nombre del nodo, versión de prompt, variables. Salida: objeto validado o error tipado.

## Dependencias

API de Claude (`ANTHROPIC_API_KEY`).

## Responsable sugerido

Data scientist.
