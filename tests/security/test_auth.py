from datetime import UTC, datetime, timedelta

import pytest
from company_os.application.identity import digest
from company_os.policy.access import require_recent_mfa
from sqlalchemy import text

from database.seeds.synthetic import key
from tests.conftest import identity_token


def test_unauthenticated_and_session_bootstrap_boundary(client, settings):
    assert client.get("/v1/me").status_code == 401
    assert (
        client.post(
            "/v1/auth/session",
            json={"csrf_token": "a" * 64},
            headers={"Authorization": "Bearer " + identity_token(settings)},
        ).status_code
        == 403
    )


def test_authenticated_permission_denial_is_403_not_401(client, login, monkeypatch):
    headers = login()
    path = f"/v1/workspaces/{key('workspace-a')}/health"
    assert client.get(path, headers=headers).status_code == 200
    identity_service = client.app.state.identity
    original_profile = identity_service.profile

    def without_system_permission(identity):
        profile = original_profile(identity)
        for workspace in profile["workspaces"]:
            workspace["permissions"] = [p for p in workspace["permissions"] if p != "system.read"]
        return profile

    monkeypatch.setattr(identity_service, "profile", without_system_permission)
    response = client.get(path, headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert response.json()["error"]["message"] == "Request denied."
    assert client.get("/v1/me", headers=headers).status_code == 200
    for invalid_headers in [{}, {"Authorization": "Bearer invalid"}]:
        response = client.get(path, headers=invalid_headers)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert (
        client.get(f"/v1/workspaces/{key('workspace-b')}/health", headers=headers).status_code
        == 404
    )


def test_authenticated_mfa_denial_uses_authorization_handler(client, login, monkeypatch):
    headers = login()
    identity_service = client.app.state.identity
    original_profile = identity_service.profile

    def assurance_guarded_profile(identity):
        profile = original_profile(identity)
        require_recent_mfa(identity)
        return profile

    # Test-only guard invocation after real session authentication; no new API operation.
    monkeypatch.setattr(identity_service, "profile", assurance_guarded_profile)
    response = client.get("/v1/me", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert response.json()["error"]["message"] == "Request denied."
    assert client.get("/v1/me").status_code == 401


@pytest.mark.parametrize(
    "claims",
    [
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
        {"iss": "evil"},
        {"aud": "evil"},
        {"sub": "uninvited"},
        {"exp": datetime.now(UTC) + timedelta(hours=2)},
    ],
)
def test_invalid_or_expired_identity(client, settings, claims):
    response = client.post(
        "/v1/auth/session",
        json={"csrf_token": "a" * 64},
        headers={
            "Authorization": "Bearer " + identity_token(settings, **claims),
            "X-Console-Secret": settings.console_secret.get_secret_value(),
        },
    )
    assert response.status_code == 401


def test_a_b_access_and_admin_is_not_approver(client, login):
    for letter, other in [("a", "b"), ("b", "a")]:
        headers = login(letter)
        profile = client.get("/v1/me", headers=headers)
        assert profile.status_code == 200
        workspaces = profile.json()["data"]["workspaces"]
        assert len(workspaces) == 1
        assert workspaces[0]["id"] == str(key(f"workspace-{letter}"))
        assert (
            client.get(f"/v1/workspaces/{key(f'workspace-{letter}')}", headers=headers).status_code
            == 200
        )
        wrong = client.get(f"/v1/workspaces/{key(f'workspace-{other}')}", headers=headers)
        assert wrong.status_code == 404 and "Workspace" not in wrong.text
        if letter == "b":
            assert "approval.grant" not in workspaces[0]["permissions"]
        assert (
            client.post(
                f"/v1/workspaces/{key(f'workspace-{letter}')}/approvals", headers=headers
            ).status_code
            == 405
        )
        # Phase 5 exposes a read collection; POST is still not a state setter.
        approvals = client.get(
            f"/v1/workspaces/{key(f'workspace-{letter}')}/approvals", headers=headers
        )
        assert approvals.status_code == (200 if letter == "a" else 403)


@pytest.mark.parametrize("field,value", [("status", "revoked"), ("expires_at", "2000-01-01")])
def test_membership_revocation_next_request(client, login, admin, field, value):
    headers = login()
    with admin.begin() as conn:
        conn.execute(
            text(
                f"UPDATE app.memberships SET {field}=:value,record_version=record_version+1 WHERE id=:id"
            ),
            {"value": value, "id": key("membership-a")},
        )
    try:
        assert (
            client.get(f"/v1/workspaces/{key('workspace-a')}", headers=headers).status_code == 404
        )
        assert client.get("/v1/me", headers=headers).json()["data"]["workspaces"] == []
    finally:
        with admin.begin() as conn:
            conn.execute(
                text(
                    "UPDATE app.memberships SET status='active',expires_at=NULL,record_version=record_version+1 WHERE id=:id"
                ),
                {"id": key("membership-a")},
            )


def test_disabled_identity_denied_on_existing_session(client, login, admin):
    headers = login()
    with admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE app.principals SET status='disabled',record_version=record_version+1 WHERE id=:id"
            ),
            {"id": key("user-a")},
        )
    try:
        assert client.get("/v1/me", headers=headers).status_code == 401
    finally:
        with admin.begin() as conn:
            conn.execute(
                text(
                    "UPDATE app.principals SET status='active',record_version=record_version+1 WHERE id=:id"
                ),
                {"id": key("user-a")},
            )


@pytest.mark.parametrize(
    "change",
    [
        "revoked_at=now()",
        "last_seen_at=now()-interval '31 minutes'",
        "created_at=now()-interval '13 hours',expires_at=now()-interval '1 hour'",
    ],
)
def test_revoked_idle_and_absolute_expired_sessions(client, login, admin, change):
    headers = login()
    with admin.begin() as conn:
        conn.execute(
            text(f"UPDATE app.auth_sessions SET {change} WHERE token_hash=:hash"),
            {"hash": digest(headers["Authorization"][7:])},
        )
    assert client.get("/v1/me", headers=headers).status_code == 401


def test_logout_requires_csrf_revokes_and_audits(client, login, admin):
    headers = login()
    for override in [
        {"Origin": "https://evil.example"},
        {"X-CSRF-Token": "b" * 64},
        {"Origin": ""},
    ]:
        assert client.post("/v1/auth/logout", headers={**headers, **override}).status_code == 403
        assert client.get("/v1/me", headers=headers).status_code == 200
    assert client.post("/v1/auth/logout", headers=headers).status_code == 204
    assert client.post("/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/v1/me", headers=headers).status_code == 401
    with admin.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM app.audit_entries WHERE action_type='auth.logout'")
            ).scalar_one()
            >= 1
        )


def test_closed_body_and_safe_health_errors(client, login, settings):
    response = client.post(
        "/v1/auth/session",
        headers={"X-Console-Secret": settings.console_secret.get_secret_value()},
        json={
            "csrf_token": "a" * 64,
            "workspace_id": str(key("workspace-b")),
            "secret": "canary-private-content",
        },
    )
    assert response.status_code == 422
    assert "canary" not in response.text
    for path in ["/health/live", "/health/ready"]:
        response = client.get(path)
        assert response.json() == {"status": "ok"}
        assert "no-store" in response.headers["cache-control"]
    health = client.get(f"/v1/workspaces/{key('workspace-a')}/health", headers=login()).json()
    assert health["data"]["live_sending"] is False
    assert sum(c["status"] == "not_configured" for c in health["data"]["components"]) == 7
