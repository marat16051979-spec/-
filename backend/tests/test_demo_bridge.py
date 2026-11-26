"""Демо-мост (то, что работает в браузере на GitHub Pages) проверяется в обычном Python."""
import base64
import json

import pytest

from app.demo_bridge import Demo


@pytest.fixture(scope="module")
def demo(sample_bytes):
    d = Demo()
    rep = d.load("sample.csv", sample_bytes)
    assert rep["loaded"] == 75
    return d


def call(demo, method, path, query="", body=None, **kw):
    return json.loads(demo.request(method, path, query, json.dumps(body) if body else "", **kw))


def test_summary_and_queue(demo):
    s = call(demo, "GET", "/api/summary")
    assert s["status"] == 200 and s["json"]["total"] == 75 and s["json"]["high"] == 7
    q = call(demo, "GET", "/api/cases", "flagged=true&limit=5")["json"]
    assert len(q["items"]) == 5 and q["items"][0]["score"] == 100


def test_case_status_rules_levels(demo):
    assert call(demo, "GET", "/api/cases/PA-9201")["json"]["level"] == "высокий"
    r = call(demo, "PATCH", "/api/cases/PA-9201/status", body={"status": "Подтверждено", "comment": "ок"})
    assert r["json"]["status"] == "Подтверждено"
    assert call(demo, "GET", "/api/cases/NOPE")["status"] == 404
    assert call(demo, "PATCH", "/api/rules/N5", body={"weight": 55})["json"]["weight"] == 55
    assert call(demo, "GET", "/api/cases/NS-9701")["json"]["score"] == 55
    assert call(demo, "POST", "/api/rules/N5/reset")["json"]["weight"] == 25
    assert call(demo, "PUT", "/api/settings/levels", body={"high": 10, "medium": 30})["status"] == 422
    assert call(demo, "GET", "/api/rules/history")["json"][0]["rule"] == "N5"


def test_files(demo):
    r = call(demo, "GET", "/api/export", "fmt=xlsx")
    assert r["filename"].endswith(".xlsx") and base64.b64decode(r["file_b64"])[:2] == b"PK"
    t = call(demo, "GET", "/api/import/template")
    assert base64.b64decode(t["file_b64"]).decode("utf-8-sig").startswith("id;product")


def test_import_via_bridge(demo):
    data = "id;product;paymentsAfterDeath;extra\nX-1;ПА;2;1\n".encode("utf-8")
    r = call(demo, "POST", "/api/import", body={"mode": "append"}, filename="x.csv", file_data=data)
    assert r["json"]["skipped_columns"] == ["extra"] and r["json"]["total_cases"] == 76
    assert call(demo, "GET", "/api/cases/X-1")["json"]["score"] == 50


def test_unknown_route(demo):
    assert call(demo, "GET", "/api/nope")["status"] == 404
