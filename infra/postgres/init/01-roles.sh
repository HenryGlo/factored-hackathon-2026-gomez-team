#!/usr/bin/env bash
# Se ejecuta UNA vez, al inicializar el volumen del contenedor (docker-entrypoint-initdb.d).
# Crea los roles de grupo sin login y los usuarios de login de la app, con contraseñas de .env.
# Los GRANT sobre esquemas y tablas los aplica la migración de Alembic (0002), no este script.
set -euo pipefail
: "${APP_DB_USER:?}" "${APP_DB_PASSWORD:?}" "${CONSOLE_DB_USER:?}" "${CONSOLE_DB_PASSWORD:?}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v app_user="$APP_DB_USER" -v app_pw="$APP_DB_PASSWORD" \
     -v console_user="$CONSOLE_DB_USER" -v console_pw="$CONSOLE_DB_PASSWORD" <<'SQL'
SELECT 'CREATE ROLE app_rw NOLOGIN' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') \gexec
SELECT 'CREATE ROLE app_ro NOLOGIN' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_ro') \gexec
-- usuarios de login: sin superusuario, sin crear bases ni roles, heredan solo su grupo
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_pw' NOSUPERUSER NOCREATEDB NOCREATEROLE IN ROLE app_rw;
CREATE ROLE :"console_user" LOGIN PASSWORD :'console_pw' NOSUPERUSER NOCREATEDB NOCREATEROLE IN ROLE app_ro;
SQL
