"""Configuración de la capa LLM: backend/config/llm.toml con override por variables de entorno."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parents[2] / "config" / "llm.toml"
NODES = ("intent", "extract", "clarify", "confirm", "explain", "faq_answer", "handoff_summary")
ALIASES = ("haiku", "sonnet")
PROVIDERS = ("anthropic_api", "claude_cli", "fake")
CONFIRM_MODES = ("template", "llm")
CLARIFY_MODES = ("template", "llm", "auto")


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    timeout_seconds: float
    retries: int
    models: dict[str, str]                       # alias por nodo (claude_cli)
    confirm_mode: str = "template"   # template | llm
    clarify_mode: str = "auto"       # template | llm | auto (regla en docs/conversation-flow.md)
    model_ids: dict[str, str] = field(default_factory=dict)    # ID fijo por nodo (anthropic_api)
    max_tokens: dict[str, int] = field(default_factory=dict)
    pricing: dict = field(default_factory=dict)

    def model_for(self, node: str) -> str:
        """Lo que se pide al proveedor: ID fijo con la API (nada de alias en producción), alias con claude -p."""
        return self.model_ids[node] if self.provider == "anthropic_api" else self.models[node]


def load_llm_config(env: dict[str, str] | None = None, path: Path = CONFIG_FILE) -> LLMConfig:
    env = dict(os.environ if env is None else env)
    cfg = tomllib.loads(path.read_text(encoding="utf-8"))
    models, model_ids, max_tokens = {}, {}, {}
    for node in NODES:
        override = env.get(f"MODEL_{node.upper()}")
        alias = override or cfg["nodes"][node]["claude_cli"]
        if alias not in ALIASES:
            raise ValueError(f"MODEL_{node.upper()}={alias!r}: usar uno de {ALIASES}")
        models[node] = alias
        model_ids[node] = cfg["model_ids"][alias] if override else cfg["nodes"][node]["anthropic_api"]
        max_tokens[node] = int(cfg["nodes"][node].get("max_tokens", 1024))
    provider = env.get("LLM_PROVIDER") or cfg["provider"]
    if provider not in PROVIDERS:
        raise ValueError(f"LLM_PROVIDER={provider!r}: usar uno de {PROVIDERS}")
    pricing = tomllib.loads((path.parent / cfg.get("pricing_file", "llm_pricing.toml")).read_text(encoding="utf-8"))
    confirm_mode = env.get("CONFIRM_MODE") or cfg.get("confirm_mode", "template")
    if confirm_mode not in CONFIRM_MODES:
        raise ValueError(f"CONFIRM_MODE={confirm_mode!r}: usar uno de {CONFIRM_MODES}")
    clarify_mode = env.get("CLARIFY_MODE") or cfg.get("clarify_mode", "auto")
    if clarify_mode not in CLARIFY_MODES:
        raise ValueError(f"CLARIFY_MODE={clarify_mode!r}: usar uno de {CLARIFY_MODES}")
    return LLMConfig(provider=provider,
                     timeout_seconds=float(env.get("LLM_TIMEOUT_SECONDS") or cfg["timeout_seconds"]),
                     retries=int(env.get("LLM_RETRIES") or cfg["retries"]), models=models,
                     confirm_mode=confirm_mode, clarify_mode=clarify_mode, model_ids=model_ids, max_tokens=max_tokens,
                     pricing=pricing)
