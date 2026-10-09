import pytest
from fastapi.testclient import TestClient

from falxon import http as fhttp
from web.app import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_home_page_renders():
    r = client.get("/")
    assert r.status_code == 200
    assert "Check the facts" in r.text and "Falxon" in r.text


def test_form_check_redirects_to_report_and_renders():
    r = client.post("/check", data={"claim": "Sydney is the capital of Australia."}, follow_redirects=False)
    assert r.status_code == 303
    page = client.get(r.headers["location"])
    assert page.status_code == 200
    assert "False" in page.text and "Canberra" in page.text


def test_repeat_claim_uses_cache():
    a = client.post("/check", data={"claim": "Canberra is the capital of Australia."}, follow_redirects=False)
    b = client.post("/check", data={"claim": "Canberra is the capital of Australia."}, follow_redirects=False)
    assert a.headers["location"] == b.headers["location"]


def test_api_verify_and_fetch_report():
    r = client.post("/api/v1/verify", json={"claim": "The Eiffel Tower is located in Paris."})
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"]["label"] == "SUPPORTED"
    again = client.get(f"/api/v1/reports/{body['id']}")
    assert again.json()["claim"] == "The Eiffel Tower is located in Paris."


def test_api_rejects_empty_claim():
    r = client.post("/api/v1/verify", json={"claim": ""})
    assert r.status_code == 400 and "error" in r.json()


def test_article_from_text():
    text = ("Officials spoke on Monday. The Eiffel Tower is located in London, the report claimed. "
            "Sydney is the capital of Australia, according to the post. I think it is lovely.")
    r = client.post("/check-article", data={"text": text}, follow_redirects=False)
    assert r.status_code == 303
    page = client.get(r.headers["location"])
    assert page.status_code == 200 and "checkable statement" in page.text


def test_archive_and_methodology_render():
    assert client.get("/archive").status_code == 200
    assert client.get("/methodology").status_code == 200


def test_unknown_report_is_404():
    assert client.get("/report/nope").status_code == 404


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/admin", "http://169.254.169.254/latest/meta-data/", "http://localhost:8000/",
    "file:///etc/passwd", "ftp://example.com/x", "http://user:pw@example.com/",
])
def test_url_fetch_blocks_private_and_odd_addresses(url):
    with pytest.raises(fhttp.UnsafeURLError):
        fhttp.fetch_public_page(url)
