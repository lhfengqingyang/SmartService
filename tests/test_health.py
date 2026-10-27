from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)


def test_health_does_not_require_database() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_database_health_reports_ready(monkeypatch) -> None:
    monkeypatch.setattr(main, "check_database", lambda: None)

    response = client.get("/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_database_health_reports_unavailable_without_leaking_error(monkeypatch) -> None:
    def unavailable() -> None:
        raise RuntimeError("secret connection details")

    monkeypatch.setattr(main, "check_database", unavailable)

    response = client.get("/health/db")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is not ready", "error_code": "DATABASE_UNAVAILABLE"}
