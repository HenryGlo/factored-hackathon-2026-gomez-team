"""Configuración de la capa LLM: backend/config/llm.toml con override por variables de entorno."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parents[2] / "config" / "llm.toml"
NODES = ("intent", "extract", "clarify", "confirm", "explain", "handoff_summary")
ALIASES = ("haiku", "sonnet")


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    timeout_seconds: float
    retries: int
    models: dict[str, str]

    def model_for(self, node: str) -> str:
        return self.models[node]


def load_llm_config(env: dict[str, str] | None = None, path: Path = CONFIG_FILE) -> LLMConfig:
    env = dict(os.environ if env is None else env)
    cfg = tomllib.loads(path.read_text(encoding="utf-8"))
    models = {}
    for node in NODES:
        alias = env.get(f"MODEL_{node.upper()}") or cfg["nodes"][node]["model"]
        if alias not in ALIASES:
            raise ValueError(f"MODEL_{node.upper()}={alias!r}: usar uno de {ALIASES}")
        models[node] = alias
    provider = env.get("LLM_PROVIDER") or cfg["provider"]
    if provider not in ("claude_cli", "fake"):
        raise ValueError(f"LLM_PROVIDER={provider!r}: usar claude_cli o fake")
    return LLMConfig(provider=provider,
                     timeout_seconds=float(env.get("LLM_TIMEOUT_SECONDS") or cfg["timeout_seconds"]),
                     retries=int(env.get("LLM_RETRIES") or cfg["retries"]), models=models)
