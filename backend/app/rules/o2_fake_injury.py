"""O2. ОСНС: признаки фиктивной производственной травмы."""
from .base import RuleSpec

_WEEKDAYS = {5: "субботу", 6: "воскресенье"}


def evaluate(c, ctx, p):
    signs = []
    ev = c.get("eventDate")
    if ev is not None and ev.weekday() in _WEEKDAYS:
        signs.append(f"событие в {_WEEKDAYS[ev.weekday()]}")
    delay = c.get("actDelayDays")
    if delay is not None and delay > int(p["d"]):
        signs.append(f"акт Н-1 через {delay} дн.")
    if c.get("witnesses") is False:
        signs.append("нет свидетелей")
    if len(signs) >= int(p["n"]):
        return "признаки: " + "; ".join(signs)
    return None


RULE = RuleSpec(
    id="O2",
    scheme="ОСНС",
    products=("ОСНС",),
    name="Признаки фиктивной травмы",
    weight=20,
    params={"d": 10, "n": 2},
    param_titles={"d": "Задержка акта Н-1 больше, дней", "n": "Минимум признаков"},
    action="Выезд на место, опрос свидетелей, видеонаблюдение и журналы проходной",
    evaluate=evaluate,
)
