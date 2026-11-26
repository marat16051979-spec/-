"""Прогон правил и скоринг (PRD, 6.3–6.4). Чистые функции без БД."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .context import Context, build_context
from .rules import RULES_BY_ID

log = logging.getLogger("antifraud.engine")

DEFAULT_LEVELS = {"high": 50, "medium": 25}
LEVEL_NAMES = {"high": "высокий", "medium": "средний", "low": "низкий"}


@dataclass
class RuleConfig:
    """Настройки правила из таблицы `rules`."""

    id: str
    weight: int
    enabled: bool = True
    params: dict[str, Any] = field(default_factory=dict)
    action: str = ""
    scheme: str = ""
    products: tuple[str, ...] = ()
    name: str = ""

    @classmethod
    def default(cls, rule_id: str) -> "RuleConfig":
        r = RULES_BY_ID[rule_id]
        return cls(
            id=r.id, weight=r.weight, enabled=True, params=dict(r.params), action=r.action,
            scheme=r.scheme, products=r.products, name=r.name,
        )


def default_configs() -> list[RuleConfig]:
    return [RuleConfig.default(rid) for rid in RULES_BY_ID]


@dataclass
class CaseResult:
    case_id: str
    score: int
    level: str
    hits: list[dict]


def level_for(score: int, levels: dict | None = None) -> str:
    lv = levels or DEFAULT_LEVELS
    if score >= lv["high"]:
        return "высокий"
    if score >= lv["medium"]:
        return "средний"
    return "низкий"


def evaluate_case(case: dict, ctx: Context, configs: list[RuleConfig], errors: list | None = None) -> list[dict]:
    """Список сработавших правил. Ошибка одного правила не останавливает прогон."""
    hits = []
    product = case.get("product")
    for cfg in configs:
        if not cfg.enabled:
            continue
        spec = RULES_BY_ID.get(cfg.id)
        if spec is None:
            continue
        products = cfg.products or spec.products
        if product not in products:
            continue
        params = {**spec.params, **(cfg.params or {})}
        try:
            explanation = spec.evaluate(case, ctx, params)
        except Exception as e:  # noqa: BLE001 — правило пропускается, ошибка логируется
            log.exception("Ошибка правила %s на деле %s", cfg.id, case.get("id"))
            if errors is not None:
                errors.append({"rule": cfg.id, "case": case.get("id"), "error": f"{type(e).__name__}: {e}"})
            continue
        if explanation:
            hits.append({
                "rule": cfg.id,
                "scheme": cfg.scheme or spec.scheme,
                "name": cfg.name or spec.name,
                "weight": int(cfg.weight),
                "explanation": explanation,
                "action": cfg.action or spec.action,
            })
    return hits


def score_hits(hits: list[dict]) -> int:
    return min(100, sum(h["weight"] for h in hits))


def run(
    cases: list[dict],
    configs: list[RuleConfig] | None = None,
    levels: dict | None = None,
    as_of: date | None = None,
) -> tuple[list[CaseResult], Context, list[dict]]:
    configs = configs if configs is not None else default_configs()
    params = {c.id: {**RULES_BY_ID[c.id].params, **(c.params or {})} for c in configs if c.id in RULES_BY_ID}
    ctx = build_context(cases, params, as_of=as_of)
    errors: list[dict] = []
    results = []
    for case in cases:
        hits = evaluate_case(case, ctx, configs, errors)
        s = score_hits(hits)
        results.append(CaseResult(case_id=case["id"], score=s, level=level_for(s, levels), hits=hits))
    return results, ctx, errors
