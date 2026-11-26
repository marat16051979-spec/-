import io
from datetime import date

import pytest

from app import importer


def test_semicolon_bom_and_extra_columns():
    data = "﻿id;product;amount;лишний столбец;contractDate\n1;ПА;1 000 000,50;x;15.03.2026\n".encode("utf-8")
    cases, rep = importer.parse_file("a.csv", data)
    assert rep.loaded == 1
    assert rep.skipped_columns == ["лишний столбец"]
    assert "agent" in rep.missing_columns
    assert cases[0]["amount"] == 1_000_000.5
    assert cases[0]["contractDate"] == date(2026, 3, 15)


def test_comma_without_bom_and_bools():
    data = "id,product,complaint,witnesses,beneficiaryRel\n2,нсж,да,0,Третье лицо\n".encode("utf-8")
    cases, rep = importer.parse_file("b.csv", data)
    c = cases[0]
    assert c["product"] == "НСЖ" and c["complaint"] is True and c["witnesses"] is False
    assert c["beneficiaryRel"] == "третье лицо"


def test_required_columns():
    with pytest.raises(importer.ImportFailed):
        importer.parse_file("c.csv", "id;agent\n1;X\n".encode("utf-8"))


def test_bad_rows_reported_not_fatal():
    data = "id;product;amount;contractDate\n;ПА;1;\n3;ХХХ;1;\n4;ПА;abc;2026-13-40\n".encode("utf-8")
    cases, rep = importer.parse_file("d.csv", data)
    assert rep.loaded == 1 and rep.rejected == 2
    assert cases[0]["amount"] is None and cases[0]["contractDate"] is None
    fields = {e["field"] for e in rep.errors}
    assert {"id", "product", "amount", "contractDate"} <= fields


def test_cp1251_fallback():
    data = "id;product;client\n5;ОСНС;Иванов\n".encode("cp1251")
    cases, _ = importer.parse_file("e.csv", data)
    assert cases[0]["client"] == "Иванов"


def test_xlsx_import():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["id", "product", "contractDate", "amount", "extra"])
    ws.append(["X-1", "ПА", date(2026, 1, 2), 5_000_000, "?"])
    buf = io.BytesIO()
    wb.save(buf)
    cases, rep = importer.parse_file("f.xlsx", buf.getvalue())
    assert cases[0]["contractDate"] == date(2026, 1, 2)
    assert cases[0]["amount"] == 5_000_000
    assert rep.skipped_columns == ["extra"]


def test_roundtrip(sample_cases):
    data = importer.cases_to_csv(sample_cases)
    again, rep = importer.parse_file("r.csv", data)
    assert again == sample_cases and rep.missing_columns == []
