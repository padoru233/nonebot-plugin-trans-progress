from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import nonebot

    nonebot.init()

    from nonebot_plugin_trans_progress import web

    for name, value in {
        "moeflow_web_url": "https://moeflow.example.com",
        "moeflow_api_url": "https://moeflow.example.com/bot-auth",
        "trans_moeflow_client_secret": "client-secret",
        "trans_moeflow_redirect_uri": "https://bot.example.com/trans/auth/moeflow/callback",
        "trans_auth_session_secret": "session-secret",
        "trans_moeflow_allowed_subjects": ["allowed-user"],
    }.items():
        monkeypatch.setattr(web.plugin_config, name, value)

    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key="session-secret",
        session_cookie="trans_admin_session",
        same_site="lax",
        https_only=True,
    )
    app.include_router(web.api_router)
    app.include_router(web.public_router)
    return TestClient(app, base_url="https://bot.example.com")


def stub_moeflow_identity(monkeypatch: pytest.MonkeyPatch, identity: dict) -> None:
    async def post(self, url, **kwargs):
        return httpx.Response(
            200, json=identity, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)


def start_login(client: TestClient) -> str:
    response = client.get("/auth/moeflow/login", follow_redirects=False)
    assert response.status_code == 303
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def test_unauthenticated_api_requires_login(client: TestClient):
    assert client.get("/auth/me").status_code == 401


def test_callback_without_login_attempt_shows_retry_page(client: TestClient):
    response = client.get("/auth/moeflow/callback?code=abc&state=xyz")

    assert response.status_code == 400
    assert "重新登录" in response.text


def test_callback_rejects_non_ascii_state_without_server_error(client: TestClient):
    start_login(client)

    response = client.get(
        "/auth/moeflow/callback", params={"code": "c", "state": "状态"}
    )

    assert response.status_code == 400


def test_admin_can_log_in_see_identity_and_log_out(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    state = start_login(client)
    stub_moeflow_identity(
        monkeypatch, {"subject": "admin-1", "name": "Admin", "admin": True}
    )

    callback = client.get(
        "/auth/moeflow/callback",
        params={"code": "c", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert callback.headers["location"] == "/trans/"
    assert client.get("/auth/me").json() == {"subject": "admin-1", "name": "Admin"}

    assert client.post("/auth/logout").status_code == 200
    assert client.get("/auth/me").status_code == 401


def test_allow_listed_user_can_log_in(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    state = start_login(client)
    stub_moeflow_identity(
        monkeypatch, {"subject": "allowed-user", "name": "Ally", "admin": False}
    )

    client.get(
        "/auth/moeflow/callback",
        params={"code": "c", "state": state},
        follow_redirects=False,
    )

    assert client.get("/auth/me").json()["name"] == "Ally"


def test_unlisted_user_sees_their_id_and_gets_no_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    state = start_login(client)
    stub_moeflow_identity(
        monkeypatch, {"subject": "stranger-9", "name": "<b>Eve</b>", "admin": False}
    )

    response = client.get(
        "/auth/moeflow/callback", params={"code": "c", "state": state}
    )

    assert response.status_code == 403
    assert "stranger-9" in response.text
    assert "&lt;b&gt;Eve&lt;/b&gt;" in response.text
    assert "<b>Eve</b>" not in response.text
    assert client.get("/auth/me").status_code == 401


def test_logged_out_page_offers_to_log_in_again(client: TestClient):
    response = client.get("/auth/logged-out")

    assert response.status_code == 200
    assert "已退出登录" in response.text
    assert "/trans/auth/moeflow/login" in response.text
