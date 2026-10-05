-- Esquema eval: flujos generados y resultados de sus corridas, en la base LOCAL (EVAL_STORE_URL o ADMIN_DATABASE_URL).
-- No es una migración de Alembic a propósito: la base desplegada nunca lo crea. Lo aplica eval/generated/store.py
-- (idempotente) antes de escribir. Sin IDs del dataset: los casos usan selectores y marcadores, como los YAML de eval/cases/.
CREATE SCHEMA IF NOT EXISTS eval;
COMMENT ON SCHEMA eval IS 'Evaluación a escala: flujos generados (eval/generated) y resultados por caso. Solo en la base local.';

CREATE TABLE IF NOT EXISTS eval.batches (
    batch_id          serial PRIMARY KEY,
    created_at        timestamptz NOT NULL DEFAULT now(),
    generator_version text NOT NULL,
    seed              bigint NOT NULL,
    params            jsonb NOT NULL DEFAULT '{}',
    n_cases           integer NOT NULL,
    git_commit        text,
    note              text
);

CREATE TABLE IF NOT EXISTS eval.generated_cases (
    batch_id          integer NOT NULL REFERENCES eval.batches ON DELETE CASCADE,
    case_id           text NOT NULL,
    language          char(2) NOT NULL,
    category          text NOT NULL,
    selector          text NOT NULL,
    seed_case_id      text NOT NULL,                 -- caso escrito a mano (dev) o paráfrasis revisada del que sale
    seed_split        text NOT NULL,
    origin            text NOT NULL CHECK (origin IN ('combinatorio', 'parafrasis_claude')),
    pick              integer NOT NULL,
    opener            text NOT NULL DEFAULT '',
    noise             text NOT NULL,
    expected_outcomes text[] NOT NULL,
    definition        jsonb NOT NULL,                -- el caso completo (eval/cases/schema.py:Case)
    PRIMARY KEY (batch_id, case_id)
);
CREATE INDEX IF NOT EXISTS ix_generated_cases_strata ON eval.generated_cases (batch_id, language, category);

CREATE TABLE IF NOT EXISTS eval.runs (
    run_id            serial PRIMARY KEY,
    batch_id          integer NOT NULL REFERENCES eval.batches ON DELETE CASCADE,
    started_at        timestamptz NOT NULL,
    finished_at       timestamptz NOT NULL DEFAULT now(),
    variant           text NOT NULL,                 -- con los --set, p. ej. sistema+LLM_PROVIDER=fake
    llm_provider      text NOT NULL,
    sample_size       integer NOT NULL,
    sample_seed       bigint NOT NULL,
    repeats           integer NOT NULL,
    database          text NOT NULL,                 -- base de evaluación donde corrió (*_test)
    git_commit        text,
    git_dirty         boolean,
    summary           jsonb NOT NULL,                -- eval/harness/metrics.py:summarize
    report_path       text
);

CREATE TABLE IF NOT EXISTS eval.case_results (
    run_id            integer NOT NULL REFERENCES eval.runs ON DELETE CASCADE,
    batch_id          integer NOT NULL,
    case_id           text NOT NULL,
    repeat            integer NOT NULL,
    outcome           text NOT NULL,
    all_pass          boolean NOT NULL,
    unsafe            boolean NOT NULL,
    expected_auto     boolean NOT NULL,
    safe_auto         boolean NOT NULL,
    expected_escalated boolean NOT NULL,
    escalated         boolean NOT NULL,
    failed_checks     text[] NOT NULL DEFAULT '{}',
    root_cause        text,                          -- extracción, aclaración, política, escalamiento, idioma, tool
    cost_usd          numeric(12, 6) NOT NULL DEFAULT 0,
    n_turns           integer NOT NULL,
    latency_ms        numeric(12, 1) NOT NULL,       -- suma de los turnos del caso
    turn_latency_max_ms numeric(12, 1),
    llm_calls         integer NOT NULL,
    error             text,
    checks            jsonb NOT NULL,
    PRIMARY KEY (run_id, case_id, repeat),
    FOREIGN KEY (batch_id, case_id) REFERENCES eval.generated_cases ON DELETE CASCADE
);

-- Una fila por caso corrido con sus dimensiones: para agrupar por idioma, categoría, ruido, saludo, semilla…
CREATE OR REPLACE VIEW eval.v_results AS
SELECT r.*, run.variant, run.llm_provider, run.started_at, c.language, c.category, c.selector, c.seed_case_id, c.seed_split,
       c.origin, c.pick, c.opener <> '' AS with_opener, c.noise, c.expected_outcomes
FROM eval.case_results r
JOIN eval.runs run ON run.run_id = r.run_id
JOIN eval.generated_cases c ON c.batch_id = r.batch_id AND c.case_id = r.case_id;
