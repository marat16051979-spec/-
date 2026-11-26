"""Критерии приёмки PRD (раздел 11) на tests/fixtures/sample.csv."""
import pytest

from app.scoring import run


@pytest.fixture(scope="module")
def results(sample_cases):
    res, ctx, errors = run(sample_cases)
    assert errors == []
    return {r.case_id: r for r in res}


def rules_of(r) -> set[str]:
    return {h["rule"] for h in r.hits}


CASH = [f"PA-90{i:02d}" for i in range(1, 10)]
CASH_DISABILITY = CASH[:4]


def test_sample_size(sample_cases):
    assert 70 <= len(sample_cases) <= 90


def test_cashback_agent(results):
    for cid in CASH:
        assert {"A1", "A2"} <= rules_of(results[cid]), cid
    for cid in CASH_DISABILITY:
        assert {"A1", "A2", "A3", "A4"} <= rules_of(results[cid]), cid
        assert results[cid].level == "высокий", cid
    assert any("A5" in rules_of(results[c]) for c in CASH_DISABILITY)
    assert "A4" not in rules_of(results["PA-9005"])


def test_guaranteed_period(results):
    r = results["PA-9101"]
    assert rules_of(r) == {"A6", "A7"}
    assert r.level == "средний"


def test_payments_after_death(results):
    r = results["PA-9201"]
    assert rules_of(r) == {"A8", "A9"}
    assert r.level == "высокий"


def test_osns_all_signs(results):
    r = results["OS-9301"]
    assert rules_of(r) == {"O1", "O2", "O3", "O4", "A9"}
    assert r.score == 100 and r.level == "высокий"
    o2 = next(h for h in r.hits if h["rule"] == "O2")
    assert "субботу" in o2["explanation"] and "нет свидетелей" in o2["explanation"]


def test_salary_scheme(results):
    for cid in [f"NS-94{i:02d}" for i in range(1, 6)]:
        assert "N1" in rules_of(results[cid]), cid
        assert results[cid].level == "средний", cid


def test_laundering(results):
    r = results["NS-9501"]
    assert rules_of(r) == {"N2"}
    assert r.level == "высокий"


def test_churning(results):
    for cid in ("NS-9601", "NS-9602", "NS-9603"):
        assert rules_of(results[cid]) == {"N3", "N4"}, cid
        assert results[cid].level == "средний"
    n3 = next(h for h in results["NS-9601"].hits if h["rule"] == "N3")
    assert n3["explanation"] == "карта K-77410 платит за 3 клиентов"
    assert "N4" in rules_of(results["NS-9604"])
    assert rules_of(results["NS-9606"]) == set()   # не выкуплен


def test_hidden_illness(results):
    r = results["NS-9701"]
    assert rules_of(r) == {"N5"}
    assert r.level == "средний"


def test_normal_cases_are_clean(results):
    planted_prefixes = ("PA-90", "PA-91", "PA-92", "OS-93", "NS-94", "NS-95", "NS-96", "NS-97")
    normal = [r for cid, r in results.items() if not cid.startswith(planted_prefixes)]
    assert len(normal) >= 45
    dirty = {r.case_id: rules_of(r) for r in normal if r.hits}
    assert dirty == {}


def test_every_hit_has_explanation_and_action(results):
    for r in results.values():
        for h in r.hits:
            assert h["explanation"] and h["action"], (r.case_id, h)
