"""Interfaz de los clientes LLM y tipos comunes.

Los nodos solo conocen `LLMClient.complete_json`: cambiar de `claude -p` a la API de Claude (para
el despliegue) es escribir otra implementación, sin tocar los nodos.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResult(Generic[T]):
    data: T                       # salida validada con el modelo Pydantic del nodo
    node: str
    model: str                    # alias pedido (haiku | sonnet)
    model_id: str | None          # ID real que devolvió el proveedor
    prompt_version: str
    latency_ms: int               # reloj de pared, incluye arranque del proceso
    cost_usd: float | None
    provider: str
    attempts: int = 1
    raw: dict[str, Any] = field(default_factory=dict)


class LLMError(Exception):
    """Error tipado de la capa LLM. `kind` permite al controlador elegir el fallback seguro."""

    def __init__(self, kind: str, node: str, message: str, attempts: int = 1):
        super().__init__(f"[{node}] {kind}: {message}")
        self.kind, self.node, self.message, self.attempts = kind, node, message, attempts


class LLMTimeout(LLMError):
    def __init__(self, node: str, message: str, attempts: int = 1):
        super().__init__("timeout", node, message, attempts)


class LLMUnavailable(LLMError):
    def __init__(self, node: str, message: str, attempts: int = 1):
        super().__init__("unavailable", node, message, attempts)


class LLMInvalidOutput(LLMError):
    def __init__(self, node: str, message: str, attempts: int = 1):
        super().__init__("invalid_output", node, message, attempts)


class LLMClient(ABC):
    provider: str = "abstract"

    @abstractmethod
    async def complete_json(self, node: str, system_prompt: str, user_content: str, schema: type[T],
                            model: str, prompt_version: str) -> LLMResult[T]:
        """Devuelve la salida del nodo validada contra `schema` o lanza LLMError."""
