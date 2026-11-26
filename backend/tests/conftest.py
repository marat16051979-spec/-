from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import importer
from app.api.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "sample.csv"


@pytest.fixture(scope="session")
def sample_bytes() -> bytes:
    return SAMPLE.read_bytes()


@pytest.fixture(scope="session")
def sample_cases(sample_bytes) -> list[dict]:
    cases, report = importer.parse_file("sample.csv", sample_bytes)
    assert report.rejected == 0, report.errors
    return cases


@pytest.fixture()
def client():
    app = create_app("sqlite://")  # БД в памяти
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def loaded_client(client, sample_bytes):
    r = client.post("/api/import", files={"file": ("sample.csv", sample_bytes, "text/csv")}, data={"mode": "replace"})
    assert r.status_code == 200, r.text
    return client
