"""N4. Схема 7: высокая доля выкупов в первый год у агента."""
from .base import RuleSpec, days, first_year_surrender, num


def evaluate(c, ctx, p):
    agent = c.get("agent")
    if not agent or not first_year_surrender(c):
        return None
    lp = ctx.lapse.get(agent)
    if lp is None or lp.n < int(p["n"]):
        return None
    pct = lp.ratio * 100
    if pct >= float(p["r"]):
        d = days(c.get("contractDate"), c.get("surrenderDate"))
        return (
            f"у агента {agent} {lp.lapsed} из {lp.n} договоров НСЖ выкуплены в первый год "
            f"({num(round(pct))}%); это дело выкуплено через {d} дн."
        )
    return None


RULE = RuleSpec(
    id="N4",
    scheme="7",
    products=("НСЖ",),
    name="Высокая доля выкупов в первый год у агента",
    weight=15,
    params={"r": 30, "n": 3},
    param_titles={"r": "Доля выкупов от, %", "n": "Минимум договоров у агента"},
    action="Возврат комиссии первого года; контроль метрики устойчивости портфеля агента",
    evaluate=evaluate,
)
