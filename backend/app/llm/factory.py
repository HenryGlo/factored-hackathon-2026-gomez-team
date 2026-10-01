"""Construye el cliente LLM según la configuración (LLM_PROVIDER)."""
from __future__ import annotations

from backend.app.llm.claude_cli import ClaudeCLIClient
from backend.app.llm.client import LLMClient
from backend.app.llm.config import LLMConfig
from backend.app.llm.fake import FakeLLMClient


def make_client(config: LLMConfig) -> LLMClient:
    if config.provider == "claude_cli":
        return ClaudeCLIClient(timeout_seconds=config.timeout_seconds, retries=config.retries)
    return FakeLLMClient()
