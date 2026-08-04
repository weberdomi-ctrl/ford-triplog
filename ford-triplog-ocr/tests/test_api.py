from fastapi.testclient import TestClient

from app import APP_NAME, APP_VERSION, app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == APP_NAME
    assert payload["version"] == APP_VERSION
    assert payload["engine"] == "rapidocr"
    assert payload["pdf_first_page_only"] is True


def test_unsupported_media_type() -> None:
    response = client.post(
        "/ocr",
        files={"file": ("receipt.txt", b"test", "text/plain")},
    )

    assert response.status_code == 415
