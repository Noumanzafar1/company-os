"""Multiple budget caps per logical reservation without double-counting usage."""

from alembic import op

revision = "0010_runtime_budget_caps"
down_revision = "0009_runtime_callbacks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE app.reservation_budget_caps(id uuid PRIMARY KEY,workspace_id uuid NOT NULL REFERENCES app.workspaces(id),created_at timestamptz NOT NULL DEFAULT now(),schema_version smallint NOT NULL DEFAULT 1,created_by uuid NOT NULL REFERENCES app.principals(id),reservation_id uuid NOT NULL,budget_id uuid NOT NULL,UNIQUE(workspace_id,id),UNIQUE(workspace_id,reservation_id,budget_id),FOREIGN KEY(workspace_id,reservation_id) REFERENCES app.budget_reservations(workspace_id,id),FOREIGN KEY(workspace_id,budget_id) REFERENCES app.budgets(workspace_id,id));
    ALTER TABLE app.reservation_budget_caps ENABLE ROW LEVEL SECURITY;
    ALTER TABLE app.reservation_budget_caps FORCE ROW LEVEL SECURITY;
    CREATE POLICY runtime_scope ON app.reservation_budget_caps TO company_api,company_worker USING(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id)) WITH CHECK(workspace_id=app.current_workspace_id() AND created_by=app.current_principal_id() AND app.has_active_membership(app.current_principal_id(),workspace_id));
    GRANT SELECT,INSERT ON app.reservation_budget_caps TO company_api,company_worker;
    CREATE INDEX reservation_caps_created ON app.reservation_budget_caps(workspace_id,created_at,id);
    CREATE INDEX reservation_caps_reservation ON app.reservation_budget_caps(workspace_id,reservation_id);
    CREATE INDEX reservation_caps_budget ON app.reservation_budget_caps(workspace_id,budget_id);
    CREATE TRIGGER runtime_immutable BEFORE UPDATE OR DELETE ON app.reservation_budget_caps FOR EACH ROW EXECUTE FUNCTION app.core_row_guard('append');
    """)


def downgrade() -> None:
    op.execute("DROP TABLE app.reservation_budget_caps")
