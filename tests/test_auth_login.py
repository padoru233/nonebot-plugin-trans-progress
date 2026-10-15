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
        "trans_moeflow_team_groups": {"team-1": ["111", "222"]},
        "trans_webhook_token": "webhook-secret",
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
    app.include_router(web.webhook_router)
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
    assert client.get("/auth/me").json() == {
        "subject": "admin-1",
        "name": "Admin",
        "groups": None,
        "moeflow_url": "https://moeflow.example.com",
    }

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
    assert 'href="https://moeflow.example.com"' in response.text


def log_in_as(client: TestClient, monkeypatch: pytest.MonkeyPatch, identity: dict):
    state = start_login(client)
    stub_moeflow_identity(monkeypatch, identity)
    return client.get(
        "/auth/moeflow/callback",
        params={"code": "c", "state": state},
        follow_redirects=False,
    )


def team_admin(team_id: str = "team-1") -> dict:
    return {
        "subject": "team-admin-1",
        "name": "Tammy",
        "admin": False,
        "admin_teams": [{"id": team_id, "name": "字幕组"}],
    }


def test_team_admin_is_limited_to_the_groups_mapped_to_their_teams(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    response = log_in_as(client, monkeypatch, team_admin())

    assert response.status_code == 303
    assert client.get("/auth/me").json()["groups"] == ["111", "222"]


def test_team_admin_cannot_touch_groups_outside_their_scope(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    log_in_as(client, monkeypatch, team_admin())

    outside = {"group_id": "999"}
    assert client.post("/settings/remind_now", json=outside).status_code == 403
    assert (
        client.post(
            "/settings/update", json={**outside, "enable": True, "time": "10:00"}
        ).status_code
        == 403
    )
    assert client.post("/group/sync_members", json=outside).status_code == 403
    assert client.get("/health").status_code == 403


def test_team_admin_cannot_sync_or_delete_members_even_in_their_own_groups(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    log_in_as(client, monkeypatch, team_admin())

    in_scope = {"group_id": "111"}
    assert client.post("/group/sync_members", json=in_scope).status_code == 403
    assert client.delete("/member/1").status_code == 403


def test_full_access_admin_is_not_blocked_by_member_restrictions(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    log_in_as(
        client, monkeypatch, {"subject": "admin-1", "name": "Admin", "admin": True}
    )

    # 越过权限检查后才会触达数据库；这里只要不是 403 即说明未被团队限制拦截
    assert client.post("/group/sync_members", json={"group_id": "x"}).status_code != 403


def test_team_admin_of_an_unmapped_team_is_refused_with_the_team_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    response = log_in_as(client, monkeypatch, team_admin("unmapped-team"))

    assert response.status_code == 403
    assert "unmapped-team" in response.text
    assert "TRANS_MOEFLOW_TEAM_GROUPS" in response.text
    assert client.get("/auth/me").status_code == 401


def test_allow_listed_user_who_administers_a_team_keeps_full_access(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    identity = {**team_admin(), "subject": "allowed-user"}
    log_in_as(client, monkeypatch, identity)

    assert client.get("/auth/me").json()["groups"] is None


def test_older_moeflow_without_team_information_still_admits_admins(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    identity = {"subject": "admin-1", "name": "Admin", "admin": True}
    response = log_in_as(client, monkeypatch, identity)

    assert response.status_code == 303
    assert client.get("/auth/me").json()["groups"] is None


def test_malformed_team_information_is_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    identity = {**team_admin(), "admin_teams": [{"id": 1}]}
    response = log_in_as(client, monkeypatch, identity)

    assert response.status_code == 502
    assert client.get("/auth/me").status_code == 401


WEBHOOK = "/episode/member/sync"


def test_webhook_requires_the_service_token(client: TestClient):
    assert client.post(WEBHOOK, json={}).status_code == 401
    wrong = {"X-Auth-Token": "wrong"}
    assert client.post(WEBHOOK, json={}, headers=wrong).status_code == 401


def test_webhook_accepts_the_service_token_without_a_browser_session(
    client: TestClient,
):
    right = {"X-Auth-Token": "webhook-secret"}

    # 鉴权通过后，空请求体会因参数校验返回 422，而不是 401
    assert client.post(WEBHOOK, json={}, headers=right).status_code == 422


def test_browser_session_cannot_call_webhooks(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    log_in_as(
        client, monkeypatch, {"subject": "admin-1", "name": "Admin", "admin": True}
    )

    assert client.post(WEBHOOK, json={}).status_code == 401


def test_service_token_cannot_call_browser_apis(client: TestClient):
    right = {"X-Auth-Token": "webhook-secret"}

    assert client.get("/projects", headers=right).status_code == 401


def test_webhooks_are_closed_until_a_token_is_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    from nonebot_plugin_trans_progress import web

    monkeypatch.setattr(web.plugin_config, "trans_webhook_token", None)

    response = client.post(WEBHOOK, json={}, headers={"X-Auth-Token": ""})

    assert response.status_code == 503
