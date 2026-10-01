"""Configuración de protección: backend/config/security.toml con override por entorno."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parents[2] / "config" / "security.toml"


@dataclass(frozen=True)
class Limit:
    limit: int
    window_seconds: int

    @classmethod
    def parse(cls, value: str) -> "Limit":
        n, sec = str(value).split("/")
        if int(n) < 1 or int(sec) < 1:
            raise ValueError(f"límite inválido: {value!r}")
        return cls(int(n), int(sec))


@dataclass(frozen=True)
class SecurityConfig:
    rate_enabled: bool
    rate: dict[str, Limit]
    daily_calls: int
    daily_cost_usd: float
    session_calls: int
    session_cost_usd: float
    max_message_chars: int


def load_security_config(env: dict[str, str] | None = None, path: Path = CONFIG_FILE) -> SecurityConfig:
    env = dict(os.environ if env is None else env)
    cfg = tomllib.loads(path.read_text(encoding="utf-8"))
    rate = {k: Limit.parse(env.get(f"RATE_{k.upper()}") or v) for k, v in cfg["rate"].items() if k != "enabled"}
    enabled = str(env.get("RATE_LIMITS_ENABLED", cfg["rate"].get("enabled", True))).lower() not in ("false", "0", "no")
    b = {k: env.get(f"LLM_BUDGET_{k.upper()}") or v for k, v in cfg["llm_budget"].items()}
    return SecurityConfig(rate_enabled=enabled, rate=rate, daily_calls=int(b["daily_calls"]), daily_cost_usd=float(b["daily_cost_usd"]),
                          session_calls=int(b["session_calls"]), session_cost_usd=float(b["session_cost_usd"]),
                          max_message_chars=int(env.get("MAX_MESSAGE_CHARS") or cfg["http"]["max_message_chars"]))
