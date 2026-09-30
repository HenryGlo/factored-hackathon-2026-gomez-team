"""Motores de base de datos: lectura/escritura (app_rw) y solo lectura para la consola (app_ro)."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from backend.app.config import Settings


@dataclass
class Databases:
    rw: AsyncEngine   # backend: lee ref/ops, lee y escribe app
    ro: AsyncEngine   # consola: solo lectura

    @classmethod
    def from_settings(cls, s: Settings) -> "Databases":
        kw = dict(pool_pre_ping=True, pool_size=5, max_overflow=5)
        return cls(rw=create_async_engine(s.database_url, **kw), ro=create_async_engine(s.console_database_url, **kw))

    async def dispose(self) -> None:
        await self.rw.dispose()
        await self.ro.dispose()
