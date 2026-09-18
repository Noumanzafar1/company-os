import os
from uuid import UUID, uuid5

from company_os.contracts import RegionPolicy, RetentionPolicy
from sqlalchemy import create_engine, text

NAMESPACE = UUID("dec8c45a-1e5b-4c61-8a0f-71e9d0d55991")


def key(name: str) -> UUID:
    return uuid5(NAMESPACE, name)


def seed(*, include_business: bool = True) -> None:
    if os.environ.get("COMPANY_ENV") not in {"development", "test"}:
        raise RuntimeError("Synthetic fixtures are local/test only")
    engine = create_engine(os.environ["MIGRATION_DATABASE_URL"], hide_parameters=True)
    founder = key("user-a")
    with engine.begin() as conn:
        for tag, kind in [("user-a", "user"), ("user-b", "user"), ("worker", "service")]:
            params = {"id": key(tag), "kind": kind, "actor": founder}
            conn.execute(
                text(
                    "INSERT INTO app.principals(id,kind,status,created_by,updated_by) VALUES(:id,:kind,'active',:actor,:actor) ON CONFLICT DO NOTHING"
                ),
                params,
            )
            if kind == "user":
                conn.execute(
                    text(
                        "INSERT INTO app.users(id,principal_id,auth_subject,display_name,created_by,updated_by) VALUES(:id,:id,:subject,:name,:actor,:actor) ON CONFLICT DO NOTHING"
                    ),
                    {
                        **params,
                        "subject": f"synthetic-{tag}",
                        "name": f"Synthetic User {tag[-1].upper()}",
                    },
                )
            else:
                conn.execute(
                    text(
                        "INSERT INTO app.service_identities(id,principal_id,name,token_key_ref,expires_at,capability_profile,created_by,updated_by) VALUES(:id,:id,'foundation-worker','env:WORKER_DATABASE_URL',now()+interval '1 year','heartbeat-only',:actor,:actor) ON CONFLICT DO NOTHING"
                    ),
                    params,
                )
        for role, permissions in {
            "founder": [
                "workspace.read",
                "system.read",
                "approval.grant",
                "business.read",
                "business.write",
                "identity.review",
            ],
            "system_administrator": ["workspace.read", "system.read"],
        }.items():
            conn.execute(
                text(
                    "INSERT INTO app.roles(id,name,created_by,updated_by) VALUES(:id,:name,:actor,:actor) ON CONFLICT DO NOTHING"
                ),
                {"id": key(role), "name": role, "actor": founder},
            )
            for permission in permissions:
                if not include_business and permission in {
                    "business.read",
                    "business.write",
                    "identity.review",
                }:
                    continue
                conn.execute(
                    text(
                        "INSERT INTO app.role_permissions(id,role_id,permission,created_by,updated_by) VALUES(:id,:role,:permission,:actor,:actor) ON CONFLICT DO NOTHING"
                    ),
                    {
                        "id": key(role + permission),
                        "role": key(role),
                        "permission": permission,
                        "actor": founder,
                    },
                )
        for letter, role, kind in [
            ("a", "founder", "acquisition"),
            ("b", "system_administrator", "client_delivery"),
        ]:
            params = {
                "id": key(f"workspace-{letter}"),
                "name": f"Workspace {letter.upper()}",
                "kind": kind,
                "actor": founder,
                "retention": RetentionPolicy(profiles={"R7": 365}).model_dump_json(),
                "region": RegionPolicy().model_dump_json(),
            }
            conn.execute(
                text(
                    "INSERT INTO app.workspaces(id,name,kind,status,timezone,retention_profile,region_policy,created_by,updated_by) VALUES(:id,:name,:kind,'active','Asia/Karachi',CAST(:retention AS jsonb),CAST(:region AS jsonb),:actor,:actor) ON CONFLICT DO NOTHING"
                ),
                params,
            )
            conn.execute(
                text(
                    "INSERT INTO app.memberships(id,workspace_id,principal_id,role_id,status,created_by,updated_by) VALUES(:id,:workspace,:principal,:role,'active',:actor,:actor) ON CONFLICT DO NOTHING"
                ),
                {
                    "id": key(f"membership-{letter}"),
                    "workspace": params["id"],
                    "principal": key(f"user-{letter}"),
                    "role": key(role),
                    "actor": founder,
                },
            )
    from database.seeds.core_business import seed_business

    if include_business:
        seed_business(engine)
        from database.seeds.runtime import seed_runtime

        seed_runtime(engine)
        from database.seeds.authority import seed_authority

        seed_authority(engine)
    engine.dispose()
    print("Synthetic A/B identities ready; existing grants/revocations preserved")


if __name__ == "__main__":
    seed()
