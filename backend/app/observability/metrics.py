"""Métricas por endpoint en memoria, para el panel de administración futuro (GET /api/metrics).

Por (método, ruta con plantilla) guarda conteos, errores y las últimas N latencias, para p50 y p95. Se reinicia con el
proceso. Lo durable (llamadas y costo del LLM por día, latencia de los turnos) sale de app.traces con las vistas SQL de la
migración 0006.
"""
from __future__ import annotations

from datetime import datetime, timezone
from collections import defaultdict, deque


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 1)


class EndpointMetrics:
    def __init__(self, keep: int = 2000):
        self.lat: dict[tuple[str, str], deque] = defaultdict(lambda: deque(maxlen=keep))
        self.count: dict[tuple[str, str], int] = defaultdict(int)
        self.errors_4xx: dict[tuple[str, str], int] = defaultdict(int)
        self.errors_5xx: dict[tuple[str, str], int] = defaultdict(int)
        self.rate_limited: dict[tuple[str, str], int] = defaultdict(int)
        self.server_errors: deque = deque(maxlen=50)          # (instante ISO, método, ruta, estado) de los últimos 5xx

    def record(self, method: str, route: str, status: int, latency_ms: float) -> None:
        k = (method, route)
        self.count[k] += 1
        self.lat[k].append(latency_ms)
        if status == 429:
            self.rate_limited[k] += 1
        if 400 <= status < 500:
            self.errors_4xx[k] += 1
        elif status >= 500:
            self.errors_5xx[k] += 1
            self.server_errors.append((datetime.now(timezone.utc).isoformat(timespec="seconds"), method, route, status))

    def snapshot(self) -> list[dict]:
        return [{"method": m, "route": r, "requests": self.count[(m, r)], "errors_4xx": self.errors_4xx[(m, r)],
                 "errors_5xx": self.errors_5xx[(m, r)], "rate_limited": self.rate_limited[(m, r)],
                 "latency_ms_p50": percentile(list(self.lat[(m, r)]), 0.5), "latency_ms_p95": percentile(list(self.lat[(m, r)]), 0.95),
                 "sample": len(self.lat[(m, r)])} for (m, r) in sorted(self.count)]
