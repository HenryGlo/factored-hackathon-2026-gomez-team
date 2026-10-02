"""scripts/bootstrap_env.py: el .env generado deja arrancar el backend sin editar nada y nunca pisa uno existente."""
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("bootstrap_env", REPO / "scripts" / "bootstrap_env.py")
bootstrap_env = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap_env)


def parse(text: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line and not line.startswith("#"))


def test_generated_env_has_no_empty_values_and_consistent_urls(tmp_path):
    target = tmp_path / ".env"
    assert bootstrap_env.main(["--env-file", str(target)]) == 0
    env = parse(target.read_text())
    # una variable vacía rompería la lectura de enteros y fechas de la configuración: o tiene valor o queda comentada
    assert all(v.strip() for v in env.values())
    assert env["DATABASE_URL"] == f"postgresql+psycopg://{env['APP_DB_USER']}:{env['APP_DB_PASSWORD']}@127.0.0.1:{env['POSTGRES_PORT']}/{env['POSTGRES_DB']}"
    assert env["ADMIN_DATABASE_URL"].startswith(f"postgresql+psycopg://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}@")
    assert env["TEST_DATABASE_URL"].endswith("_test")
    assert len(env["DEMO_PASSWORD"]) >= 12 and len({env[k] for k in env if k.endswith("PASSWORD")}) == 4
    assert target.stat().st_mode & 0o777 == 0o600
    # las claves de terceros no se inventan
    assert "ANTHROPIC_API_KEY" not in env and "ELEVENLABS_API_KEY" not in env


def test_never_overwrites_an_existing_env(tmp_path):
    target = tmp_path / ".env"
    target.write_text("KEEP=1\n")
    assert bootstrap_env.main(["--env-file", str(target)]) == 0
    assert target.read_text() == "KEEP=1\n"
