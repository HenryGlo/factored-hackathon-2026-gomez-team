"""Modo demostración: GET /api/demo/info (público) para que el login muestre el aviso y los usuarios demo.

- `DEMO_MODE=true` lo enciende (apagado por defecto). Apagado, el endpoint responde `{"demo_mode": false}` y nada más.
- Devuelve los usuarios demo ACTIVOS de la base con su escenario, en es y pt. Son usuarios ficticios sobre datos sintéticos.
- NUNCA devuelve la contraseña ni dónde está guardada: solo dice en qué documento la encuentran los jueces.
- No abre nada más: los límites de peticiones, el presupuesto de LLM y las guardas son los mismos con o sin modo demo.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Request
from sqlalchemy import text

from backend.app.auth.deps import databases

router = APIRouter(prefix="/api/demo", tags=["demo"])

NOTICE = {"es": "Entorno de demostración con datos ficticios. Ningún cliente, tarjeta ni movimiento es real.",
          "pt": "Ambiente de demonstração com dados fictícios. Nenhum cliente, cartão ou movimento é real."}
PASSWORD_HINT = {"es": "La contraseña de los usuarios demo está en la documentación de entrega del equipo (no se muestra aquí).",
                 "pt": "A senha dos usuários de demonstração está na documentação de entrega da equipe (não é mostrada aqui)."}
# escenario de cada cliente demo (data_pipeline/etl/demo_customers.py); el orden es el del recorrido de la demo
SCENARIOS: dict[str, dict[str, str]] = {
    "cargo_claro": {"es": "Cargo claro: un cargo reciente con comercio y monto únicos. Reclámalo de punta a punta.",
                    "pt": "Cobrança clara: uma cobrança recente com loja e valor únicos. Reclame de ponta a ponta."},
    "cargos_parecidos": {"es": "Cargos parecidos: dos cargos de monto muy similar. El asistente pregunta cuál es.",
                         "pt": "Cobranças parecidas: duas cobranças de valor muito similar. O assistente pergunta qual é."},
    "fraude_alto": {"es": "Riesgo alto: un cargo con señal de riesgo alta. Pasa al equipo de fraude como ticket.",
                    "pt": "Risco alto: uma cobrança com sinal de risco alto. Vai para a equipe de fraude como ticket."},
    "fuera_de_plazo": {"es": "Fuera de plazo: un cargo de hace más de 60 días. Pasa a una persona.",
                       "pt": "Fora do prazo: uma cobrança de mais de 60 dias. Vai para uma pessoa."},
    "pendiente": {"es": "Pendiente: un cargo todavía sin confirmar. Informa, sin abrir reclamo.",
                  "pt": "Pendente: uma cobrança ainda não confirmada. Informa, sem abrir reclamação."},
    "revertido": {"es": "Revertido: un cargo que ya fue revertido. Informa que no hay cargo vigente.",
                  "pt": "Estornado: uma cobrança já estornada. Informa que não há cobrança vigente."},
}
STAFF = {"analyst": {"es": "Agente de soporte: bandeja de tickets y detalle de cada caso.",
                     "pt": "Agente de suporte: caixa de tickets e detalhe de cada caso."},
         "admin": {"es": "Administrador: SLO, métricas, costos y logs.", "pt": "Administrador: SLO, métricas, custos e logs."}}
ROLE_ORDER = {"customer": 0, "analyst": 1, "admin": 2}
USERS = text("""SELECT username, role, display_name FROM app.users
                WHERE is_active AND (username LIKE 'demo\\_%' OR role IN ('analyst', 'admin')) ORDER BY username""")


@router.get("/info")
async def demo_info(request: Request) -> dict:
    if not request.app.state.settings.demo_mode:
        return {"demo_mode": False}
    async with databases(request).rw.connect() as c:
        rows = (await c.execute(USERS)).mappings().all()
    users = []
    for r in rows:
        m = re.fullmatch(r"demo_(.+)_(\d+)", r["username"])
        scenario = m.group(1) if m and r["role"] == "customer" else None
        if r["role"] == "customer" and scenario not in SCENARIOS:
            continue
        users.append({"username": r["username"], "role": r["role"], "display_name": r["display_name"], "scenario": scenario,
                      "rank": int(m.group(2)) if scenario and m else None,
                      "description": SCENARIOS[scenario] if scenario else STAFF[r["role"]]})
    order = list(SCENARIOS)
    users.sort(key=lambda u: (ROLE_ORDER[u["role"]], u["rank"] or 0, order.index(u["scenario"]) if u["scenario"] else 0, u["username"]))
    return {"demo_mode": True, "notice": NOTICE, "password_hint": PASSWORD_HINT, "users": users}
