"""Permit scoped validation locks without granting workers approval mutation."""

from alembic import op

revision = "0014_authority_validation_role"
down_revision = "0013_policy_authority"
branch_labels = None
depends_on = None

READ = (
    "approval_requests",
    "authority_test_targets",
    "approval_manifests",
    "policy_versions",
    "policies",
    "authority_freezes",
    "approval_targets",
)


def upgrade() -> None:
    for table in READ:
        op.execute(f"GRANT SELECT ON app.{table} TO company_auth")
        op.execute(
            f"CREATE POLICY authority_validator ON app.{table} TO company_auth USING(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id))"
        )
    op.execute("""
    GRANT UPDATE ON app.approval_requests,app.authority_test_targets TO company_auth;
    ALTER FUNCTION app.authority_validate(uuid) SECURITY DEFINER;
    ALTER FUNCTION app.authority_validate(uuid) OWNER TO company_auth;
    """)


def downgrade() -> None:
    op.execute("""
    ALTER FUNCTION app.authority_validate(uuid) OWNER TO CURRENT_USER;
    ALTER FUNCTION app.authority_validate(uuid) SECURITY INVOKER;
    REVOKE UPDATE ON app.approval_requests,app.authority_test_targets FROM company_auth;
    """)
    for table in READ:
        op.execute(
            f"DROP POLICY authority_validator ON app.{table}; REVOKE SELECT ON app.{table} FROM company_auth"
        )
