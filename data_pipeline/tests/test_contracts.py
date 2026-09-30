"""Los contratos YAML y los modelos SQLAlchemy describen las mismas columnas de ref (sin deriva)."""
import re

import pytest
from sqlalchemy.dialects import postgresql

from backend.persistence.models import metadata
from data_pipeline.contracts.engine import LOAD_ORDER, load_contracts

LINEAGE = {"source_file", "etl_run_id"}


def norm(t: str) -> str:
    return re.sub(r"\s+", "", t.upper().replace("WITHOUT TIME ZONE", ""))


@pytest.mark.parametrize("table", LOAD_ORDER)
def test_contract_matches_model(table):
    contract = load_contracts()[table]
    model = metadata.tables[f"ref.{table}"]
    in_model = {c.name: (norm(str(c.type.compile(dialect=postgresql.dialect()))), c.nullable)
                for c in model.columns if c.name not in LINEAGE}
    in_contract = {k: (norm(v["type"]), v["nullable"]) for k, v in contract.columns.items()}
    assert in_contract == in_model
    assert contract.primary_key == [c.name for c in model.primary_key.columns]


def test_rules_are_well_formed():
    for table, c in load_contracts().items():
        ids = [r.id for r in c.all_rules]
        assert len(ids) == len(set(ids)), f"{table}: ids de regla repetidos"
        for r in c.rules:
            if r.check in ("domain", "range"):
                assert r.column in c.columns or r.column in ("first_name", "last_name"), r.id
            if r.check == "fk":
                assert r.references["table"] in LOAD_ORDER and len(r.columns) == len(r.references["columns"]), r.id
