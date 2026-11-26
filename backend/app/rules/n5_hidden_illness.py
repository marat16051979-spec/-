"""N5. Схема 8: смерть в первые годы без андеррайтинга или за рубежом."""
from .base import RuleSpec, between, days


def evaluate(c, ctx, p):
    d = days(c.get("contractDate"), c.get("deathDate"))
    if not between(d, 0, float(p["d"])):
        return None
    reasons = []
    if c.get("medUnderwriting") is False:
        reasons.append("без медицинского андеррайтинга")
    if c.get("deathAbroad") is True:
        reasons.append("смерть за рубежом")
    if not reasons:
        return None
    return f"смерть через {d} дн. после договора; " + "; ".join(reasons)


RULE = RuleSpec(
    id="N5",
    scheme="8",
    products=("НСЖ",),
    name="Ранняя смерть без андеррайтинга или за рубежом",
    weight=25,
    params={"d": 730},
    param_titles={"d": "Не позднее дней после договора"},
    action="Проверка документов о смерти через госорганы; медицинский андеррайтинг для крупных сумм",
    evaluate=evaluate,
)
