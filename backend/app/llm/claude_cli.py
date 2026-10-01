"""Cliente LLM que invoca `claude -p` (suscripción de Claude Code) como subproceso.

Equivalente a (sin shell, argumentos en lista):

    claude -p --model <alias> --output-format json --json-schema '<schema>'
      --system-prompt-file <tmp>/system.md --tools "" --disallowedTools "mcp__*"
      --no-session-persistence --max-turns 3 --strict-mcp-config --setting-sources ""

- El texto del usuario va por stdin.
- El directorio de trabajo es una carpeta temporal vacía: no se carga CLAUDE.md del repo.
- `--strict-mcp-config --setting-sources ""` evita que entren servidores MCP, memorias y ajustes
  del usuario. Medido: 514 tokens de entrada en vez de 1.171 con un system prompt de una línea.
  El CLI igual agrega un recordatorio de entorno (SO, fecha y el email de la cuenta), que no se
  puede quitar sin --bare.
- NO se usa --bare: exige API key y no usa la suscripción.

Salida real verificada con Claude Code 2.1.286 (`--output-format json`): objeto con
`structured_output` (lo validado contra --json-schema), `result`, `is_error`, `subtype`,
`total_cost_usd`, `duration_ms`, `num_turns` y `modelUsage` ({id real del modelo: uso}).
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path

from pydantic import BaseModel, ValidationError

from backend.app.llm.client import LLMClient, LLMError, LLMInvalidOutput, LLMResult, LLMTimeout, LLMUnavailable


class ClaudeCLIClient(LLMClient):
    provider = "claude_cli"

    def __init__(self, binary: str = "claude", timeout_seconds: float = 60, retries: int = 1, max_turns: int = 3):
        self.binary, self.timeout, self.retries, self.max_turns = binary, timeout_seconds, retries, max_turns

    def command(self, model: str, schema: type[BaseModel], system_prompt_file: Path) -> list[str]:
        return [self.binary, "-p", "--model", model, "--output-format", "json",
                "--json-schema", json.dumps(schema.model_json_schema(), ensure_ascii=False),
                "--system-prompt-file", str(system_prompt_file),
                "--tools", "", "--disallowedTools", "mcp__*",
                "--no-session-persistence", "--max-turns", str(self.max_turns),
                "--strict-mcp-config", "--setting-sources", ""]

    async def _once(self, node: str, system_prompt: str, user_content: str, schema: type[BaseModel],
                    model: str) -> tuple[dict, BaseModel, float]:
        with tempfile.TemporaryDirectory(prefix="llm_") as tmp:
            workdir = Path(tmp) / "work"          # carpeta vacía como directorio de trabajo
            workdir.mkdir()
            sp = Path(tmp) / "system.md"          # fuera del directorio de trabajo
            sp.write_text(system_prompt, encoding="utf-8")
            t0 = time.perf_counter()
            try:
                proc = await asyncio.create_subprocess_exec(
                    *self.command(model, schema, sp), cwd=workdir, stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            except FileNotFoundError as e:
                raise LLMUnavailable(node, f"no se encontró el binario {self.binary!r}") from e
            try:
                out, err = await asyncio.wait_for(proc.communicate(user_content.encode()), timeout=self.timeout)
            except asyncio.TimeoutError as e:
                proc.kill()
                await proc.wait()
                raise LLMTimeout(node, f"sin respuesta en {self.timeout:.0f} s") from e
            elapsed = (time.perf_counter() - t0) * 1000
        if proc.returncode != 0 and not out:
            raise LLMUnavailable(node, f"código {proc.returncode}: {err.decode(errors='replace')[:300]}")
        try:
            raw = json.loads(out)
        except json.JSONDecodeError as e:
            raise LLMInvalidOutput(node, f"salida no es JSON: {out[:200]!r}") from e
        if raw.get("is_error") or raw.get("subtype") != "success":
            raise LLMUnavailable(node, f"{raw.get('subtype')}: {str(raw.get('result'))[:300]}")
        payload = raw.get("structured_output")
        if payload is None:   # respaldo: el texto final como JSON
            try:
                payload = json.loads(raw.get("result") or "")
            except json.JSONDecodeError as e:
                raise LLMInvalidOutput(node, "sin structured_output") from e
        try:
            data = schema.model_validate(payload)
        except ValidationError as e:
            raise LLMInvalidOutput(node, f"no cumple el esquema: {e.errors()[:3]}") from e
        return raw, data, elapsed

    async def complete_json(self, node, system_prompt, user_content, schema, model, prompt_version) -> LLMResult:
        last: LLMError | None = None
        for attempt in range(1, self.retries + 2):
            try:
                raw, data, elapsed = await self._once(node, system_prompt, user_content, schema, model)
            except LLMError as e:
                e.attempts = attempt
                last = e
                continue
            usage = raw.get("modelUsage") or {}
            return LLMResult(data=data, node=node, model=model, model_id=next(iter(usage), None),
                             prompt_version=prompt_version, latency_ms=round(elapsed),
                             cost_usd=raw.get("total_cost_usd"), provider=self.provider, attempts=attempt,
                             raw={k: raw.get(k) for k in ("duration_ms", "duration_api_ms", "num_turns", "session_id",
                                                           "total_cost_usd", "usage")})
        raise last  # type: ignore[misc]
