"""N3. Схема 7: одна карта платит за разных клиентов."""
from .base import RuleSpec


def evaluate(c, ctx, p):
    card = c.get("payerCard")
    if not card:
        return None
    n = ctx.card.get(card, 0)
    if n >= int(p["n"]):
        return f"карта {card} платит за {n} клиентов"
    return None


RULE = RuleSpec(
    id="N3",
    scheme="7",
    products=("НСЖ",),
    name="Одна карта платит за разных клиентов",
    weight=20,
    params={"n": 2},
    param_titles={"n": "Клиентов на одну карту"},
    action="Проверить связь плательщика с клиентами и агентом; возврат комиссии при подтверждении",
    evaluate=evaluate,
)
