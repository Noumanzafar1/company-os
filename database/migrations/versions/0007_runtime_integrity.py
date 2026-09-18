"""Runtime integrity and bounded quota linkage; preserves revision 0006."""

from alembic import op

revision = "0007_runtime_integrity"
down_revision = "0006_durable_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE app.external_effects ADD quota_bucket_id uuid;
    ALTER TABLE app.external_effects ADD FOREIGN KEY(workspace_id,quota_bucket_id) REFERENCES app.quota_buckets(workspace_id,id);
    CREATE INDEX external_effect_quota_fk ON app.external_effects(workspace_id,quota_bucket_id);
    CREATE FUNCTION app.runtime_event_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE valid boolean;
    BEGIN
      CASE NEW.aggregate_type
      WHEN 'runtime_input' THEN SELECT EXISTS(SELECT 1 FROM app.runtime_inputs WHERE workspace_id=NEW.workspace_id AND id=NEW.aggregate_id) INTO valid;
      WHEN 'job' THEN SELECT EXISTS(SELECT 1 FROM app.jobs WHERE workspace_id=NEW.workspace_id AND id=NEW.aggregate_id) INTO valid;
      WHEN 'effect' THEN SELECT EXISTS(SELECT 1 FROM app.external_effects WHERE workspace_id=NEW.workspace_id AND id=NEW.aggregate_id) INTO valid;
      WHEN 'budget' THEN SELECT EXISTS(SELECT 1 FROM app.budgets WHERE workspace_id=NEW.workspace_id AND id=NEW.aggregate_id) INTO valid;
      WHEN 'incident' THEN SELECT EXISTS(SELECT 1 FROM app.incidents WHERE workspace_id=NEW.workspace_id AND id=NEW.aggregate_id) INTO valid;
      ELSE valid=false;
      END CASE;
      IF NOT valid OR NEW.schema_version<>1 OR NEW.payload<>jsonb_build_object('id',NEW.aggregate_id::text)
      OR NOT ((NEW.aggregate_type='runtime_input' AND NEW.event_type IN ('test.aggregate_changed','test.effect_requested'))
      OR (NEW.aggregate_type='job' AND NEW.event_type IN ('job.started','job.succeeded','job.retry_scheduled','job.waiting','job.failed','job.cancelled'))
      OR (NEW.aggregate_type='effect' AND NEW.event_type IN ('effect.uncertain','effect.reconciled'))
      OR (NEW.aggregate_type='budget' AND NEW.event_type IN ('budget.warning','budget.exhausted'))
      OR (NEW.aggregate_type='incident' AND NEW.event_type IN ('security.incident_opened','security.incident_resolved')))
      THEN RAISE EXCEPTION 'Invalid event registry or aggregate' USING ERRCODE='23514'; END IF;
      IF NEW.actor_id<>NEW.created_by THEN RAISE EXCEPTION 'Event actor mismatch' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER runtime_event_validate BEFORE INSERT ON app.events FOR EACH ROW EXECUTE FUNCTION app.runtime_event_guard();
    REVOKE ALL ON FUNCTION app.runtime_event_guard() FROM PUBLIC;
    """)

    op.execute("""
    CREATE TABLE app.company_runtime_caps(id uuid PRIMARY KEY,period_start timestamptz NOT NULL,period_end timestamptz NOT NULL,category text NOT NULL CHECK(category='synthetic'),limit_usd numeric(20,8) NOT NULL CHECK(limit_usd>=0),CHECK(period_end>period_start));
    ALTER TABLE app.company_runtime_caps ENABLE ROW LEVEL SECURITY;
    ALTER TABLE app.company_runtime_caps FORCE ROW LEVEL SECURITY;
    GRANT SELECT ON app.company_runtime_caps,app.budget_reservations,app.usage_entries TO company_auth;
    CREATE POLICY company_cap_internal ON app.company_runtime_caps TO company_auth USING(true);
    CREATE POLICY company_cost_internal ON app.budget_reservations TO company_auth USING(true);
    CREATE POLICY company_usage_internal ON app.usage_entries TO company_auth USING(true);
    CREATE FUNCTION app.runtime_company_cap_ok() RETURNS boolean LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
      SELECT app.has_active_membership(app.current_principal_id(),app.current_workspace_id())
      AND (SELECT count(*) FROM app.company_runtime_caps WHERE period_start<=now() AND period_end>now())>=2
      AND NOT EXISTS(SELECT 1 FROM app.company_runtime_caps c WHERE c.period_start<=now() AND c.period_end>now()
        AND c.limit_usd < (SELECT COALESCE(sum(maximum_usd),0) FROM app.budget_reservations WHERE state IN ('reserved','uncertain'))
        +(SELECT COALESCE(sum(cost_usd),0) FROM app.usage_entries WHERE cost_status='confirmed' AND created_at>=c.period_start AND created_at<c.period_end))
    $$;
    ALTER FUNCTION app.runtime_company_cap_ok() OWNER TO company_auth;
    REVOKE ALL ON FUNCTION app.runtime_company_cap_ok() FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION app.runtime_company_cap_ok() TO company_api,company_worker;
    """)


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION app.runtime_company_cap_ok(); DROP POLICY company_cost_internal ON app.budget_reservations; DROP POLICY company_usage_internal ON app.usage_entries; DROP TABLE app.company_runtime_caps"
    )
    op.execute(
        "DROP TRIGGER runtime_event_validate ON app.events; DROP FUNCTION app.runtime_event_guard()"
    )
    op.execute("ALTER TABLE app.external_effects DROP COLUMN quota_bucket_id")
