"""Voz con ElevenLabs detrás del backend (prompt 08, A3): /api/voice/config, /api/voice/stt y /api/voice/tts.

- Apagada por defecto (VOICE_ENABLED). El frontend nunca ve la clave: el backend hace de proxy.
- STT devuelve solo la transcripción. El cliente la ve, la puede corregir y la envía como un mensaje normal: entra al MISMO
  flujo y las MISMAS guardas que el chat escrito. La voz no salta ninguna regla y nunca confirma una acción (R4: hace falta
  el botón en pantalla).
- TTS solo lee el texto de un turno del asistente que ya existe y es de ese cliente: no es un sintetizador de texto libre.
- El audio no se guarda en ningún lado. Se registra solo el consumo (segundos y caracteres) para el presupuesto y el costo.
- Presupuesto propio por sesión y por día, límite de peticiones, y modo degradado: ante cualquier fallo o límite, el
  endpoint responde con un error tipado y el chat sigue por texto.
- El audio y el texto a leer salen a un tercero (ElevenLabs): ver docs/llm-data.md.
"""
from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from backend.app.auth.deps import current_session, databases
from backend.app.auth.service import SessionContext
from backend.app.conversations import require_customer_csrf
from backend.app.errors import ApiError, not_found

router = APIRouter(prefix="/api/voice", tags=["voz"])
LOG = logging.getLogger("backend.voice")
CONFIG_FILE = Path(__file__).resolve().parents[1] / "config" / "voice.toml"
AUDIO_TYPES = ("audio/webm", "audio/ogg", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4", "audio/aac", "video/webm")
SPEAKABLE = ("text", "summary", "message")           # campos de los bloques que se leen en voz alta


@dataclass(frozen=True)
class VoiceConfig:
    enabled: bool
    api_key: str | None
    voice_id: str | None
    cfg: dict

    @property
    def ready(self) -> bool:
        return self.enabled and bool(self.api_key) and bool(self.voice_id)

    @property
    def reason(self) -> str | None:
        if not self.enabled:
            return "voice_disabled"
        if not self.api_key or not self.voice_id:
            return "voice_not_configured"
        return None


def load_voice_config(env: dict[str, str] | None = None) -> VoiceConfig:
    env = dict(os.environ if env is None else env)
    enabled = str(env.get("VOICE_ENABLED", "false")).lower() in ("true", "1", "yes")
    return VoiceConfig(enabled, env.get("ELEVENLABS_API_KEY") or None, env.get("ELEVENLABS_VOICE_ID") or None,
                       tomllib.loads(CONFIG_FILE.read_text(encoding="utf-8")))


def voice_config(request: Request) -> VoiceConfig:
    return request.app.state.voice


def http_client(request: Request) -> httpx.AsyncClient:
    """Cliente HTTP hacia ElevenLabs. Los tests ponen uno con transporte simulado en app.state.voice_http."""
    client = getattr(request.app.state, "voice_http", None)
    if client is None:
        cfg = voice_config(request).cfg["provider"]
        client = request.app.state.voice_http = httpx.AsyncClient(base_url=cfg["base_url"], timeout=cfg["timeout_seconds"])
    return client


def require_voice(request: Request, ctx: SessionContext = Depends(require_customer_csrf)) -> SessionContext:
    v = voice_config(request)
    if not v.ready:
        raise ApiError(503, v.reason or "voice_disabled", "La voz no está disponible. Sigamos por texto.",
                       details={"fallback": "text"})
    return ctx


USAGE = """SELECT coalesce(sum(seconds) FILTER (WHERE session_id = :s), 0) AS session_seconds,
                  coalesce(sum(characters) FILTER (WHERE session_id = :s), 0) AS session_chars,
                  coalesce(sum(seconds), 0) AS day_seconds, coalesce(sum(characters), 0) AS day_chars
           FROM app.voice_usage WHERE created_at >= date_trunc('day', now() AT TIME ZONE 'utc') AT TIME ZONE 'utc'"""


async def check_budget(request: Request, ctx: SessionContext, kind: str, amount: float = 0) -> None:
    """429 si la sesión o el día ya gastaron el presupuesto de voz (o lo pasarían con este pedido)."""
    b = voice_config(request).cfg["budget"]
    async with databases(request).rw.connect() as c:
        u = (await c.execute(text(USAGE), {"s": ctx.session_id})).mappings().one()
    used = {"session_stt_seconds": float(u["session_seconds"]), "daily_stt_seconds": float(u["day_seconds"]),
            "session_tts_chars": int(u["session_chars"]), "daily_tts_chars": int(u["day_chars"])}
    keys = ("session_stt_seconds", "daily_stt_seconds") if kind == "stt" else ("session_tts_chars", "daily_tts_chars")
    for k in keys:
        if used[k] + amount > b[k] or used[k] >= b[k]:
            LOG.warning("voice_budget_exceeded", extra={"limit": k, "used": used[k]})
            raise ApiError(429, "voice_budget_exceeded", "Se agotó el uso de voz por ahora. Sigamos por texto.",
                           details={"fallback": "text", "limit": k})


async def record(request: Request, ctx: SessionContext, kind: str, seconds: float = 0, characters: int = 0,
                 conversation_id: str | None = None) -> float:
    price = voice_config(request).cfg["pricing"]
    cost = round(seconds / 60 * price["stt_usd_per_minute"] + characters / 1000 * price["tts_usd_per_1000_chars"], 6)
    async with databases(request).rw.begin() as c:
        await c.execute(text("""INSERT INTO app.voice_usage (session_id, customer_id, conversation_id, kind, seconds, characters, cost_usd)
                                VALUES (:s, :c, :cv, :k, :sec, :ch, :cost)"""),
                        {"s": ctx.session_id, "c": ctx.customer_id, "cv": conversation_id, "k": kind, "sec": round(seconds, 2),
                         "ch": characters, "cost": cost})
    LOG.info("voice_usage", extra={"kind": kind, "seconds": round(seconds, 2), "characters": characters, "cost_usd": cost})
    return cost


def unavailable(code: str = "voice_unavailable") -> ApiError:
    return ApiError(502, code, "La voz falló. Sigamos por texto.", retryable=True, details={"fallback": "text"})


@router.get("/config")
async def get_config(request: Request, _: SessionContext = Depends(current_session)) -> dict:
    """Para que el frontend sepa si ofrecer la voz. Nunca incluye la clave."""
    v = voice_config(request)
    lim = v.cfg["limits"]
    return {"enabled": v.ready, "reason": v.reason, "max_audio_bytes": lim["max_audio_bytes"], "max_tts_chars": lim["max_tts_chars"],
            "audio_types": list(AUDIO_TYPES), "confirmations": "siempre en pantalla, con botón: la voz no confirma acciones"}


@router.post("/stt")
async def speech_to_text(request: Request, language: Literal["es", "pt"] | None = None,
                         ctx: SessionContext = Depends(require_voice)) -> dict:
    """Cuerpo = el audio (Content-Type audio/*). Devuelve la transcripción para que el cliente la revise y la envíe como un
    mensaje normal. No guarda el audio ni llama al flujo del chat."""
    v = voice_config(request)
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype not in AUDIO_TYPES:
        raise ApiError(415, "unsupported_audio", "Formato de audio no soportado.", details={"accepted": list(AUDIO_TYPES)})
    limit = v.cfg["limits"]["max_audio_bytes"]
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise ApiError(413, "audio_too_large", "El audio es muy largo. Graba un mensaje más corto.", details={"max_bytes": limit})
    audio = b""
    async for chunk in request.stream():
        audio += chunk
        if len(audio) > limit:
            raise ApiError(413, "audio_too_large", "El audio es muy largo. Graba un mensaje más corto.", details={"max_bytes": limit})
    if not audio:
        raise ApiError(400, "validation_error", "El audio llegó vacío.")
    await check_budget(request, ctx, "stt")
    data = {"model_id": v.cfg["provider"]["stt_model"]}
    if language:
        data["language_code"] = language
    try:
        r = await http_client(request).post("/v1/speech-to-text", headers={"xi-api-key": v.api_key or ""}, data=data,
                                            files={"file": ("audio", audio, ctype)})
    except httpx.HTTPError as e:
        LOG.warning("voice_error", extra={"kind": "stt", "error": type(e).__name__})
        raise unavailable() from e
    if r.status_code != 200:
        LOG.warning("voice_error", extra={"kind": "stt", "status": r.status_code})
        raise unavailable()
    body = r.json()
    transcript = str(body.get("text") or "").strip()
    words = body.get("words") or []
    seconds = float(max((w.get("end") or 0 for w in words), default=0)) or len(audio) / 16000     # sin tiempos: estimación por tamaño
    await record(request, ctx, "stt", seconds=seconds)
    max_chars = request.app.state.security.max_message_chars
    return {"text": transcript[:max_chars], "language_code": body.get("language_code"), "seconds": round(seconds, 2),
            "truncated": len(transcript) > max_chars,
            "next": "muestra la transcripción, deja corregirla y envíala con POST /api/conversations/{id}/turns (via: voice)"}


class Speak(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: str = Field(max_length=40)
    turn_id: str = Field(max_length=40)


SPOKEN: dict[str, dict[str, Any]] = {
    "es": {"options": "Puedes decir: {items}.", "or": " o ", "nth": ["La primera", "La segunda", "La tercera", "La cuarta", "La quinta"],
           "pick": "Dime cuál: por ejemplo, la primera, o el nombre del comercio.", "more": "y {n} más en la pantalla",
           "confirm": "Para confirmar, toca el botón Confirmar en la pantalla."},
    "pt": {"options": "Você pode dizer: {items}.", "or": " ou ", "nth": ["A primeira", "A segunda", "A terceira", "A quarta", "A quinta"],
           "pick": "Diga qual: por exemplo, a primeira, ou o nome da loja.", "more": "e mais {n} na tela",
           "confirm": "Para confirmar, toque no botão Confirmar na tela."},
}


def _tx_phrase(t: dict) -> str:
    return ", ".join(x for x in (t.get("label"), t.get("amount_label"), t.get("date_label")) if x)


def speakable(blocks: list[dict], lang: str = "es") -> str:
    """Texto que se lee de un turno del asistente, en orden: lo mismo que el cliente ve escrito y, para el modo voz (manos
    libres), también las opciones: las candidatas ("La primera: Netflix, 15,99 USD, 3 jun 2026…"), los movimientos de una
    lista y las respuestas rápidas ("Puedes decir: …"). Las confirmaciones se leen, pero se recuerda que se confirman con el
    botón (R4: la voz no confirma acciones)."""
    s = SPOKEN.get(lang, SPOKEN["es"])
    parts = []
    for b in blocks or []:
        kind = b.get("type")
        if kind == "candidate_list":
            cands = b.get("candidates") or []
            parts += [f"{s['nth'][i]}: {_tx_phrase(c)}." for i, c in enumerate(cands[:5])]
            parts.append(s["pick"])
        elif kind == "transaction_list":
            txs = b.get("transactions") or []
            parts += [f"{s['nth'][i]}: {_tx_phrase(x)}." for i, x in enumerate(txs[:5])]
            if len(txs) > 5:
                parts.append(s["more"].format(n=len(txs) - 5) + ".")
        elif kind == "quick_replies":
            labels = [o["label"] for o in b.get("options") or []]
            if labels:
                items = ", ".join(labels[:-1]) + (s["or"] + labels[-1] if len(labels) > 1 else labels[0])
                parts.append(s["options"].format(items=items))
        else:
            for k in SPEAKABLE:
                if isinstance(b.get(k), str) and b[k].strip():
                    parts.append(b[k].strip())
                    break
            if kind == "action_confirmation":
                parts.append(s["confirm"])
    return "\n".join(parts)


@router.post("/tts")
async def text_to_speech(body: Speak, request: Request, ctx: SessionContext = Depends(require_voice)) -> StreamingResponse:
    """Lee en voz alta un turno del asistente de una conversación del cliente. Audio en streaming (audio/mpeg), sin guardarlo."""
    v = voice_config(request)
    async with databases(request).rw.connect() as c:
        row = (await c.execute(text("""SELECT t.blocks, cv.language FROM app.turns t JOIN app.conversations cv USING (conversation_id)
                                       WHERE t.turn_id = :t AND t.conversation_id = :cv AND t.role = 'assistant' AND cv.customer_id = :c"""),
                               {"t": body.turn_id, "cv": body.conversation_id, "c": ctx.customer_id})).mappings().first()
    if row is None:
        raise not_found()
    say = speakable(row["blocks"], row["language"] or "es")[: v.cfg["limits"]["max_tts_chars"]]
    if not say:
        raise ApiError(400, "nothing_to_say", "Ese turno no tiene texto para leer.")
    await check_budget(request, ctx, "tts", amount=len(say))
    p = v.cfg["provider"]
    req = http_client(request).build_request(
        "POST", f"/v1/text-to-speech/{v.voice_id}/stream", params={"output_format": p["tts_output_format"]},
        headers={"xi-api-key": v.api_key or ""}, json={"text": say, "model_id": p["tts_model"], "language_code": row["language"]})
    try:
        upstream = await http_client(request).send(req, stream=True)
    except httpx.HTTPError as e:
        LOG.warning("voice_error", extra={"kind": "tts", "error": type(e).__name__})
        raise unavailable() from e
    if upstream.status_code != 200:
        await upstream.aclose()
        LOG.warning("voice_error", extra={"kind": "tts", "status": upstream.status_code})
        raise unavailable()
    await record(request, ctx, "tts", characters=len(say), conversation_id=body.conversation_id)

    async def stream():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
    return StreamingResponse(stream(), media_type="audio/mpeg", headers={"Cache-Control": "no-store", "X-Voice-Characters": str(len(say))})
