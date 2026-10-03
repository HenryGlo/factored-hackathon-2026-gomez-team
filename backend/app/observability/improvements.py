"""GET /api/admin/improvements (issue #61): reportes del ciclo de mejora con Opus y los PR que propuso, para el panel admin.

Los reportes viven en las ramas `improve/<fecha>` de los PR que abre `scripts/improve_loop.py` (nunca se fusionan solos), no
en `main` ni en la base. El backend los lee de GitHub: la lista de PR con rama `improve/` y, de cada rama,
`reports/improve-<fecha>.json`. Con el repo público no necesita credenciales; con uno privado usa `GITHUB_TOKEN` si existe.
Se guarda en memoria 10 minutos. Si GitHub no responde, devuelve la lista vacía y el motivo: el panel lo dice, no falla.
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request

from backend.app.auth.deps import require_admin
from backend.app.auth.service import SessionContext

router = APIRouter(prefix="/api/admin", tags=["admin"])
REPO = os.environ.get("GITHUB_REPO", "HenryGlo/factored-hackathon-2026-gomez-team")
TTL_SECONDS = 600


def _headers() -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "disputas-admin"}
    if token := os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = f"Bearer {token}"
    return h


def _pr_state(pr: dict) -> str:
    if pr.get("merged_at"):
        return "merged"
    if pr.get("state") == "open":
        return "draft" if pr.get("draft") else "open"
    return "closed"


def summarize(pr: dict, report: dict | None) -> dict[str, Any]:
    """Una fila del panel: fecha, patrones con su evidencia (n/N), casos y cambios de prompt propuestos, y el PR."""
    ref = pr["head"]["ref"]
    day = ref.split("/", 1)[1]
    date = f"{day[:4]}-{day[4:6]}-{day[6:8]}" if len(day) >= 8 and day[:8].isdigit() else day
    patterns, cases, prompts = [], 0, 0
    if report:
        total = sum((report.get("conteo") or {}).values()) or None
        for p in (report.get("analysis") or {}).get("patrones", []):
            n = len(p.get("evidencia") or [])
            cases += len(p.get("casos_propuestos") or [])
            prompts += bool(p.get("cambio_de_prompt"))
            patterns.append({"title": p.get("titulo"), "evidence": f"{n}/{total}" if total else str(n), "actionable": bool(p.get("accionable"))})
    return {"date": date, "path": f"reports/improve-{day}.md", "report_url": f"https://github.com/{REPO}/blob/{ref}/reports/improve-{day}.md",
            "patterns": patterns, "proposed_cases": cases, "prompt_changes": prompts, "llm": (report or {}).get("llm"),
            "pr_url": pr["html_url"], "pr_number": pr["number"], "pr_state": _pr_state(pr), "pr_title": pr.get("title")}


async def fetch(client: httpx.AsyncClient) -> list[dict]:
    """Las ramas improve/* (aunque sus PR sean viejos) y, de cada una, su PR y su reporte."""
    owner = REPO.split("/", 1)[0]
    r = await client.get(f"https://api.github.com/repos/{REPO}/git/matching-refs/heads/improve/", headers=_headers())
    r.raise_for_status()
    rows = []
    for ref in (x["ref"].removeprefix("refs/heads/") for x in r.json()):
        prs = await client.get(f"https://api.github.com/repos/{REPO}/pulls", params={"state": "all", "head": f"{owner}:{ref}"},
                               headers=_headers())
        prs.raise_for_status()
        if not prs.json():
            continue
        day = ref.split("/", 1)[1]
        rep = await client.get(f"https://raw.githubusercontent.com/{REPO}/{ref}/reports/improve-{day}.json", headers=_headers())
        rows.append(summarize(prs.json()[0], rep.json() if rep.status_code == 200 else None))
    return sorted(rows, key=lambda x: x["date"], reverse=True)


@router.get("/improvements")
async def improvements(request: Request, _: SessionContext = Depends(require_admin)) -> dict:
    cache = getattr(request.app.state, "improvements_cache", None)
    if cache and time.monotonic() - cache[0] < TTL_SECONDS:
        return cache[1]
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            body = {"reports": await fetch(client), "source": f"github.com/{REPO}", "unavailable": None}
    except (httpx.HTTPError, ValueError, KeyError) as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        body = {"reports": [], "source": f"github.com/{REPO}",
                "unavailable": "github_private_or_not_found" if status == 404 else "github_unreachable"}
    request.app.state.improvements_cache = (time.monotonic(), body)
    return body
