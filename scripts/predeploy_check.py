"""Comprobaciones previas al despliegue que no necesitan red ni Docker (las llama scripts/predeploy_check.sh).

1. render.yaml al día: las variables NO secretas de disputas-api son exactamente las de infra/render/prod.env; los secretos
   van con `sync: false`; ninguna variable trae un valor que parezca un secreto.
2. Variables documentadas: cada variable de render.yaml aparece en docs/deployment.md o en .env.example.
3. Sin datos del dataset en el repo: ni archivos de datos fuera de los fixtures sintéticos, ni IDs con el formato del dataset
   real (CLI-/PRD-/TRX-) en archivos versionados, ni archivos grandes inesperados.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SECRETS = {"ANTHROPIC_API_KEY", "DEMO_PASSWORD"}                     # sync: false (panel de Render)
MANAGED = {"ADMIN_DATABASE_URL", "APP_DB_USER", "APP_DB_PASSWORD", "CONSOLE_DB_USER", "CONSOLE_DB_PASSWORD"}   # base y generateValue
DATA_EXT = re.compile(r"\.(csv|parquet|feather|duckdb|sqlite|db|pkl|xlsx)$")
DATA_ALLOWED = ("data_pipeline/fixtures/", "eval/manual/template.csv", "eval/cases/")
REAL_ID = re.compile(rb"\b(?:CLI|PRD)-[A-Z0-9]{12}\b|\bTRX-[A-Z0-9]{20}\b")
BIG_BYTES, BIG_ALLOWED = 1_000_000, ("models/intent/", "frontend/docs/screenshots/", "docs/screenshots/")


def prod_env() -> dict[str, str]:
    lines = (ROOT / "infra/render/prod.env").read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))


def check_render() -> list[str]:
    path = ROOT / "render.yaml"
    if not path.exists():
        return ["no existe render.yaml (está en el PR del despliegue; fusionarlo antes de desplegar)"]
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    api = next(s for s in doc["services"] if s["name"] == "disputas-api")
    env = {e["key"]: e for e in api["envVars"]}
    errors = []
    plain = {k: str(e["value"]) for k, e in env.items() if "value" in e and k not in MANAGED}
    want = prod_env()
    for k in sorted(set(want) | set(plain)):
        if plain.get(k) != want.get(k):
            errors.append(f"{k}: render.yaml={plain.get(k)!r} · prod.env={want.get(k)!r}")
    for k in SECRETS:
        if env.get(k, {}).get("sync") is not False:
            errors.append(f"{k} debe ir con `sync: false` (secreto del panel)")
    for k, v in plain.items():
        if re.search(r"sk-ant-|password|secret", v, re.I) or (re.fullmatch(r"[A-Za-z0-9_\-]{32,}", v)):
            errors.append(f"{k} tiene un valor que parece un secreto")
    docs = (ROOT / "docs/deployment.md").read_text(encoding="utf-8") + (ROOT / ".env.example").read_text(encoding="utf-8")
    errors += [f"{k} no está documentada en docs/deployment.md ni en .env.example" for k in sorted(env) if k not in docs]
    static = next(s for s in doc["services"] if s["name"] == "disputas-web")
    if not any(r.get("source") == "/api/*" for r in static.get("routes", [])):
        errors.append("el sitio estático no reescribe /api/* al backend")
    if doc["databases"][0].get("ipAllowList") != []:
        errors.append("la base debe quedar sin acceso externo (ipAllowList: [])")
    return errors


def check_no_dataset() -> list[str]:
    files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.decode().split("\0")
    errors = []
    for f in filter(None, files):
        p = ROOT / f
        if not p.is_file():
            continue
        if DATA_EXT.search(f) and not f.startswith(DATA_ALLOWED):
            errors.append(f"archivo de datos versionado: {f}")
        size = p.stat().st_size
        if size > BIG_BYTES and not f.startswith(BIG_ALLOWED):
            errors.append(f"archivo grande versionado ({size // 1000} kB): {f}")
        # un ID de relleno (CLI-ZZZZ9999ZZZZ) no es un dato: los reales mezclan muchos caracteres distintos
        real = [m for m in REAL_ID.finditer(p.read_bytes())] if size < 5_000_000 else []
        if m := next((m for m in real if len(set(m.group(0)[4:])) > 3), None):
            errors.append(f"ID con formato del dataset real en {f}: {m.group(0)[:6].decode()}…")
    return errors


def main() -> int:
    rc = 0
    for name, fn in (("render.yaml al día con infra/render/prod.env y variables documentadas", check_render),
                     ("sin datos del dataset ni archivos grandes en el repo", check_no_dataset)):
        errors = fn()
        print(f"{'✔' if not errors else '✘'} {name}")
        for e in errors:
            print(f"    - {e}")
        rc |= bool(errors)
    return rc


if __name__ == "__main__":
    sys.exit(main())
