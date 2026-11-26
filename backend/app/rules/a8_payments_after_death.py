"""A8. Схема 4: выплаты после даты смерти."""
from .base import RuleSpec


def evaluate(c, ctx, p):
    n = c.get("paymentsAfterDeath")
    if n is not None and n > 0:
        return f"{n} выплат(ы) после даты смерти"
    return None


RULE = RuleSpec(
    id="A8",
    scheme="4",
    products=("ПА",),
    name="Выплаты после смерти",
    weight=50,
    params={},
    action="Остановить выплаты до подтверждения, что получатель жив; сверка с регистром смертей; возврат переплаты",
    evaluate=evaluate,
)
