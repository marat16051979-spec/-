"""Импорт CSV/XLSX по шаблону полей (PRD 5.1, 7.6).

Обязательны только `id` и `product`. Лишние столбцы пропускаются и попадают в отчёт.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any, Iterable

from .fields import FIELD_BY_NAME, FIELD_NAMES, FIELDS, PRODUCTS, REQUIRED, ParseError, format_value, parse_value

_HEADER_ALIASES = {f.name.lower(): f.name for f in FIELDS}
_HEADER_ALIASES.update({f.title.lower(): f.name for f in FIELDS})


@dataclass
class ImportReport:
    loaded: int = 0
    rejected: int = 0
    skipped_columns: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)  # {row, field, message}

    def as_dict(self) -> dict:
        return {
            "loaded": self.loaded,
            "rejected": self.rejected,
            "skipped_columns": self.skipped_columns,
            "missing_columns": self.missing_columns,
            "errors": self.errors[:200],
            "errors_total": len(self.errors),
        }


class ImportFailed(ValueError):
    pass


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ImportFailed("Не удалось определить кодировку файла (ожидается UTF-8)")


def read_csv_rows(data: bytes) -> tuple[list[str], list[list[Any]]]:
    text = _decode(data)
    first = text.split("\n", 1)[0]
    delim = ";" if first.count(";") >= first.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        raise ImportFailed("Файл пустой")
    return rows[0], rows[1:]


def read_xlsx_rows(data: bytes) -> tuple[list[str], list[list[Any]]]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows = [list(r) for r in ws.iter_rows(values_only=True) if any(v not in (None, "") for v in r)]
    wb.close()
    if not rows:
        raise ImportFailed("Лист пустой")
    header = ["" if h is None else str(h) for h in rows[0]]
    return header, rows[1:]


def parse_rows(header: list[str], rows: Iterable[list[Any]]) -> tuple[list[dict], ImportReport]:
    report = ImportReport()
    mapping: dict[int, str] = {}
    for i, h in enumerate(header):
        key = str(h).strip().lstrip("﻿")
        name = _HEADER_ALIASES.get(key.lower())
        if name and name not in mapping.values():
            mapping[i] = name
        elif key:
            report.skipped_columns.append(key)
    present = set(mapping.values())
    missing_required = [r for r in REQUIRED if r not in present]
    if missing_required:
        raise ImportFailed(f"Нет обязательных столбцов: {', '.join(missing_required)}")
    report.missing_columns = [n for n in FIELD_NAMES if n not in present]

    cases: dict[str, dict] = {}
    for row_no, row in enumerate(rows, start=2):
        case: dict[str, Any] = {n: None for n in FIELD_NAMES}
        for i, name in mapping.items():
            raw = row[i] if i < len(row) else None
            try:
                case[name] = parse_value(FIELD_BY_NAME[name], raw)
            except ParseError as e:
                if name in REQUIRED:
                    case[name] = None
                report.errors.append({"row": row_no, "field": name, "message": str(e)})
        if not case["id"]:
            report.rejected += 1
            report.errors.append({"row": row_no, "field": "id", "message": "пустой id — строка пропущена"})
            continue
        if case["product"] not in PRODUCTS:
            report.rejected += 1
            report.errors.append({"row": row_no, "field": "product", "message": "нет продукта — строка пропущена"})
            continue
        if case["id"] in cases:
            report.errors.append({"row": row_no, "field": "id", "message": f"повтор id {case['id']} — взята последняя строка"})
        cases[case["id"]] = case
    report.loaded = len(cases)
    return list(cases.values()), report


def parse_file(filename: str, data: bytes) -> tuple[list[dict], ImportReport]:
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        header, rows = read_xlsx_rows(data)
    else:
        header, rows = read_csv_rows(data)
    return parse_rows(header, rows)


def template_csv() -> bytes:
    """Пустой шаблон для загрузки: только заголовки."""
    return ("﻿" + ";".join(FIELD_NAMES) + "\n").encode("utf-8")


def cases_to_csv(cases: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(FIELD_NAMES)
    for c in cases:
        w.writerow([format_value(c.get(n)) for n in FIELD_NAMES])
    return ("﻿" + buf.getvalue()).encode("utf-8")
