"""Cliente LLM para producción: API de Claude con el SDK oficial `anthropic` (asíncrono).

Misma interfaz que el resto (`LLMClient.complete_json`); los nodos no cambian.

- **Salida estructurada:** `output_config.format = {"type": "json_schema", "schema": ...}`, según
  https://platform.claude.com/docs/en/build-with-claude/structured-outputs (consultada el 2026-09-30).
  - El esquema sale del modelo Pydantic del nodo con `anthropic.transform_schema`, que quita lo que la API no aplica
    (minLength, maxLength, maximum, pattern…) y lo deja como texto en la descripción.
  - Pydantic valida después con el modelo original, así esos límites se siguen exigiendo.
  - Los enums se comparan sin distinguir mayúsculas: la API no garantiza el casing. Antes de validar se reescribe
    el valor con el casing del esquema.
  - `stop_reason` `refusal` o `max_tokens`: la salida puede no cumplir el esquema → `LLMInvalidOutput`.
- **Prompt caching:** el system prompt va como bloque con `cache_control: ephemeral` (TTL de 5 minutos).
  - La API solo cachea desde un mínimo de tokens por modelo: 4.096 en Haiku 4.5 y 512 en Sonnet 5.5.
  - Debajo del mínimo no hay error; simplemente no se cachea. `usage` lo muestra y queda en la traza (raw.usage).
- **Errores:** `timeout` y `max_retries` del SDK desde la configuración. El SDK reintenta con backoff 408, 409, 429,
  5xx (incluido 529 overloaded) y errores de red, respetando `retry-after`. Agotados los intentos:
  - `APITimeoutError` → `LLMTimeout`;
  - conexión, 429, 5xx y errores de cuenta o configuración (401, 403, 404, 400) → `LLMUnavailable`;
  - salida que no cumple el esquema → `LLMInvalidOutput`, con un reintento propio si `retries` > 0.
- **Costo:** por llamada, desde `usage` y la tabla versionada `backend/config/llm_pricing.toml`.
- **Clave:** `ANTHROPIC_API_KEY` solo por entorno. Nunca en la configuración versionada ni en las trazas.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

import anthropic
from pydantic import BaseModel, ValidationError

from backend.app.llm.client import LLMClient, LLMError, LLMInvalidOutput, LLMResult, LLMTimeout, LLMUnavailable


def cost_usd(model_id: str, usage: Any, pricing: dict) -> float | None:
    """USD de una llamada. None si el modelo no está en la tabla de precios."""
    p = (pricing.get("models") or {}).get(model_id)
    if not p or usage is None:
        return None
    tokens = {"input": getattr(usage, "input_tokens", 0) or 0, "output": getattr(usage, "output_tokens", 0) or 0,
              "cache_write_5m": getattr(usage, "cache_creation_input_tokens", 0) or 0,
              "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0}
    return round(sum(tokens[k] * p[k] for k in tokens) / 1_000_000, 8)


def _resolve(node: dict, defs: dict) -> dict:
    while "$ref" in node:
        node = defs[node["$ref"].split("/")[-1]]
    return node


def normalize_enums(value: Any, node: dict, defs: dict) -> Any:
    """Reescribe strings de enums con el casing del esquema (la API puede devolver 'Alto' por 'alto')."""
    node = _resolve(node, defs)
    if isinstance(value, str) and "enum" in node:
        by_lower = {str(e).lower(): e for e in node["enum"] if isinstance(e, str)}
        return by_lower.get(value.lower(), value)
    if isinstance(value, dict) and "properties" in node:
        return {k: normalize_enums(v, node["properties"].get(k, {}), defs) for k, v in value.items()}
    if isinstance(value, list) and isinstance(node.get("items"), dict):
        return [normalize_enums(v, node["items"], defs) for v in value]
    for key in ("anyOf", "oneOf"):
        for option in node.get(key, []):
            opt = _resolve(option, defs)
            if (isinstance(value, str) and ("enum" in opt or opt.get("type") == "string")) or \
               (isinstance(value, dict) and opt.get("type") == "object") or (isinstance(value, list) and opt.get("type") == "array"):
                return normalize_enums(value, opt, defs)
    return value


class AnthropicAPIClient(LLMClient):
    provider = "anthropic_api"

    def __init__(self, timeout_seconds: float = 60, retries: int = 1, max_tokens: dict[str, int] | None = None,
                 pricing: dict | None = None, api_key: str | None = None, client: anthropic.AsyncAnthropic | None = None):
        self.timeout, self.retries = timeout_seconds, retries
        self.max_tokens, self.pricing = max_tokens or {}, pricing or {}
        self._api_key = api_key
        self._client = client
        self._schemas: dict[type[BaseModel], dict] = {}

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            key = self._api_key or os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                raise LLMUnavailable("config", "falta ANTHROPIC_API_KEY en el entorno")
            self._client = anthropic.AsyncAnthropic(api_key=key, timeout=self.timeout, max_retries=self.retries)
        return self._client

    def schema_for(self, schema: type[BaseModel]) -> dict:
        if schema not in self._schemas:
            self._schemas[schema] = anthropic.transform_schema(schema)
        return self._schemas[schema]

    async def _once(self, node: str, system_prompt: str, user_content: str, schema: type[BaseModel], model: str):
        api_schema = self.schema_for(schema)
        if self._client is None and not (self._api_key or os.environ.get("ANTHROPIC_API_KEY")):
            raise LLMUnavailable(node, "falta ANTHROPIC_API_KEY en el entorno")
        t0 = time.perf_counter()
        try:
            raw = await self.client.messages.with_raw_response.create(
                model=model, max_tokens=self.max_tokens.get(node, 1024),
                system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_content}],
                output_config={"format": {"type": "json_schema", "schema": api_schema}})
        except anthropic.APITimeoutError as e:
            raise LLMTimeout(node, f"sin respuesta en {self.timeout:.0f} s (tras {self.retries} reintentos)") from e
        except anthropic.APIConnectionError as e:
            raise LLMUnavailable(node, f"error de conexión: {e}") from e
        except anthropic.APIStatusError as e:
            raise LLMUnavailable(node, f"HTTP {e.status_code} {type(e).__name__}: {str(e.message)[:200]}") from e
        msg = await raw.parse()
        elapsed = (time.perf_counter() - t0) * 1000
        if msg.stop_reason in ("refusal", "max_tokens"):
            raise LLMInvalidOutput(node, f"stop_reason={msg.stop_reason}: la salida puede no cumplir el esquema")
        text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", None) == "text")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMInvalidOutput(node, f"salida no es JSON: {text[:200]!r}") from e
        payload = normalize_enums(payload, api_schema, api_schema.get("$defs", {}))
        try:
            data = schema.model_validate(payload)
        except ValidationError as e:
            raise LLMInvalidOutput(node, f"no cumple el esquema: {e.errors()[:3]}") from e
        return msg, data, elapsed, raw.retries_taken, raw.headers.get("request-id")

    async def complete_json(self, node, system_prompt, user_content, schema, model, prompt_version) -> LLMResult:
        last: LLMError | None = None
        sdk_retries = 0
        for attempt in range(1, (2 if self.retries > 0 else 1) + 1):      # reintento propio solo por salida inválida
            try:
                msg, data, elapsed, retries_taken, request_id = await self._once(node, system_prompt, user_content, schema, model)
            except LLMInvalidOutput as e:
                e.attempts = attempt + sdk_retries
                last = e
                continue
            except LLMError as e:
                e.attempts = attempt + self.retries                       # el SDK ya agotó sus reintentos
                raise
            sdk_retries += retries_taken
            u = msg.usage
            usage = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                     "cache_creation_input_tokens": u.cache_creation_input_tokens or 0,
                     "cache_read_input_tokens": u.cache_read_input_tokens or 0}
            return LLMResult(data=data, node=node, model=model, model_id=msg.model, prompt_version=prompt_version,
                             latency_ms=round(elapsed), cost_usd=cost_usd(msg.model, u, self.pricing), provider=self.provider,
                             attempts=attempt + sdk_retries,
                             raw={"usage": usage, "stop_reason": msg.stop_reason, "request_id": request_id,
                                  "sdk_retries": retries_taken, "pricing_retrieved": self.pricing.get("retrieved")})
        raise last  # type: ignore[misc]
