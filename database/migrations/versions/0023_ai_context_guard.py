"""Narrow current-workspace predicate and storage-level AI call bindings."""

from alembic import op

revision = "0023_ai_context_guard"
down_revision = "0022_ai_route_authority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE FUNCTION app.ai_workspace_current(epoch bigint) RETURNS boolean
    LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
      SELECT app.has_active_membership(app.current_principal_id(),app.current_workspace_id()) AND EXISTS(
        SELECT 1 FROM app.workspaces WHERE id=app.current_workspace_id() AND status='active' AND authz_epoch=epoch)
    $$;
    ALTER FUNCTION app.ai_workspace_current(bigint) OWNER TO company_auth;
    REVOKE ALL ON FUNCTION app.ai_workspace_current(bigint) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION app.ai_workspace_current(bigint) TO company_api,company_worker;
    CREATE FUNCTION app.ai_call_binding() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE a app.agent_runs; r app.ai_routes; j app.jobs; b app.budget_reservations;
    BEGIN
      SELECT * INTO a FROM app.agent_runs WHERE id=NEW.agent_run_id FOR UPDATE;
      SELECT * INTO r FROM app.ai_routes WHERE id=a.route_id;
      SELECT * INTO j FROM app.jobs WHERE id=a.job_id FOR UPDATE;
      SELECT * INTO b FROM app.budget_reservations WHERE id=NEW.reservation_id FOR UPDATE;
      IF a.id IS NULL OR r.id IS NULL OR j.id IS NULL OR b.id IS NULL
        OR j.state<>'running' OR j.lease_expires_at<=clock_timestamp() OR j.cancel_requested_at IS NOT NULL
        OR b.job_id IS DISTINCT FROM j.id OR b.state<>'reserved' OR b.amount_usd IS DISTINCT FROM NEW.estimated_usd
        OR NEW.provider NOT IN ('fake_openai','fake_anthropic')
        OR NEW.provider IS DISTINCT FROM r.body->>'primary_provider'
        OR NEW.model_id IS DISTINCT FROM r.body->>'primary_model_id'
        OR NEW.price_id IS DISTINCT FROM r.price_id OR NEW.prompt_id IS DISTINCT FROM r.prompt_id
        OR NEW.status<>'started' OR NEW.confirmed_usd IS NOT NULL OR NEW.ended_at IS NOT NULL
        OR NEW.ordinal>(a.task->>'max_model_calls')::integer
        OR EXISTS(SELECT 1 FROM app.model_runs WHERE agent_run_id=a.id AND status IN ('started','uncertain')) THEN
        RAISE EXCEPTION 'Model call binding/reservation/fence required' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER ai_bound_call BEFORE INSERT ON app.model_runs FOR EACH ROW EXECUTE FUNCTION app.ai_call_binding();
    REVOKE ALL ON FUNCTION app.ai_call_binding() FROM PUBLIC;
    """)


def downgrade() -> None:
    op.execute("""DROP TRIGGER ai_bound_call ON app.model_runs; DROP FUNCTION app.ai_call_binding();
    DROP FUNCTION app.ai_workspace_current(bigint);""")
