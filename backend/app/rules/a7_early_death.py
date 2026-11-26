"""A7. Схема 3: смерть вскоре после договора ПА."""
from .base import RuleSpec, between, days


def evaluate(c, ctx, p):
    d = days(c.get("contractDate"), c.get("deathDate"))
    if between(d, 0, float(p["d"])):
        return f"смерть через {d} дн. после договора"
    return None


RULE = RuleSpec(
    id="A7",
    scheme="3",
    products=("ПА",),
    name="Смерть вскоре после договора",
    weight=20,
    params={"d": 730},
    param_titles={"d": "Не позднее дней после договора"},
    action="Углублённая проверка обстоятельств смерти (первые 2 года договора)",
    evaluate=evaluate,
)
