"""Мост для демо-версии на GitHub Pages: API работает в браузере через Pyodide.

Тот же код движка и обработчиков, что и на сервере; БД — SQLite в памяти вкладки.
JS вызывает Demo.request(...) вместо сетевого запроса и получает JSON-строку.
"""
from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import parse_qsl

from . import services
from .api import handlers
from .db import make_engine, make_session_factory

DEMO_USER = "демо"


class Demo:
    def __init__(self, database_url: str = "sqlite://"):
        self.engine = make_engine(database_url)
        self.Session = make_session_factory(self.engine)
        services.init_db(self.engine, self.Session)

    def load(self, filename: str, data: bytes) -> dict:
        if hasattr(data, "to_bytes"):  # Uint8Array из JS (Pyodide JsProxy)
            data = data.to_bytes()
        with self.Session() as s:
            out = handlers.import_file(s, DEMO_USER, filename, bytes(data))
            s.commit()
        return out

    def request(self, method: str, path: str, query: str = "", body_json: str = "",
                filename: str = "", file_data: Any = None) -> str:
        """Ответ — JSON-строка {status, json} или {status, file_b64, media_type, filename}."""
        q = dict(parse_qsl(query or "", keep_blank_values=False))
        body: dict = json.loads(body_json) if body_json else {}
        if file_data is not None:
            if hasattr(file_data, "to_bytes"):  # Uint8Array из JS (Pyodide JsProxy)
                file_data = file_data.to_bytes()
            body = {**body, "filename": filename, "data": bytes(file_data)}
        with self.Session() as s:
            try:
                result = handlers.dispatch(s, method.upper(), path, q, body, DEMO_USER)
                s.commit()
            except handlers.ApiError as e:
                s.rollback()
                return json.dumps({"status": e.status, "json": {"detail": e.detail}}, ensure_ascii=False)
            except Exception as e:  # noqa: BLE001 — показать ошибку в интерфейсе, а не уронить демо
                s.rollback()
                return json.dumps({"status": 500, "json": {"detail": f"{type(e).__name__}: {e}"}}, ensure_ascii=False)
        if isinstance(result, handlers.FileOut):
            return json.dumps({
                "status": 200, "file_b64": base64.b64encode(result.content).decode("ascii"),
                "media_type": result.media_type, "filename": result.filename,
            })
        return json.dumps({"status": 200, "json": result}, ensure_ascii=False, default=str)
