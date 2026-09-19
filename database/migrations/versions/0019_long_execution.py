"""Add bounded synthetic execution identity, immutable configuration and evidence."""

from alembic import op

revision = "0019_long_execution"
down_revision = "0018_phase5_review_fixes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, fields, mutable in [
        (
            "long_task_specs",
            "input_id uuid NOT NULL, spec jsonb NOT NULL CHECK(jsonb_typeof(spec)='object' AND octet_length(spec::text)<=2048), spec_hash char(64) NOT NULL, UNIQUE(workspace_id,input_id), FOREIGN KEY(workspace_id,input_id) REFERENCES app.runtime_inputs(workspace_id,id)",
            False,
        ),
        (
            "long_executions",
            "job_id uuid NOT NULL, attempt_id uuid NOT NULL, fence bigint NOT NULL CHECK(fence>0), input_hash char(64) NOT NULL, state text NOT NULL CHECK(state IN ('active','finished','abandoned')), outcome varchar(100), details jsonb NOT NULL DEFAULT '{}' CHECK(octet_length(details::text)<=8192), ended_at timestamptz, UNIQUE(workspace_id,attempt_id), FOREIGN KEY(workspace_id,job_id) REFERENCES app.jobs(workspace_id,id), FOREIGN KEY(workspace_id,attempt_id) REFERENCES app.job_attempts(workspace_id,id)",
            True,
        ),
    ]:
        extra = (
            ",updated_at timestamptz NOT NULL DEFAULT now(),updated_by uuid NOT NULL REFERENCES app.principals(id),record_version bigint NOT NULL DEFAULT 1"
            if mutable
            else ""
        )
        op.execute(f"""CREATE TABLE app.{table}(id uuid PRIMARY KEY,workspace_id uuid NOT NULL REFERENCES app.workspaces(id),created_at timestamptz NOT NULL DEFAULT now(),created_by uuid NOT NULL REFERENCES app.principals(id),schema_version smallint NOT NULL DEFAULT 1{extra},{fields},UNIQUE(workspace_id,id));
        ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE app.{table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY runtime_scope ON app.{table} TO company_api,company_worker USING(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id)) WITH CHECK(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id));
        CREATE TRIGGER runtime_guard BEFORE UPDATE OR DELETE ON app.{table} FOR EACH ROW EXECUTE FUNCTION app.core_row_guard('{"mutable" if mutable else "append"}');
        CREATE TRIGGER runtime_actor BEFORE INSERT OR UPDATE ON app.{table} FOR EACH ROW EXECUTE FUNCTION app.runtime_actor_guard('{"mutable" if mutable else "append"}');
        GRANT SELECT ON app.{table} TO company_api,company_worker;
        CREATE INDEX {table}_chronology ON app.{table}(workspace_id,created_at,id);
        """)
    op.execute("""
    GRANT INSERT ON app.long_task_specs TO company_api;
    GRANT INSERT,UPDATE ON app.long_executions TO company_worker;
    CREATE FUNCTION app.long_execution_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE j app.jobs; a app.job_attempts;
    BEGIN
      SELECT * INTO j FROM app.jobs WHERE workspace_id=NEW.workspace_id AND id=NEW.job_id FOR UPDATE;
      SELECT * INTO a FROM app.job_attempts WHERE workspace_id=NEW.workspace_id AND id=NEW.attempt_id;
      IF TG_OP='INSERT' THEN
        IF j.id IS NULL OR a.job_id IS DISTINCT FROM j.id OR a.phase<>'start' OR a.fence<>NEW.fence OR j.fence<>NEW.fence OR j.state NOT IN ('leased','running') OR j.lease_expires_at<=clock_timestamp() OR NEW.state<>'active' OR NEW.ended_at IS NOT NULL THEN RAISE EXCEPTION 'Invalid long execution' USING ERRCODE='23514'; END IF;
      ELSE
        IF (NEW.job_id,NEW.attempt_id,NEW.fence,NEW.input_hash) IS DISTINCT FROM (OLD.job_id,OLD.attempt_id,OLD.fence,OLD.input_hash) OR OLD.state<>'active' OR NEW.state NOT IN ('finished','abandoned') OR NEW.ended_at IS NULL THEN RAISE EXCEPTION 'Immutable execution identity/history' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER execution_identity BEFORE INSERT OR UPDATE ON app.long_executions FOR EACH ROW EXECUTE FUNCTION app.long_execution_guard();
    CREATE FUNCTION app.long_spec_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE input app.runtime_inputs;
    BEGIN
      SELECT * INTO input FROM app.runtime_inputs WHERE workspace_id=NEW.workspace_id AND id=NEW.input_id FOR UPDATE;
      IF input.id IS NULL OR EXISTS(SELECT 1 FROM app.jobs WHERE workspace_id=NEW.workspace_id AND input_ref=input.id AND attempt_count>0) THEN RAISE EXCEPTION 'Execution already admitted' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER spec_identity BEFORE INSERT ON app.long_task_specs FOR EACH ROW EXECUTE FUNCTION app.long_spec_guard();
    REVOKE ALL ON FUNCTION app.long_execution_guard(),app.long_spec_guard() FROM PUBLIC;
    """)


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM app.long_executions) THEN RAISE EXCEPTION 'Preserve execution history: use matched backup rollback'; END IF; END $$;
    DROP TABLE app.long_executions;
    DROP TABLE app.long_task_specs;
    DROP FUNCTION app.long_execution_guard(),app.long_spec_guard();""")
