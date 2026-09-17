"""User-authorized offline verified-MFA fixture; no network or runtime bypass."""

import json
import secrets
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from company_os.adapters.auth import JWTIdentityProvider
from company_os.application.identity import IdentityService
from company_os.domain.identity import AuthenticationFailed
from company_os.domain.scoring import canonical_hash
from company_os.persistence.business import get, insert
from company_os.persistence.database import rows, transaction
from cryptography.hazmat.primitives.asymmetric import ec

from database.seeds.synthetic import key


@pytest.fixture
def offline_mfa(client, settings, runtime):
    config = settings.model_copy(
        update={"auth_mode": "supabase", "supabase_url": "https://offline-identity.example"}
    )
    provider = JWTIdentityProvider(config)
    private = ec.generate_private_key(ec.SECP256R1())
    provider.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key())
    )
    now = int(datetime.now(UTC).timestamp())
    claims = {
        "sub": "synthetic-user-a",
        "iss": "https://offline-identity.example/auth/v1",
        "aud": "authenticated",
        "iat": now,
        "exp": now + 900,
        "aal": "aal2",
        "amr": [{"method": "totp", "timestamp": now}],
    }
    token = jwt.encode(claims, private, algorithm="ES256")
    assert provider.verify(token).assurance == "aal2"
    with pytest.raises(AuthenticationFailed):
        provider.verify(
            jwt.encode(claims, ec.generate_private_key(ec.SECP256R1()), algorithm="ES256")
        )
    csrf = secrets.token_hex(32)
    # A verified asymmetric identity enters the same persistent session boundary.
    session = IdentityService(runtime, provider).start(token, csrf)
    return {
        "Authorization": "Bearer " + session,
        "Origin": settings.console_origin,
        "X-CSRF-Token": csrf,
    }


def test_reviewed_merge_reversal_preserves_attribution_and_requires_versions(
    client, offline_mfa, runtime
):
    prefix = f"/v1/workspaces/{key('workspace-a')}"
    with transaction(runtime, key("user-a"), key("workspace-a"), 1) as conn:
        before = rows(
            conn,
            "SELECT id,subject_id FROM app.evidence WHERE subject_id IN (:s,:r) ORDER BY id",
            {"s": key("a-account-8"), "r": key("a-account-9")},
        )
    body = {
        "survivor_id": str(key("a-account-8")),
        "retired_id": str(key("a-account-9")),
        "survivor_version": 1,
        "retired_version": 1,
        "reason": "Synthetic reviewer inspected both entity records",
        "evidence_ids": [str(key("a-evidence-8-problem")), str(key("a-evidence-9-problem"))],
    }
    headers = {**offline_mfa, "Idempotency-Key": str(uuid4())}
    result = client.post(prefix + "/identities/merge", json=body, headers=headers)
    assert result.status_code == 200, result.text
    assert (
        client.post(prefix + "/identities/merge", json=body, headers=headers).json()
        == result.json()
    )
    merge_id = result.json()["result_id"]
    with transaction(runtime, key("user-a"), key("workspace-a"), 1) as conn:
        retired = get(conn, "accounts", key("a-account-9"))
        assert retired["status"] == "merged" and retired["merged_into_id"] == key("a-account-8")
        assert get(conn, "contact_points", key("a-contact-9"))["status"] == "conflicted"
        assert rows(
            conn,
            "SELECT id FROM app.suppressions WHERE contact_point_id=:id AND state='review_required'",
            {"id": key("a-contact-9")},
        )
        assert (
            rows(
                conn,
                "SELECT id,subject_id FROM app.evidence WHERE subject_id IN (:s,:r) ORDER BY id",
                {"s": key("a-account-8"), "r": key("a-account-9")},
            )
            == before
        )
    reversal = {
        "survivor_version": 2,
        "retired_version": 2,
        "reason": "Synthetic review corrects the mistaken match",
        "evidence_ids": body["evidence_ids"],
    }
    path = prefix + f"/identities/merges/{merge_id}/reverse"
    assert (
        client.post(
            path, json=reversal, headers={**offline_mfa, "Idempotency-Key": str(uuid4())}
        ).status_code
        == 400
    )
    with transaction(runtime, key("user-a"), key("workspace-a"), 1) as conn:
        original = get(conn, "evidence", key("a-evidence-9-problem"))
        values = {
            k: v
            for k, v in original.items()
            if k not in {"id", "workspace_id", "created_at", "created_by"}
        }

        def observation(**changes):
            data = {**values, **changes, "provider_record_id": str(uuid4())}
            data.pop("content_sha256")
            data["content_sha256"] = canonical_hash(json.loads(json.dumps(data, default=str)))
            return insert(conn, "evidence", data)

        expired = observation(expires_at=datetime.now(UTC) - timedelta(hours=1))
        retracted = observation()
        insert(
            conn,
            "evidence_retractions",
            {"evidence_id": retracted["id"], "reason": "Synthetic withdrawn identity support"},
        )
        uncertain = observation(entity_match="uncertain")
        revoked = observation(source_id=key("a-source-revoked"))
        superseded = observation()
        observation(supersedes_id=superseded["id"])
        decision_count = len(rows(conn, "SELECT id FROM app.decisions"))
        merge_before = get(conn, "identity_merges", merge_id)
    for evidence_id, expected in [
        (key("a-evidence-0-problem"), 422),
        (expired["id"], 422),
        (retracted["id"], 422),
        (uncertain["id"], 422),
        (revoked["id"], 422),
        (superseded["id"], 422),
        (key("b-evidence-0-problem"), 404),
        (uuid4(), 404),
    ]:
        rejected = client.post(
            path,
            json={**reversal, "evidence_ids": [str(evidence_id)]},
            headers={**offline_mfa, "Idempotency-Key": str(uuid4()), "If-Match": "1"},
        )
        assert rejected.status_code == expected, rejected.text
    with transaction(runtime, key("user-a"), key("workspace-a"), 1) as conn:
        assert len(rows(conn, "SELECT id FROM app.decisions")) == decision_count
        assert not rows(
            conn, "SELECT id FROM app.identity_merge_reversals WHERE merge_id=:id", {"id": merge_id}
        )
        assert get(conn, "identity_merges", merge_id) == merge_before
    reversed_result = client.post(
        path,
        json=reversal,
        headers={**offline_mfa, "Idempotency-Key": str(uuid4()), "If-Match": "1"},
    )
    assert reversed_result.status_code == 200, reversed_result.text
    with transaction(runtime, key("user-a"), key("workspace-a"), 1) as conn:
        retired = get(conn, "accounts", key("a-account-9"))
        assert retired["status"] == "identity_hold" and retired["merged_into_id"] is None
        assert get(conn, "contact_points", key("a-contact-9"))["status"] == "conflicted"
        assert (
            len(rows(conn, "SELECT id FROM app.identity_merges WHERE id=:id", {"id": merge_id}))
            == 1
        )
        assert (
            len(
                rows(
                    conn,
                    "SELECT id FROM app.identity_merge_reversals WHERE merge_id=:id",
                    {"id": merge_id},
                )
            )
            == 1
        )


def test_cross_workspace_merge_is_safe_404(client, offline_mfa):
    response = client.post(
        f"/v1/workspaces/{key('workspace-a')}/identities/merge",
        headers={**offline_mfa, "Idempotency-Key": str(uuid4())},
        json={
            "survivor_id": str(key("a-account-0")),
            "retired_id": str(key("b-account-0")),
            "survivor_version": 1,
            "retired_version": 1,
            "reason": "Synthetic cross-boundary attack",
            "evidence_ids": [str(key("a-evidence-0-problem"))],
        },
    )
    assert response.status_code == 404
