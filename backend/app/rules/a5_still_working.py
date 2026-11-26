"""A5. Схема 2: при инвалидности клиент продолжает работать."""
from .base import RuleSpec


def evaluate(c, ctx, p):
    if c.get("basis") == "инвалидность" and c.get("stillWorking") is True:
        return "основание — инвалидность, но клиент продолжает работать"
    return None


RULE = RuleSpec(
    id="A5",
    scheme="2",
    products=("ПА",),
    name="Инвалидность, но клиент работает",
    weight=15,
    params={},
    action="Сверить с данными о пенсионных взносах и проверить заключение через госсистемы",
    evaluate=evaluate,
)
