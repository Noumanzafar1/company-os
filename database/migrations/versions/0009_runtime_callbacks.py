"""Runtime callback receipts and trace metadata; additive Phase 4 refinement."""

from alembic import op

revision = "0009_runtime_callbacks"
down_revision = "0008_runtime_actor_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE app.runtime_completions(id uuid PRIMARY KEY,workspace_id uuid NOT NULL REFERENCES app.workspaces(id),created_at timestamptz NOT NULL DEFAULT now(),schema_version smallint NOT NULL DEFAULT 1,created_by uuid NOT NULL REFERENCES app.principals(id),job_id uuid NOT NULL,fence bigint NOT NULL,result_ref uuid NOT NULL,UNIQUE(workspace_id,id),UNIQUE(workspace_id,job_id,fence),FOREIGN KEY(workspace_id,job_id) REFERENCES app.jobs(workspace_id,id),FOREIGN KEY(workspace_id,result_ref) REFERENCES app.runtime_inputs(workspace_id,id));
    ALTER TABLE app.runtime_completions ENABLE ROW LEVEL SECURITY;
    ALTER TABLE app.runtime_completions FORCE ROW LEVEL SECURITY;
    CREATE POLICY runtime_scope ON app.runtime_completions TO company_api,company_worker USING(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id)) WITH CHECK(workspace_id=app.current_workspace_id() AND created_by=app.current_principal_id() AND app.has_active_membership(app.current_principal_id(),workspace_id));
    GRANT SELECT,INSERT ON app.runtime_completions TO company_api,company_worker;
    CREATE INDEX runtime_completions_created ON app.runtime_completions(workspace_id,created_at,id);
    CREATE INDEX runtime_completions_job_fk ON app.runtime_completions(workspace_id,job_id);
    CREATE INDEX runtime_completions_result_fk ON app.runtime_completions(workspace_id,result_ref);
    CREATE TRIGGER runtime_immutable BEFORE UPDATE OR DELETE ON app.runtime_completions FOR EACH ROW EXECUTE FUNCTION app.core_row_guard('append');
    ALTER TABLE app.audit_entries ADD causation_id uuid,ADD event_id uuid,ADD job_id uuid,ADD effect_id uuid,ADD attempt_id uuid,ADD provider_request_id varchar(100);
    ALTER TABLE app.audit_entries ADD FOREIGN KEY(workspace_id,event_id) REFERENCES app.events(workspace_id,id),ADD FOREIGN KEY(workspace_id,job_id) REFERENCES app.jobs(workspace_id,id),ADD FOREIGN KEY(workspace_id,effect_id) REFERENCES app.external_effects(workspace_id,id),ADD FOREIGN KEY(workspace_id,attempt_id) REFERENCES app.job_attempts(workspace_id,id);
    CREATE INDEX audit_event_fk ON app.audit_entries(workspace_id,event_id);
    CREATE INDEX audit_job_fk ON app.audit_entries(workspace_id,job_id);
    CREATE INDEX audit_effect_fk ON app.audit_entries(workspace_id,effect_id);
    CREATE INDEX audit_attempt_fk ON app.audit_entries(workspace_id,attempt_id);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE app.runtime_completions")
    op.execute(
        "ALTER TABLE app.audit_entries DROP COLUMN causation_id,DROP COLUMN event_id,DROP COLUMN job_id,DROP COLUMN effect_id,DROP COLUMN attempt_id,DROP COLUMN provider_request_id"
    )
