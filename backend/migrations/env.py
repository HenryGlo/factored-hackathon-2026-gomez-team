"""Entorno de Alembic: usa los modelos de backend/persistence/models.py y ADMIN_DATABASE_URL (dueño de los esquemas)."""
import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine, pool

from backend.persistence.models import SCHEMAS, metadata

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def database_url() -> str:
    # -x db_url=... permite apuntar a otra base (lo usa el test del ETL)
    url = context.get_x_argument(as_dictionary=True).get("db_url") or os.environ.get("ADMIN_DATABASE_URL")
    if not url:
        raise RuntimeError("Falta ADMIN_DATABASE_URL (ver .env.example)")
    return url


def include_object(obj, name, type_, reflected, compare_to):
    # Solo se gestionan los esquemas del proyecto; public queda para alembic_version
    if type_ == "table":
        return obj.schema in SCHEMAS
    return True


def run_migrations_offline() -> None:
    context.configure(url=database_url(), target_metadata=metadata, literal_binds=True,
                      include_schemas=True, include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata, include_schemas=True,
                          include_object=include_object, compare_type=True, compare_server_default=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
