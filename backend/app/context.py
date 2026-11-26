"""Контекст портфеля (PRD, 6.1): агрегаты, которые считаются до прогона правил."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median

from .rules.base import days, first_year_surrender


@dataclass
class Lapse:
    n: int = 0          # договоров НСЖ у агента
    lapsed: int = 0     # из них выкуплено в первый год

    @property
    def ratio(self) -> float:
        return self.lapsed / self.n if self.n else 0.0


@dataclass
class Context:
    as_of: date | None = None
    pa_window_start: date | None = None
    paRecent: dict[str, int] = field(default_factory=dict)
    paMed: float = 0.0
    issuer: dict[str, int] = field(default_factory=dict)
    card: dict[str, int] = field(default_factory=dict)
    corp: dict[str, int] = field(default_factory=dict)
    lapse: dict[str, Lapse] = field(default_factory=dict)


def build_context(cases: list[dict], params: dict[str, dict], as_of: date | None = None) -> Context:
    """Строит контекст.

    params — параметры правил по id ({"A2": {"win": 90, ...}, "N1": {"d": 60, ...}}).
    as_of — дата отсчёта окна A2; по умолчанию максимальная дата договора в портфеле,
    чтобы результат был воспроизводим на одних и тех же данных.
    """
    win = int(params.get("A2", {}).get("win", 90))
    n1_d = int(params.get("N1", {}).get("d", 60))

    if as_of is None:
        dates = [c["contractDate"] for c in cases if c.get("contractDate")]
        as_of = max(dates) if dates else None

    ctx = Context(as_of=as_of)
    if as_of is not None:
        ctx.pa_window_start = as_of - timedelta(days=win)

    pa_agents: set[str] = set()
    pa_recent: Counter[str] = Counter()
    issuer: Counter[str] = Counter()
    card_clients: dict[str, set[str]] = defaultdict(set)
    corp: Counter[str] = Counter()
    lapse: dict[str, Lapse] = defaultdict(Lapse)

    for c in cases:
        product = c.get("product")
        agent = c.get("agent")
        if product == "ПА":
            if agent:
                pa_agents.add(agent)
                cd = c.get("contractDate")
                if cd and ctx.pa_window_start and ctx.pa_window_start <= cd <= as_of:
                    pa_recent[agent] += 1
            if c.get("basis") == "инвалидность" and c.get("disabilityIssuer"):
                issuer[c["disabilityIssuer"]] += 1
        elif product == "НСЖ":
            if c.get("payerCard"):
                card_clients[c["payerCard"]].add(c.get("client") or c["id"])
            if c.get("employer"):
                d = days(c.get("contractDate"), c.get("surrenderDate"))
                if d is not None and 365 <= d <= 365 + n1_d:
                    corp[c["employer"]] += 1
            if agent:
                lapse[agent].n += 1
                if first_year_surrender(c):
                    lapse[agent].lapsed += 1

    ctx.paRecent = {a: pa_recent.get(a, 0) for a in pa_agents}
    ctx.paMed = float(median(ctx.paRecent.values())) if ctx.paRecent else 0.0
    ctx.issuer = dict(issuer)
    ctx.card = {k: len(v) for k, v in card_clients.items()}
    ctx.corp = dict(corp)
    ctx.lapse = dict(lapse)
    return ctx
