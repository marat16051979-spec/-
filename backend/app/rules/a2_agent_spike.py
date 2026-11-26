"""A2. Схема 1: всплеск продаж ПА у агента."""
from .base import RuleSpec, num


def evaluate(c, ctx, p):
    agent = c.get("agent")
    cd = c.get("contractDate")
    if not agent or cd is None or ctx.pa_window_start is None:
        return None
    if not (ctx.pa_window_start <= cd <= ctx.as_of):
        return None
    recent = ctx.paRecent.get(agent, 0)
    threshold = max(float(p["min"]), float(p["k"]) * ctx.paMed)
    if recent >= threshold:
        return (
            f"у агента {agent} {recent} договоров ПА за {num(p['win'])} дн. "
            f"(медиана по агентам {num(ctx.paMed)}, порог {num(threshold)})"
        )
    return None


RULE = RuleSpec(
    id="A2",
    scheme="1",
    products=("ПА",),
    name="Всплеск продаж ПА у агента",
    weight=15,
    params={"win": 90, "k": 3, "min": 4},
    param_titles={"win": "Окно, дней", "k": "Кратность медианы", "min": "Минимум договоров"},
    action="Мониторинг концентрации продаж агента; выборочные контрольные звонки его клиентам",
    evaluate=evaluate,
)
