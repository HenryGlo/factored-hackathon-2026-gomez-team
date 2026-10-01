"""Registro de la traza de un turno: cada paso con nodo, tipo (llm | ml | code), implementación,
modelo pedido y real, versión de prompt, entrada, salida, reglas, latencia y costo. Sin cadena de
pensamiento: solo entradas, salidas y registros de ejecución."""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from backend.app.llm.client import LLMResult


def _jsonable(o: Any) -> Any:
    return json.loads(json.dumps(o, default=lambda x: str(x) if isinstance(x, Decimal) else (x.isoformat() if hasattr(x, "isoformat") else str(x)),
                                 ensure_ascii=False))


@dataclass
class Step:
    seq: int
    node: str
    kind: str
    implementation: str | None = None
    tool: str | None = None
    model: str | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    latency_ms: int = 0
    cost_usd: float | None = None
    payload: dict = field(default_factory=dict)
    rules: list | None = None
    error: str | None = None


class TraceRecorder:
    def __init__(self) -> None:
        self.steps: list[Step] = []

    def add(self, node: str, kind: str, *, input: Any = None, output: Any = None, implementation: str | None = None,
            tool: str | None = None, latency_ms: int = 0, rules: list | None = None, error: str | None = None,
            extra: dict | None = None) -> Step:
        s = Step(len(self.steps) + 1, node, kind, implementation=implementation, tool=tool, latency_ms=latency_ms,
                 payload=_jsonable({"input": input, "output": output, **(extra or {})}), rules=_jsonable(rules) if rules else None,
                 error=error)
        self.steps.append(s)
        return s

    def add_llm(self, node: str, res: LLMResult | None, *, input: Any = None, error: str | None = None,
                fallback: str | None = None, model: str | None = None, extra: dict | None = None) -> Step:
        more = {"fallback": fallback, "attempts": res.attempts if res else None} if (fallback or res) else {}
        if res and res.raw.get("usage"):                 # tokens (incluida la caché) e id de la petición del proveedor
            more.update(usage=res.raw["usage"], request_id=res.raw.get("request_id"))
        s = self.add(node, "llm", input=input, output=res.data.model_dump() if res else None,
                     implementation=f"{res.provider}" if res else None, latency_ms=res.latency_ms if res else 0, error=error,
                     extra={**more, **(extra or {})} or None)
        if res:
            s.model, s.model_id, s.prompt_version, s.cost_usd = res.model, res.model_id, res.prompt_version, res.cost_usd
        else:
            s.model = model
        return s

    @contextmanager
    def timed(self):
        box = {"ms": 0}
        t0 = time.perf_counter()
        try:
            yield box
        finally:
            box["ms"] = round((time.perf_counter() - t0) * 1000)

    @property
    def cost_usd(self) -> float:
        return round(sum(s.cost_usd or 0 for s in self.steps), 6)

    @property
    def latency_ms(self) -> int:
        return sum(s.latency_ms for s in self.steps)
