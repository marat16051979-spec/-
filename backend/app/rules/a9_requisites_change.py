"""A9. Схема 4: недавняя ручная смена реквизитов."""
from .base import RuleSpec


def evaluate(c, ctx, p):
    d = c.get("requisitesChangedDays")
    if d is not None and 0 <= d <= int(p["d"]):
        return f"реквизиты изменены вручную {d} дн. назад"
    return None


RULE = RuleSpec(
    id="A9",
    scheme="4",
    products=("ПА", "ОСНС"),
    name="Ручная смена реквизитов",
    weight=10,
    params={"d": 60},
    param_titles={"d": "Не более дней назад"},
    action="Контроль ручных изменений: кто и на основании чего сменил реквизиты; подтверждение у получателя",
    evaluate=evaluate,
)
