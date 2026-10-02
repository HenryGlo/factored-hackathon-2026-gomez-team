# Backend (FastAPI) para Render. Contexto: raíz del repo (.dockerignore deja fuera datos, secretos y el frontend).
# Arranque: infra/render/start.sh (deriva las URLs de la app desde la del dueño y lanza uvicorn en $PORT).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
# en la imagen no van las herramientas de prueba (pytest*): se filtran del requirements de desarrollo y pipeline
RUN grep -vE '^(pytest|pytest-asyncio)==' requirements.txt > requirements.prod.txt && pip install -r requirements.prod.txt

COPY backend backend
COPY data_pipeline data_pipeline
# modelos pequeños versionados con su hash: cascada de intención (models/intent) y calibrador de riesgo (models/risk)
COPY models models
COPY scripts/seed_demo_users.py scripts/seed_demo_users.py
COPY infra/render infra/render

RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app

ENV APP_ENV=production LOG_FORMAT=json PORT=8000
EXPOSE 8000
CMD ["bash", "infra/render/start.sh"]
