import io


def test_import_report_and_queue(loaded_client):
    c = loaded_client
    q = c.get("/api/cases", params={"flagged": "true", "limit": 1000}).json()
    assert q["total"] > 0
    scores = [r["score"] for r in q["items"]]
    assert scores == sorted(scores, reverse=True)
    assert q["items"][0]["score"] == 100


def test_extra_columns_in_upload(client):
    data = "id;product;foo\n1;ПА;x\n".encode("utf-8")
    r = client.post("/api/import", files={"file": ("x.csv", data, "text/csv")})
    assert r.status_code == 200
    assert r.json()["skipped_columns"] == ["foo"]


def test_bad_file_is_422(client):
    r = client.post("/api/import", files={"file": ("x.csv", b"a;b\n1;2\n", "text/csv")})
    assert r.status_code == 422


def test_filters(loaded_client):
    c = loaded_client
    r = c.get("/api/cases", params={"product": "НСЖ", "scheme": "6"}).json()
    assert [x["id"] for x in r["items"]] == ["NS-9501"]
    r = c.get("/api/cases", params={"q": "альфа-строй"}).json()
    assert r["total"] == 5
    r = c.get("/api/cases", params={"level": "высокий"}).json()
    assert all(x["level"] == "высокий" for x in r["items"])


def test_case_card_and_status(loaded_client):
    c = loaded_client
    card = c.get("/api/cases/PA-9201").json()
    assert {h["rule"] for h in card["hits"]} == {"A8", "A9"}
    assert card["status"] == "Новое"
    r = c.patch("/api/cases/PA-9201/status", json={"status": "Подтверждено", "assignee": "Аналитик 1", "comment": "Сверено"})
    assert r.status_code == 200
    card = c.get("/api/cases/PA-9201").json()
    assert card["status"] == "Подтверждено" and card["assignee"] == "Аналитик 1"
    assert card["history"][-1]["comment"] == "Сверено"
    assert c.patch("/api/cases/PA-9201/status", json={"status": "???"}).status_code == 422
    assert c.patch("/api/cases/NOPE/status", json={"status": "Новое"}).status_code == 404

    calib = {x["rule"]: x for x in c.get("/api/calibration").json()}
    assert calib["A8"]["confirmed"] == 1 and calib["A8"]["precision_pct"] == 100.0


def test_weight_change_recalculates_and_is_logged(loaded_client):
    c = loaded_client
    before = c.get("/api/cases/NS-9701").json()
    assert before["score"] == 25 and before["level"] == "средний"
    v0 = c.get("/api/meta").json()["ruleset_version"]

    r = c.patch("/api/rules/N5", json={"weight": 55})
    assert r.status_code == 200 and r.json()["weight"] == 55
    after = c.get("/api/cases/NS-9701").json()
    assert after["score"] == 55 and after["level"] == "высокий"
    assert after["run"]["ruleset_version"] == v0 + 1

    hist = c.get("/api/rules/history").json()
    assert hist[0]["rule"] == "N5" and hist[0]["field"] == "weight" and hist[0]["old"] == 25 and hist[0]["new"] == 55

    c.post("/api/rules/N5/reset")
    assert c.get("/api/cases/NS-9701").json()["score"] == 25


def test_param_change_and_disable(loaded_client):
    c = loaded_client
    assert c.patch("/api/rules/N2", json={"params": {"a": 50_000_000}}).status_code == 200
    assert c.get("/api/cases/NS-9501").json()["hits"] == []
    assert c.patch("/api/rules/N2", json={"params": {"zzz": 1}}).status_code == 422
    assert c.patch("/api/rules/N2", json={"weight": 500}).status_code == 422
    c.post("/api/rules/N2/reset")
    assert c.patch("/api/rules/A8", json={"enabled": False}).status_code == 200
    assert "A8" not in {h["rule"] for h in c.get("/api/cases/PA-9201").json()["hits"]}


def test_levels_setting(loaded_client):
    c = loaded_client
    assert c.put("/api/settings/levels", json={"high": 30, "medium": 10}).status_code == 200
    assert c.get("/api/cases/PA-9101").json()["level"] == "высокий"   # 35 баллов
    assert c.put("/api/settings/levels", json={"high": 10, "medium": 30}).status_code == 422


def test_summary_and_agents(loaded_client):
    c = loaded_client
    s = c.get("/api/summary").json()
    assert s["total"] >= 70 and s["high"] > 0 and s["high_agents"] > 0
    assert sum(x["count"] for x in s["by_scheme"]) > 0
    agents = c.get("/api/agents").json()
    assert agents[0]["agent"] == "АГ-17 Сапаров Е."
    churn = next(a for a in agents if a["agent"] == "АГ-31 Калиев Р.")
    assert churn["nsj_first_year_lapse_pct"] == 83.3


def test_export(loaded_client):
    c = loaded_client
    r = c.get("/api/export", params={"fmt": "csv"})
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    assert text.splitlines()[0] == "ID;Продукт;Клиент;Агент;Балл;Уровень;Правила;Статус"
    r = c.get("/api/export", params={"fmt": "xlsx"})
    from openpyxl import load_workbook

    ws = load_workbook(io.BytesIO(r.content)).active
    assert ws.cell(1, 1).value == "ID" and ws.max_row > 70


def test_audit_log(loaded_client):
    c = loaded_client
    c.get("/api/cases/PA-9001")
    actions = {x["action"] for x in c.get("/api/audit").json()}
    assert {"import", "recalculate", "case_view"} <= actions


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Антифрод" in r.text
