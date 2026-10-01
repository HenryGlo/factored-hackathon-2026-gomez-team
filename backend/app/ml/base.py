"""Interfaces de los componentes de ML. Cada resultado dice qué implementación y versión lo produjo
(se guarda en la traza)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from backend.app.dates import DateRange
from backend.app.llm.client import LLMResult
from backend.app.llm.schemas import IntentOutput


@dataclass
class IntentPrediction:
    output: IntentOutput
    implementation: str
    version: str
    llm: LLMResult | None = None       # si lo produjo un LLM: modelo, latencia, costo
    info: dict | None = None           # cascada: ruta (local | llm), probabilidad, umbral y motivo; va a la traza


class IntentClassifier(ABC):
    implementation: str
    version: str

    @abstractmethod
    async def classify(self, text: str) -> IntentPrediction: ...


@dataclass(frozen=True)
class RankQuery:
    """Pistas ya estructuradas (salida de extract + dates.py). Todo es opcional."""
    amount: Decimal | None = None
    currency: str | None = None
    amount_approx: bool = False
    date_range: DateRange | None = None
    merchant_hint: str | None = None
    session_date: date | None = None


@dataclass
class ScoredCandidate:
    transaction: dict[str, Any]
    score: float
    probability: float                 # softmax dentro de la lista
    rank: int
    features: dict[str, float] = field(default_factory=dict)


@dataclass
class RankResult:
    candidates: list[ScoredCandidate]
    implementation: str
    version: str


class Ranker(ABC):
    implementation: str
    version: str

    @abstractmethod
    def rank(self, query: RankQuery, transactions: list[dict[str, Any]]) -> RankResult: ...


@dataclass(frozen=True)
class RiskAssessment:
    probability: float | None          # None = riesgo desconocido (sin fraud_score)
    band: str                          # alto | medio | bajo | desconocido
    threshold: float
    implementation: str
    version: str
    inputs_used: dict[str, Any] = field(default_factory=dict)


class RiskModel(ABC):
    implementation: str
    version: str

    @abstractmethod
    def assess(self, transaction: dict[str, Any]) -> RiskAssessment: ...


@dataclass(frozen=True)
class ClarifyDecision:
    ask: bool
    reasons: tuple[str, ...]           # por qué se pregunta (o 'clara')
    discriminant: str | None           # fecha | monto | comercio | tipo_problema
    show: tuple[int, ...]              # índices (en la lista rankeada) de las candidatas a mostrar
    implementation: str
    version: str


class ClarifyPolicy(ABC):
    implementation: str
    version: str

    @abstractmethod
    def decide(self, query: RankQuery, ranked: RankResult, problem_known: bool = True) -> ClarifyDecision: ...
