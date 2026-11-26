"""N2. Схема 6: крупная премия и быстрый выкуп (признаки отмывания)."""
from .base import RuleSpec, between, days, money


def evaluate(c, ctx, p):
    amount = c.get("amount")
    if amount is None or amount < float(p["a"]):
        return None
    d = days(c.get("contractDate"), c.get("surrenderDate"))
    if not between(d, 0, float(p["d"])):
        return None
    reasons = []
    if c.get("payer") == "третье лицо":
        reasons.append("платит третье лицо")
    if c.get("payoutSameAccount") is False:
        reasons.append("выкуп на другой счёт")
    if not reasons:
        return None
    return f"премия {money(amount)}, выкуп через {d} дн.; " + "; ".join(reasons)


RULE = RuleSpec(
    id="N2",
    scheme="6",
    products=("НСЖ",),
    name="Крупная премия и быстрый выкуп",
    weight=50,
    params={"a": 10_000_000, "d": 365},
    param_titles={"a": "Премия от, ₸", "d": "Выкуп не позднее, дней"},
    action="Выкуп только на исходный счёт; проверка источника средств; сообщение в АФМ",
    evaluate=evaluate,
)
