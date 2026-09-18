"""Add typed approval events without changing accepted runtime event validators."""

from alembic import op

revision = "0015_authority_events"
down_revision = "0014_authority_validation_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    DROP TRIGGER runtime_event_validate ON app.events;
    DROP TRIGGER runtime_event_aggregate_version ON app.events;
    CREATE TRIGGER runtime_event_validate BEFORE INSERT ON app.events FOR EACH ROW WHEN (NEW.aggregate_type<>'approval') EXECUTE FUNCTION app.runtime_event_guard();
    CREATE TRIGGER runtime_event_aggregate_version BEFORE INSERT ON app.events FOR EACH ROW WHEN (NEW.aggregate_type<>'approval') EXECUTE FUNCTION app.runtime_event_version_guard();
    CREATE FUNCTION app.authority_event_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE r app.approval_requests; expected_type text;
    BEGIN
      SELECT * INTO r FROM app.approval_requests WHERE id=NEW.aggregate_id AND workspace_id=NEW.workspace_id FOR SHARE;
      expected_type=CASE r.state WHEN 'pending' THEN 'approval.requested' WHEN 'approved' THEN 'approval.granted' WHEN 'rejected' THEN 'approval.rejected' WHEN 'revoked' THEN 'approval.revoked' WHEN 'superseded' THEN 'approval.invalidated' WHEN 'expired' THEN 'approval.expired' END;
      IF r.id IS NULL OR NEW.schema_version<>2 OR NEW.aggregate_version<>r.record_version OR NEW.actor_id<>NEW.created_by
        OR NEW.event_type IS DISTINCT FROM expected_type OR NEW.payload<>jsonb_build_object('approval_id',r.id::text,'payload_hash',r.payload_hash,'scope_hash',r.scope_hash,'state',r.state) THEN
        RAISE EXCEPTION 'Invalid approval event' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER authority_event_validate BEFORE INSERT ON app.events FOR EACH ROW WHEN (NEW.aggregate_type='approval') EXECUTE FUNCTION app.authority_event_guard();
    REVOKE ALL ON FUNCTION app.authority_event_guard() FROM PUBLIC;
    """)


def downgrade() -> None:
    # Retain the already persisted immutable event history. Old code cannot emit
    # new approval events; drain the outbox before a code/schema rollback.
    op.execute("""
    DROP TRIGGER authority_event_validate ON app.events; DROP FUNCTION app.authority_event_guard();
    DROP TRIGGER runtime_event_validate ON app.events; DROP TRIGGER runtime_event_aggregate_version ON app.events;
    CREATE TRIGGER runtime_event_validate BEFORE INSERT ON app.events FOR EACH ROW EXECUTE FUNCTION app.runtime_event_guard();
    CREATE TRIGGER runtime_event_aggregate_version BEFORE INSERT ON app.events FOR EACH ROW EXECUTE FUNCTION app.runtime_event_version_guard();
    """)
