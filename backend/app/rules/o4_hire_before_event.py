"""O4. ОСНС: приём на работу незадолго до события."""
from .base import RuleSpec, between, days


def evaluate(c, ctx, p):
    d = days(c.get("hireDate"), c.get("eventDate"))
    if between(d, 0, float(p["d"])):
        return f"принят на работу за {d} дн. до события"
    return None


RULE = RuleSpec(
    id="O4",
    scheme="ОСНС",
    products=("ОСНС",),
    name="Приём на работу перед событием",
    weight=30,
    params={"d": 30},
    param_titles={"d": "Не более дней до события"},
    action="Сверка с ЕСБД и пенсионными взносами",
    evaluate=evaluate,
)
