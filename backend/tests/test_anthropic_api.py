"""Prompt 05, fase 1: cliente de la API de Claude con un transporte HTTP simulado (sin red, sin clave real)."""
from __future__ import annotations

import asyncio
import json

import anthropic
import httpx2
import pytest

from backend.app.llm.anthropic_api import AnthropicAPIClient, cost_usd, normalize_enums
from backend.app.llm.client import LLMInvalidOutput, LLMTimeout, LLMUnavailable
from backend.app.llm.config import load_llm_config
from backend.app.llm.schemas import ClarifyOutput, IntentOutput

run = asyncio.run
HAIKU = "claude-haiku-4-5-20251001"
CFG = load_llm_config({"LLM_PROVIDER": "anthropic_api"})


def message(payload: dict | str, stop_reason: str = "end_turn", usage: dict | None = None) -> dict:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return {"id": "msg_01", "type": "message", "role": "assistant", "model": HAIKU,
            "content": [{"type": "text", "text": text}], "stop_reason": stop_reason, "stop_sequence": None,
            "usage": usage or {"input_tokens": 1000, "output_tokens": 100, "cache_creation_input_tokens": 0,
                               "cache_read_input_tokens": 0}}


class Script:
    """Transporte simulado: devuelve las respuestas en orden y guarda cada petición."""

    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(json.loads(request.content))
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        status, body = r
        return httpx2.Response(status, json=body, headers={"retry-after-ms": "1", "request-id": f"req_{len(self.requests)}"})


def client_with(script: Script, retries: int = 1) -> AnthropicAPIClient:
    sdk = anthropic.AsyncAnthropic(api_key="sk-ant-test", max_retries=retries, timeout=5,
                                   http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(script)))
    return AnthropicAPIClient(timeout_seconds=5, retries=retries, max_tokens=CFG.max_tokens, pricing=CFG.pricing, client=sdk)


def call(c: AnthropicAPIClient, schema=ClarifyOutput, node="clarify"):
    return run(c.complete_json(node, "Eres un asistente.", '{"idioma": "es"}', schema, HAIKU, f"{node}@v2"))


# ---------------------------------------------------------------- configuración
def test_config_uses_fixed_model_ids_with_the_api():
    assert CFG.model_for("intent") == HAIKU and CFG.model_for("explain") == "claude-sonnet-5-5"
    assert load_llm_config({"LLM_PROVIDER": "claude_cli"}).model_for("intent") == "haiku"        # alias solo con el CLI
    assert load_llm_config({"LLM_PROVIDER": "anthropic_api", "MODEL_EXPLAIN": "haiku"}).model_for("explain") == HAIKU
    assert CFG.pricing["source"].startswith("https://") and CFG.pricing["retrieved"]
    assert all(CFG.model_ids[n] in CFG.pricing["models"] for n in CFG.model_ids)                  # todo modelo tiene precio


def test_cost_from_usage_including_cache():
    usage = type("U", (), {"input_tokens": 1000, "output_tokens": 200, "cache_creation_input_tokens": 4000,
                           "cache_read_input_tokens": 10000})()
    # 1000×1 + 200×5 + 4000×1.25 + 10000×0.10 = 8000 → $0.008
    assert cost_usd(HAIKU, usage, CFG.pricing) == pytest.approx(0.008)
    assert cost_usd("modelo-sin-precio", usage, CFG.pricing) is None


# ---------------------------------------------------------------- éxito
def test_success_sends_structured_output_and_cached_system_prompt():
    script = Script((200, message({"pregunta": "¿Recuerdas qué día fue?"})))
    res = call(client_with(script))
    assert res.data.pregunta == "¿Recuerdas qué día fue?" and res.model_id == HAIKU and res.provider == "anthropic_api"
    assert res.cost_usd == pytest.approx(0.0015) and res.attempts == 1 and res.raw["request_id"] == "req_1"
    body = script.requests[0]
    assert body["model"] == HAIKU and body["max_tokens"] == CFG.max_tokens["clarify"]
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    fmt = body["output_config"]["format"]
    assert fmt["type"] == "json_schema" and fmt["schema"]["additionalProperties"] is False
    prop = fmt["schema"]["properties"]["pregunta"]                 # la API no aplica límites: quedan como texto
    assert "minLength" not in prop and "maxLength" not in prop and "minLength: 5" in prop["description"]


def test_enum_casing_is_normalized_before_validation():
    payload = {"intent": "Cargo_No_Reconocido", "otras_intenciones": ["BLOQUEAR_TARJETA"], "tema": None, "idioma": "ES",
               "certeza": "Alta", "sospecha_manipulacion": False, "multiples_intenciones": True}
    res = call(client_with(Script((200, message(payload)))), IntentOutput, "intent")
    assert (res.data.intent, res.data.otras_intenciones, res.data.idioma, res.data.certeza) == \
           ("cargo_no_reconocido", ["bloquear_tarjeta"], "es", "alta")
    schema = anthropic.transform_schema(IntentOutput)
    assert normalize_enums({"idioma": "Pt"}, schema, schema.get("$defs", {})) == {"idioma": "pt"}


# ---------------------------------------------------------------- salida inválida
def test_invalid_schema_is_retried_once_then_typed_error():
    # minLength no lo aplica la API: lo valida Pydantic después
    script = Script((200, message({"pregunta": "¿y?"})))
    with pytest.raises(LLMInvalidOutput) as e:
        call(client_with(script))
    assert len(script.requests) == 2 and e.value.attempts == 2


@pytest.mark.parametrize("payload,stop", [("{\"pregunta\": \"incompleto", "max_tokens"), ("No puedo ayudar.", "refusal"),
                                          ("esto no es json", "end_turn")])
def test_refusal_truncation_or_non_json_are_invalid_output(payload, stop):
    with pytest.raises(LLMInvalidOutput):
        call(client_with(Script((200, message(payload, stop_reason=stop))), retries=0))


# ---------------------------------------------------------------- red, límites y reintentos
def test_timeout_maps_to_llm_timeout_after_sdk_retries():
    script = Script(httpx2.ReadTimeout("lento"))
    with pytest.raises(LLMTimeout) as e:
        call(client_with(script, retries=1))
    assert len(script.requests) == 2 and e.value.attempts == 2


@pytest.mark.parametrize("status,kind", [(429, "rate_limit_error"), (529, "overloaded_error")])
def test_rate_limit_and_overload_are_retried_and_recover(status, kind):
    script = Script((status, {"type": "error", "error": {"type": kind, "message": "ocupado"}}),
                    (200, message({"pregunta": "¿Recuerdas el monto?"})))
    res = call(client_with(script, retries=1))
    assert res.data.pregunta == "¿Recuerdas el monto?" and len(script.requests) == 2 and res.attempts == 2


@pytest.mark.parametrize("status,kind", [(429, "rate_limit_error"), (529, "overloaded_error")])
def test_persistent_rate_limit_or_overload_is_unavailable(status, kind):
    script = Script((status, {"type": "error", "error": {"type": kind, "message": "ocupado"}}))
    with pytest.raises(LLMUnavailable) as e:
        call(client_with(script, retries=2))
    assert len(script.requests) == 3 and str(status) in e.value.message


def test_auth_error_is_not_retried():
    script = Script((401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}))
    with pytest.raises(LLMUnavailable):
        call(client_with(script, retries=2))
    assert len(script.requests) == 1


def test_missing_api_key_fails_fast_without_network(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMUnavailable, match="ANTHROPIC_API_KEY"):
        call(AnthropicAPIClient(timeout_seconds=1, retries=0, pricing=CFG.pricing))


def test_workspace_header_only_when_configured(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)
    assert "anthropic-workspace-id" not in AnthropicAPIClient().client.default_headers
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_test")
    assert AnthropicAPIClient().client.default_headers["anthropic-workspace-id"] == "wrkspc_test"
