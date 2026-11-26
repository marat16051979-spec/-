"""A4. Схема 2: одно учреждение выдаёт много заключений."""
from .base import RuleSpec


def evaluate(c, ctx, p):
    if c.get("basis") != "инвалидность":
        return None
    issuer = c.get("disabilityIssuer")
    if not issuer:
        return None
    n = ctx.issuer.get(issuer, 0)
    if n >= int(p["n"]):
        return f"источник «{issuer}» выдал заключения по {n} договорам ПА"
    return None


RULE = RuleSpec(
    id="A4",
    scheme="2",
    products=("ПА",),
    name="Кластер заключений одного учреждения",
    weight=20,
    params={"n": 3},
    param_titles={"n": "Договоров на один источник"},
    action="Анализ кластера заключений; при подтверждении — передача материалов в правоохранительные органы",
    evaluate=evaluate,
)
