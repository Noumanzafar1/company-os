"""FAKE PHASE 4 TEST AUTHENTICATION — NOT A PROVIDER GUARANTEE."""

import base64
import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy import Connection

from company_os.persistence.business import BusinessError
from company_os.persistence.database import rows
from company_os.persistence.runtime import get, insert, update
from company_os.runtime_contracts import FakeCallback


def authenticate(secret: str, body: bytes, timestamp: str, signature: str, now: datetime) -> None:
    if len(secret) < 32 or len(body) > 16384:
        raise BusinessError("INVALID_CALLBACK", 400)
    try:
        stamp = int(timestamp)
    except ValueError as exc:
        raise BusinessError("AUTH_FAILED", 401) from exc
    if abs(now.timestamp() - stamp) > 300:
        raise BusinessError("STALE_DELIVERY", 401)
    expected = hmac.new(
        secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise BusinessError("AUTH_FAILED", 401)


def receive(conn: Connection, endpoint_id: UUID, body: bytes, secret: str) -> dict[str, Any]:
    payload = FakeCallback.model_validate_json(body)
    if payload.occurred_at.tzinfo is None:
        raise BusinessError("INVALID_TIMESTAMP", 422)
    endpoint = get(conn, "fake_endpoints", endpoint_id, lock=True)
    if not endpoint["enabled"]:
        raise BusinessError("ENDPOINT_DISABLED", 403)
    body_hash = hashlib.sha256(body).hexdigest()
    previous = rows(
        conn,
        "SELECT * FROM app.webhook_inbox WHERE connection_id=:id AND provider_event_key=:key",
        {"id": endpoint_id, "key": payload.event_key},
    )
    if previous:
        if previous[0]["payload_sha256"] != body_hash:
            raise BusinessError("CALLBACK_KEY_CONFLICT")
        return previous[0]
    cipher = Fernet(base64.urlsafe_b64encode(hashlib.sha256(("raw:" + secret).encode()).digest()))
    item = insert(
        conn,
        "webhook_inbox",
        {
            "connection_id": endpoint_id,
            "provider_event_key": payload.event_key,
            "payload_encrypted": cipher.encrypt(body).decode(),
            "payload_sha256": body_hash,
            "authenticated": True,
            "provider_occurred_at": payload.occurred_at.astimezone(UTC),
            "state": "received",
            "external_id": payload.external_id,
            "observation_version": payload.version,
            "observation": payload.observation,
        },
    )
    if payload.schema_version != 1:
        return update(conn, "webhook_inbox", item, state="quarantined", error_code="UNKNOWN_SCHEMA")
    mapped = rows(
        conn, "SELECT * FROM app.runtime_inputs WHERE id=:id", {"id": payload.external_id}
    )
    if not mapped:
        return update(
            conn, "webhook_inbox", item, state="quarantined", error_code="UNKNOWN_EXTERNAL_ID"
        )
    previous = rows(
        conn,
        "SELECT * FROM app.fake_observations WHERE connection_id=:c AND input_ref=:id FOR UPDATE",
        {"c": endpoint_id, "id": payload.external_id},
    )
    if previous:
        observation = previous[0]
        if observation["state"] == "stopped" or (
            payload.version <= observation["observation_version"]
            and payload.observation != "stopped"
        ):
            return update(conn, "webhook_inbox", item, state="ignored")
        update(
            conn,
            "fake_observations",
            observation,
            state=payload.observation,
            observation_version=max(payload.version, observation["observation_version"]),
        )
    else:
        insert(
            conn,
            "fake_observations",
            {
                "connection_id": endpoint_id,
                "input_ref": payload.external_id,
                "observation_version": payload.version,
                "state": payload.observation,
            },
        )
    # Only synthetic waiting jobs resume; callbacks confer no business authority.
    for job in rows(
        conn,
        "SELECT * FROM app.jobs WHERE input_ref=:id AND state='waiting_external' AND effect_id IS NULL AND last_error_code IS NULL FOR UPDATE",
        {"id": payload.external_id},
    ):
        update(conn, "jobs", job, state="queued", waiting_on_resource_id=None)
    return update(conn, "webhook_inbox", item, state="applied")
