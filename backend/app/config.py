"""Configuración del backend, leída de variables de entorno y .env (ver .env.example)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO / ".env", extra="ignore")

    # Bases de datos: el backend nunca usa el dueño de los esquemas ni el superusuario
    database_url: str                      # usuario de login del grupo app_rw
    console_database_url: str              # usuario de login del grupo app_ro (lecturas de la consola)

    app_env: str = "development"           # production → cookies Secure
    # Sesión
    session_idle_minutes: int = 30         # vencimiento por inactividad
    session_max_hours: int = 12            # vida máxima aunque haya actividad
    session_cookie: str = "session"
    csrf_cookie: str = "csrf_token"
    csrf_header: str = "X-CSRF-Token"
    # Límite de intentos de login
    login_window_minutes: int = 15
    login_max_failures_user: int = 5
    login_max_failures_ip: int = 20
    trust_proxy: bool = False              # usar X-Forwarded-For solo detrás de un proxy propio

    @property
    def secure_cookies(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
