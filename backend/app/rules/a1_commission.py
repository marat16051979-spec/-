"""A1. Схема 1: комиссия у предела или жалоба клиента."""
from .base import RuleSpec, num


def evaluate(c, ctx, p):
    reasons = []
    pct = c.get("commissionPct")
    threshold = float(p["lim"]) * float(p["sh"]) / 100
    if pct is not None and pct >= threshold:
        reasons.append(f"комиссия {num(pct)}% при пределе {num(p['lim'])}% (порог {num(threshold)}%)")
    if c.get("complaint") is True:
        reasons.append("есть жалоба клиента")
    return "; ".join(reasons) or None


RULE = RuleSpec(
    id="A1",
    scheme="1",
    products=("ПА",),
    name="Комиссия у предела или жалоба клиента",
    weight=25,
    params={"lim": 5, "sh": 90},
    param_titles={"lim": "Предел комиссии, %", "sh": "Доля предела для срабатывания, %"},
    action="Контрольный звонок клиенту без агента; отсрочка и возврат (clawback) комиссии",
    evaluate=evaluate,
)
