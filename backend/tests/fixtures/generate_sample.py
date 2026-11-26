"""Генератор tests/fixtures/sample.csv (PRD, раздел 11).

Все данные вымышленные. Запуск из папки backend:
    python tests/fixtures/generate_sample.py
Генерация детерминирована (seed=42): повторный запуск даёт тот же файл.
"""
from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.fields import FIELD_NAMES  # noqa: E402
from app.importer import cases_to_csv  # noqa: E402

OUT = Path(__file__).with_name("sample.csv")
AS_OF = date(2026, 10, 31)  # самая поздняя дата договора в наборе → дата отсчёта окна A2
D = timedelta

SURNAMES = ["Ахметов", "Беков", "Жумабаев", "Иванов", "Касымов", "Ли", "Мусин", "Нурланов", "Омаров", "Петров",
            "Рахимов", "Сейткали", "Тулегенов", "Утепов", "Хасенов", "Шаймерденов", "Есенов", "Абенов",
            "Данияров", "Ким", "Гусейнов", "Бекмуханов", "Садыков", "Темиров"]
INITIALS = "АБГДЕЖКМНОРСТ"
REGIONS = ["Алматы", "Астана", "Шымкент", "Карагандинская обл.", "Актюбинская обл.", "Павлодарская обл.",
           "Восточно-Казахстанская обл.", "Атырауская обл."]
NORMAL_PA_AGENTS = [f"АГ-{n:02d} {s}" for n, s in zip(range(1, 9), ["Абдиев Н.", "Брагина О.", "Валиев Т.",
                     "Гарипова С.", "Дюсенов К.", "Ергалиева А.", "Жанибеков М.", "Зайцева Л."])]
NORMAL_NSJ_AGENTS = ["АГ-21 Исаева Д.", "АГ-22 Каримов Б.", "АГ-23 Лукина В.", "АГ-24 Маратов Ж."]
EMPLOYERS = ["ТОО «Северный элеватор»", "АО «КазТрансЛогистик»", "ТОО «Степной цемент»", "ТОО «Каспий Сервис Ойл»"]

rnd = random.Random(42)
_used_clients: set[str] = set()


def client() -> str:
    while True:
        name = f"{rnd.choice(SURNAMES)} {rnd.choice(INITIALS)}.{rnd.choice(INITIALS)}."
        if name not in _used_clients:
            _used_clients.add(name)
            return name


def blank(**kw) -> dict:
    row = {n: None for n in FIELD_NAMES}
    row.update(kw)
    return row


def suspicious() -> list[dict]:
    rows = []

    # 1. Кэшбэк: агент с 9 договорами ПА за 85 дней, комиссия 4,6–5 %, 4 — с инвалидностью от «МСЭ, отдел №4».
    cash_agent = "АГ-17 Сапаров Е."
    offsets = [0, 10, 20, 30, 40, 50, 60, 70, 85]
    comm = [4.6, 4.7, 4.8, 4.9, 5.0, 4.6, 4.7, 4.8, 5.0]
    disab = {0: (15, False), 1: (27, True), 2: (45, False), 3: (70, True)}  # дней до договора, работает
    for i, (off, c) in enumerate(zip(offsets, comm)):
        cd = AS_OF - D(off)
        r = blank(id=f"PA-90{i + 1:02d}", product="ПА", client=client(), agent=cash_agent, region="Шымкент",
                  contractDate=cd, amount=rnd.randrange(6, 18) * 1_000_000, commissionPct=c, complaint=False,
                  basis="возраст", beneficiaryRel="родственник", beneficiaryAddedDays=rnd.randrange(400, 2000),
                  paymentsAfterDeath=0)
        if i in disab:
            before, working = disab[i]
            r.update(basis="инвалидность", disabilityDate=cd - D(before), disabilityIssuer="МСЭ, отдел №4",
                     stillWorking=working)
        rows.append(r)

    # 2. Гарантированный период: выгодоприобретатель — третье лицо, назначен за 10 дней, смерть через 240 дней.
    cd = date(2025, 3, 1)
    rows.append(blank(id="PA-9101", product="ПА", client=client(), agent=NORMAL_PA_AGENTS[0], region="Алматы",
                      contractDate=cd, amount=14_500_000, commissionPct=2.5, complaint=False, basis="возраст",
                      beneficiaryRel="третье лицо", beneficiaryAddedDays=10, deathDate=cd + D(240),
                      paymentsAfterDeath=0))

    # 3. Выплаты умершему: 5 выплат после смерти, реквизиты изменены 40 дней назад.
    rows.append(blank(id="PA-9201", product="ПА", client=client(), agent=NORMAL_PA_AGENTS[1], region="Астана",
                      contractDate=date(2019, 4, 1), amount=9_800_000, commissionPct=2.0, complaint=False,
                      basis="возраст", beneficiaryRel="родственник", beneficiaryAddedDays=900,
                      deathDate=date(2026, 5, 10), paymentsAfterDeath=5, requisitesChangedDays=40))

    # 4. ОСНС: событие в субботу, принят за 12 дней, зарплата 310 → 650 тыс., акт через 18 дней,
    #    без свидетелей, утрата 70 % при лёгком диагнозе.
    ev = date(2026, 3, 14)
    assert ev.weekday() == 5, "событие должно быть в субботу"
    rows.append(blank(id="OS-9301", product="ОСНС", client=client(), agent="АГ-41 Оспанов Г.",
                      region="Карагандинская обл.", contractDate=date(2025, 12, 1), amount=38_000_000,
                      employer="ТОО «Карьер-Сервис Центр»", eventDate=ev, hireDate=ev - D(12), actDelayDays=18,
                      witnesses=False, salaryAvg12=310_000, salaryLast=650_000, lossPct=70, diagnosis="лёгкий",
                      requisitesChangedDays=25))

    # 5. НСЖ, зарплатная схема: 5 договоров одного ТОО, выкуп через 366–395 дней.
    #    Премии платит работодатель со своего счёта (один плательщик за пятерых — сработает и N3).
    employer = "ТОО «Альфа-Строй Сервис»"
    for i, d in enumerate([366, 373, 380, 388, 395]):
        cd = date(2025, 1, 10) + D(i * 3)
        rows.append(blank(id=f"NS-94{i + 1:02d}", product="НСЖ", client=client(), agent="АГ-51 Корпоративный отдел",
                          region="Алматы", contractDate=cd, amount=1_200_000, employer=employer, payer="третье лицо",
                          payerCard="СЧ-ТОО-4410", surrenderDate=cd + D(d), payoutSameAccount=False,
                          medUnderwriting=True))

    # 6. Отмывание: премия 45 млн, платит третье лицо, выкуп через 120 дней на другой счёт.
    cd = date(2026, 2, 1)
    rows.append(blank(id="NS-9501", product="НСЖ", client=client(), agent="АГ-52 Брокер Плюс", region="Атырауская обл.",
                      contractDate=cd, amount=45_000_000, payer="третье лицо", payerCard="K-55019",
                      surrenderDate=cd + D(120), payoutSameAccount=False, medUnderwriting=True))

    # 7. Чёрнинг: одна карта платит за 3 клиентов, у агента 5 выкупов в первый год из 6 договоров.
    churn = "АГ-31 Калиев Р."
    for i in range(6):
        cd = date(2025, 4, 1) + D(i * 20)
        r = blank(id=f"NS-96{i + 1:02d}", product="НСЖ", client=client(), agent=churn, region="Павлодарская обл.",
                  contractDate=cd, amount=600_000 + i * 50_000, payer="сам", payerCard=f"K-6{i:04d}",
                  payoutSameAccount=True, medUnderwriting=True)
        if i < 3:
            r.update(payer="третье лицо", payerCard="K-77410")
        if i < 5:
            r.update(surrenderDate=cd + D(150 + i * 30))
        rows.append(r)

    # 8. Скрытая болезнь: премия 12 млн без андеррайтинга, смерть за рубежом через 270 дней.
    cd = date(2025, 6, 1)
    rows.append(blank(id="NS-9701", product="НСЖ", client=client(), agent=NORMAL_NSJ_AGENTS[0], region="Алматы",
                      contractDate=cd, amount=12_000_000, payer="сам", payerCard="K-70012", payoutSameAccount=True,
                      medUnderwriting=False, deathDate=cd + D(270), deathAbroad=True))
    return rows


def normal() -> list[dict]:
    rows = []
    # 20 обычных ПА: договоры раньше окна A2, комиссия 1,5–3,5 %, выгодоприобретатель — родственник.
    for i in range(20):
        cd = AS_OF - D(rnd.randrange(120, 1400))
        r = blank(id=f"PA-{1001 + i}", product="ПА", client=client(), agent=NORMAL_PA_AGENTS[i % 8],
                  region=rnd.choice(REGIONS), contractDate=cd, amount=rnd.randrange(3, 26) * 1_000_000,
                  commissionPct=round(rnd.uniform(1.5, 3.5), 1), complaint=False, basis="возраст",
                  beneficiaryRel="родственник", beneficiaryAddedDays=rnd.randrange(200, 2500), paymentsAfterDeath=0,
                  requisitesChangedDays=rnd.choice([None, rnd.randrange(200, 1500)]))
        if i % 7 == 3:  # инвалидность давно, у каждого своё учреждение
            r.update(basis="инвалидность", disabilityDate=cd - D(rnd.randrange(400, 2000)),
                     disabilityIssuer=f"МСЭ, отдел №{10 + i}", stillWorking=False)
        rows.append(r)

    # 15 обычных ОСНС: событие в будний день, акт вовремя, есть свидетели, зарплата без скачка.
    for i in range(15):
        ev = AS_OF - D(rnd.randrange(30, 900))
        while ev.weekday() >= 5:
            ev -= D(1)
        avg = rnd.randrange(180, 700) * 1000
        loss = rnd.randrange(10, 45)
        rows.append(blank(id=f"OS-{2001 + i}", product="ОСНС", client=client(), agent=f"АГ-4{2 + i % 3} ОСНС-отдел",
                          region=rnd.choice(REGIONS), contractDate=ev - D(rnd.randrange(60, 300)),
                          amount=rnd.randrange(5, 40) * 1_000_000, employer=rnd.choice(EMPLOYERS), eventDate=ev,
                          hireDate=ev - D(rnd.randrange(700, 4000)), actDelayDays=rnd.randrange(1, 8), witnesses=True,
                          salaryAvg12=avg, salaryLast=round(avg * rnd.uniform(0.9, 1.2), -3), lossPct=loss,
                          diagnosis=rnd.choice(["лёгкий", "средний", "тяжёлый"])))

    # 15 обычных НСЖ: платит сам, разные карты, без раннего выкупа и смерти.
    for i in range(15):
        cd = AS_OF - D(rnd.randrange(30, 1500))
        surrender = cd + D(rnd.randrange(800, 1200)) if i % 5 == 0 else None
        if surrender and surrender > AS_OF:
            surrender = None
        rows.append(blank(id=f"NS-{3001 + i}", product="НСЖ", client=client(), agent=NORMAL_NSJ_AGENTS[i % 4],
                          region=rnd.choice(REGIONS), contractDate=cd, amount=rnd.randrange(5, 80) * 100_000,
                          payer="сам", payerCard=f"K-{30000 + i}", surrenderDate=surrender,
                          payoutSameAccount=True, medUnderwriting=True))
    return rows


def main() -> None:
    rows = suspicious() + normal()
    assert max(r["contractDate"] for r in rows) == AS_OF
    OUT.write_bytes(cases_to_csv(rows))
    print(f"{OUT}: {len(rows)} дел")


if __name__ == "__main__":
    main()
