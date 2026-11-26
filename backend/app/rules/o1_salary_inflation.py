"""O1. ОСНС: завышение зарплаты перед событием."""
from .base import RuleSpec, money, num


def evaluate(c, ctx, p):
    last, avg = c.get("salaryLast"), c.get("salaryAvg12")
    if last is None or not avg:
        return None
    ratio = last / avg
    if ratio >= float(p["k"]):
        return f"зарплата в месяц события {money(last)} при средней {money(avg)} (×{num(round(ratio, 2))})"
    return None


RULE = RuleSpec(
    id="O1",
    scheme="ОСНС",
    products=("ОСНС",),
    name="Завышение зарплаты перед событием",
    weight=25,
    params={"k": 1.5},
    param_titles={"k": "Кратность к средней за 12 мес."},
    action="Сверка с пенсионными и налоговыми отчислениями за 12 месяцев",
    evaluate=evaluate,
)
