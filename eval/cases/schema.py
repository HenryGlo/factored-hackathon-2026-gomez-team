"""Esquema validado de un caso de evaluación (YAML en eval/cases/<split>/).

Un caso NO contiene IDs del dataset (P-04): nombra un selector (eval/cases/selectors.py), una consulta SQL
documentada que elige de forma determinista un cliente real y su transacción objetivo. Los mensajes
usan marcadores ({monto_es}, {comercio}, {fecha_ddmm}…) que el runner rellena con esa transacción.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

Outcome = Literal["resolved_case", "resolved_info", "resolved_action", "recognized", "clarified_then_resolved",
                  "abstained", "escalated"]
Category = Literal["normal", "ambiguo", "humano", "adversario", "fallo", "auth"]
ACTIONS = ("create_dispute_case", "lock_card", "create_handoff")
DEFAULT_HANDOFF_FIELDS = ["handoff_id", "conversation_id", "customer_ref", "language", "reason_code", "priority", "queue",
                          "request", "customer_claims", "verified_facts", "policy_evaluations", "actions_taken",
                          "open_questions", "summary", "status"]


class _S(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Step(_S):
    """Un paso del guion. Exactamente uno de: message, action, expire_session, relogin, fault, new_conversation, http."""
    message: str | None = None
    action: Literal["confirm", "confirm_old", "reject", "request_human", "select_target", "select_second", "select_index",
                    "select_foreign", "dispute_target", "select_card"] | None = None
    index: int | None = None                     # select_index
    card: Literal["credito", "debito"] | None = None
    expire_session: bool | None = None
    relogin: bool | None = None
    fault: list[str] | None = None               # tools que fallan desde este paso ([] limpia)
    new_conversation: bool | None = None
    link_previous: bool = False                  # con new_conversation: enlazada a la anterior, como hace el frontend tras un 409
    http: dict | None = None                     # {method, path, as: customer|analyst|anonymous}
    expect_status: int | None = None
    optional: bool = False                       # si no aplica (p. ej. no hay card_list), se salta
    when: list[Literal["inicio", "aclarando", "confirmando_movimiento", "confirmando_accion", "cerrado", "escalado"]] | None = None
    # solo se ejecuta si la conversación está en uno de estos estados (guiones escritos sin ver el sistema)

    @model_validator(mode="after")
    def exactly_one(self):
        kinds = [k for k in ("message", "action", "expire_session", "relogin", "fault", "new_conversation", "http")
                 if getattr(self, k) is not None]
        if len(kinds) != 1:
            raise ValueError(f"cada paso lleva exactamente una clave de acción; tiene {kinds}")
        return self


class Expected(_S):
    outcome: Outcome | list[Outcome]
    transaction: Literal["target", "second"] | None = None
    forbidden_actions: list[Literal["create_dispute_case", "lock_card", "create_handoff"]] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    handoff_reason: str | None = None
    handoff_fields: list[str] = Field(default_factory=lambda: list(DEFAULT_HANDOFF_FIELDS))
    max_clarify_rounds: int = 3
    clarify_rounds: int | None = None            # exacto (p. ej. 0: no debe preguntar)
    notice: str | None = None
    reason_code: str | None = None               # del reclamo creado
    faq_ids: list[str] = Field(default_factory=list)   # respuestas aprobadas esperadas, en orden (pregunta_proceso)
    fast_path: bool | None = None                # True: saludo/gracias sin LLM ni tools; False: NO debe tomar el atajo
    out_of_scope: bool = False                   # redirige con el texto aprobado y no responde la consulta
    open_at_end: bool | None = None              # True: la conversación termina abierta (estado inicio)


class Case(_S):
    case_id: str
    split: Literal["dev", "dev_paraphrase", "test"]
    language: Literal["es", "pt"]
    category: Category
    title: str
    selector: str
    pick: int = 0                                # k-ésimo cliente que cumple el selector
    session_date: date | None = None             # 'hoy' simulado; por defecto la fecha de referencia del dataset
    today_after: Literal["target", "second"] | None = None
    # 'hoy' = el día siguiente a esa transacción, para que "ayer" la señale en cualquier dataset (real o sintético)
    steps: list[Step]
    expected: Expected

    @property
    def outcomes(self) -> list[str]:
        return self.expected.outcome if isinstance(self.expected.outcome, list) else [self.expected.outcome]


def load_cases(split: str, root: Path | None = None) -> list[Case]:
    root = root or Path(__file__).resolve().parent / split
    cases = []
    for path in sorted(root.glob("*.yaml")):
        for raw in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            case = Case.model_validate(raw)
            if case.split != split:
                raise ValueError(f"{path.name}: {case.case_id} tiene split={case.split}, está en {split}/")
            cases.append(case)
    ids = [c.case_id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("case_id repetidos")
    return cases
