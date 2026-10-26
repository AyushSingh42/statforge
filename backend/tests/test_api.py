from fastapi.testclient import TestClient

from statforge import __version__
from statforge.api.main import app

client = TestClient(app)


def test_health_reports_version_and_source(monkeypatch):
    monkeypatch.setenv("STATFORGE_DATA_SOURCE", "fixture")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__, "data_source": "fixture"}
