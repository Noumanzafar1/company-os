"""Register canonical runtime payload v2; retain immutable synthetic v1 history."""

from alembic import op

revision = "0011_runtime_event_payloads"
down_revision = "0010_runtime_budget_caps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER FUNCTION app.runtime_event_guard() RENAME TO runtime_event_guard_v1;
    DROP TRIGGER runtime_event_validate ON app.events;
    CREATE FUNCTION app.runtime_event_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE valid boolean; expected jsonb;
    BEGIN
      CASE NEW.aggregate_type
      WHEN 'runtime_input' THEN
        SELECT EXISTS(SELECT 1 FROM app.runtime_inputs WHERE workspace_id=NEW.workspace_id AND id=NEW.aggregate_id) INTO valid;
        expected=jsonb_build_object('input_id',NEW.aggregate_id::text);
      WHEN 'job' THEN
        SELECT jsonb_build_object('job_id',id::text,'attempt_no',attempt_count,'error_code',last_error_code,'next_attempt_at',CASE WHEN state='retry_wait' THEN to_char(available_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"') ELSE NULL END) INTO expected FROM app.jobs WHERE workspace_id=NEW.workspace_id AND id=NEW.aggregate_id;
        valid=expected IS NOT NULL;
      WHEN 'effect' THEN
        SELECT jsonb_build_object('effect_id',id::text,'provider_request_id',provider_request_id,'resolution',state) INTO expected FROM app.external_effects WHERE workspace_id=NEW.workspace_id AND id=NEW.aggregate_id;
        valid=expected IS NOT NULL;
      WHEN 'budget' THEN
        SELECT jsonb_build_object('budget_id',id::text,'spent',spent_usd::text,'reserved',reserved_usd::text,'limit',limit_usd::text,'currency','USD') INTO expected FROM app.budgets WHERE workspace_id=NEW.workspace_id AND id=NEW.aggregate_id;
        valid=expected IS NOT NULL;
      WHEN 'incident' THEN
        SELECT jsonb_build_object('incident_id',id::text,'severity',severity,'affected_scopes',jsonb_build_array(workspace_id::text)) INTO expected FROM app.incidents WHERE workspace_id=NEW.workspace_id AND id=NEW.aggregate_id;
        valid=expected IS NOT NULL;
      ELSE valid=false;
      END CASE;
      IF NOT valid OR NEW.schema_version NOT IN (1,2)
      OR (NEW.schema_version=1 AND NEW.payload<>jsonb_build_object('id',NEW.aggregate_id::text))
      OR (NEW.schema_version=2 AND NEW.payload<>expected)
      OR NOT ((NEW.aggregate_type='runtime_input' AND NEW.event_type IN ('test.aggregate_changed','test.effect_requested'))
      OR (NEW.aggregate_type='job' AND NEW.event_type IN ('job.started','job.succeeded','job.retry_scheduled','job.waiting','job.failed','job.cancelled'))
      OR (NEW.aggregate_type='effect' AND NEW.event_type IN ('effect.uncertain','effect.reconciled'))
      OR (NEW.aggregate_type='budget' AND NEW.event_type IN ('budget.warning','budget.exhausted'))
      OR (NEW.aggregate_type='incident' AND NEW.event_type IN ('security.incident_opened','security.incident_resolved')))
      THEN RAISE EXCEPTION 'Invalid event registry or aggregate' USING ERRCODE='23514'; END IF;
      IF NEW.actor_id<>NEW.created_by THEN RAISE EXCEPTION 'Event actor mismatch' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    REVOKE ALL ON FUNCTION app.runtime_event_guard() FROM PUBLIC;
    CREATE TRIGGER runtime_event_validate BEFORE INSERT ON app.events FOR EACH ROW EXECUTE FUNCTION app.runtime_event_guard();
    """)


def downgrade() -> None:
    op.execute("""
    DROP TRIGGER runtime_event_validate ON app.events;
    DROP FUNCTION app.runtime_event_guard();
    ALTER FUNCTION app.runtime_event_guard_v1() RENAME TO runtime_event_guard;
    CREATE TRIGGER runtime_event_validate BEFORE INSERT ON app.events FOR EACH ROW EXECUTE FUNCTION app.runtime_event_guard();
    """)
