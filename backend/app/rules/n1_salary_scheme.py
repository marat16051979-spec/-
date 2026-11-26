"""N1. Схема 5: массовый выкуп у корпоративного клиента сразу после 1 года."""
from .base import RuleSpec, between, days


def evaluate(c, ctx, p):
    employer = c.get("employer")
    if not employer:
        return None
    d = days(c.get("contractDate"), c.get("surrenderDate"))
    hi = 365 + int(p["d"])
    if not between(d, 365, hi):
        return None
    n = ctx.corp.get(employer, 0)
    if n >= int(p["n"]):
        return f"выкуп через {d} дн.; у «{employer}» {n} выкупов в окне 365–{hi} дн. после договора"
    return None


RULE = RuleSpec(
    id="N1",
    scheme="5",
    products=("НСЖ",),
    name="Массовый выкуп у работодателя после 1 года",
    weight=20,
    params={"d": 60, "n": 3},
    param_titles={"d": "Окно после 365 дней, дней", "n": "Минимум выкупов у работодателя"},
    action="Анализ экономического смысла договоров; сообщение в комплаенс",
    evaluate=evaluate,
)
