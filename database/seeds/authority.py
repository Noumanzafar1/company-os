"""Idempotent offline policy fixtures. Never provision real authority."""

import json
from datetime import UTC, datetime, timedelta

from company_os.application.runtime import digest
from company_os.policy.engine import REGISTRY
from company_os.policy_contracts import PolicyRules
from sqlalchemy import Engine, text

from database.seeds.synthetic import key


def seed_authority(engine: Engine) -> None:
    with engine.begin() as conn:
        for letter in ("a", "b"):
            w, actor = key("workspace-" + letter), key("user-" + letter)
            for action in REGISTRY:
                pid, vid = key(letter + "-policy-" + action), key(letter + "-policy-v1-" + action)
                rules = PolicyRules(
                    action=action,
                    maximum_uses=100,
                    maximum_targets=200,
                    maximum_volume=20000,
                    maximum_spend="100",
                    maximum_expiry_seconds=86400,
                    permitted_roles=["founder"],
                ).model_dump(mode="json")
                conn.execute(
                    text(
                        "INSERT INTO app.policies(id,workspace_id,created_by,updated_by,action) VALUES(:id,:w,:p,:p,:a) ON CONFLICT DO NOTHING"
                    ),
                    {"id": pid, "w": w, "p": actor, "a": action},
                )
                conn.execute(
                    text(
                        "INSERT INTO app.policy_versions(id,workspace_id,created_by,policy_id,version,rules,content_hash,effective_at,expires_at,rationale) VALUES(:id,:w,:p,:pid,1,CAST(:rules AS jsonb),:hash,:start,:end,'Synthetic fixture, no provider authority') ON CONFLICT DO NOTHING"
                    ),
                    {
                        "id": vid,
                        "w": w,
                        "p": actor,
                        "pid": pid,
                        "rules": json.dumps(rules),
                        "hash": digest(rules),
                        "start": datetime.now(UTC) - timedelta(days=1),
                        "end": datetime.now(UTC) + timedelta(days=365),
                    },
                )
                conn.execute(
                    text(
                        "UPDATE app.policies SET active_version_id=:v,record_version=record_version+1 WHERE id=:id AND active_version_id IS NULL"
                    ),
                    {"v": vid, "id": pid},
                )
            for index in range(1, 5):
                conn.execute(
                    text(
                        "INSERT INTO app.authority_test_targets(id,workspace_id,created_by,updated_by,label) VALUES(:id,:w,:p,:p,:label) ON CONFLICT DO NOTHING"
                    ),
                    {
                        "id": key(f"{letter}-authority-target-{index}"),
                        "w": w,
                        "p": actor,
                        "label": f"Synthetic {letter.upper()} target {index}",
                    },
                )
