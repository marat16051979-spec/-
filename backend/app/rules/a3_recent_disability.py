"""A3. Схема 2: инвалидность установлена незадолго до договора."""
from .base import RuleSpec, between, days


def evaluate(c, ctx, p):
    if c.get("basis") != "инвалидность":
        return None
    d = days(c.get("disabilityDate"), c.get("contractDate"))
    if between(d, 0, float(p["d"])):
        return f"инвалидность за {d} дн. до договора"
    return None


RULE = RuleSpec(
    id="A3",
    scheme="2",
    products=("ПА",),
    name="Инвалидность незадолго до договора",
    weight=25,
    params={"d": 90},
    param_titles={"d": "Не более дней до договора"},
    action="Проверить заключение через государственные системы",
    evaluate=evaluate,
)
