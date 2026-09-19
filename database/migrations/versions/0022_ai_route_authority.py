"""Exact fake technical route promotion through Phase 5 decisions/manifests/uses."""

from alembic import op

revision = "0022_ai_route_authority"
down_revision = "0021_ai_gateway"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
    ALTER TABLE app.approval_uses ADD COLUMN activation_route_id uuid,
      ADD CONSTRAINT route_use_fk FOREIGN KEY(workspace_id,activation_route_id) REFERENCES app.ai_routes(workspace_id,id),
      DROP CONSTRAINT authority_use_kind,
      ADD CONSTRAINT authority_use_kind CHECK(
       (effect_id IS NOT NULL AND job_id IS NOT NULL AND activation_policy_id IS NULL AND activation_session_id IS NULL AND activation_route_id IS NULL)
       OR (effect_id IS NULL AND job_id IS NULL AND activation_session_id IS NOT NULL AND spend_reserved=0 AND volume=1
       AND ((activation_policy_id IS NOT NULL AND activation_route_id IS NULL) OR (activation_policy_id IS NULL AND activation_route_id IS NOT NULL))));
    CREATE UNIQUE INDEX one_route_use ON app.approval_uses(workspace_id,manifest_id) WHERE activation_route_id IS NOT NULL;
    DROP TRIGGER bounded_use ON app.approval_uses;
    CREATE TRIGGER bounded_use BEFORE INSERT ON app.approval_uses FOR EACH ROW WHEN (NEW.activation_route_id IS NULL) EXECUTE FUNCTION app.authority_use_guard();
    -- Extend the closed executor registry, preserving the rest of this applied
    -- function byte for byte. Fail migration if its expected signature changes.
    DO $$ DECLARE body text; BEGIN
      body=pg_get_functiondef('app.authority_commit_guard()'::regprocedure);
      IF position("""
        + """'''runtime.synthetic_batch_action'',''policy.activate''' IN body)=0 THEN RAISE EXCEPTION 'Unexpected authority registry'; END IF;
      body=replace(body,'''runtime.synthetic_batch_action'',''policy.activate''','''runtime.synthetic_batch_action'',''policy.activate'',''ai.route.promote''');
      EXECUTE body;
    END $$;
    CREATE FUNCTION app.ai_route_use_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE r app.approval_requests; c app.ai_routes; e app.ai_evaluations; code text;
    BEGIN
      code=app.authority_validate(NEW.manifest_id);
      IF code IS NOT NULL THEN RAISE EXCEPTION '%',code USING ERRCODE='23514'; END IF;
      SELECT a.* INTO r FROM app.approval_requests a JOIN app.approval_manifests m ON m.request_id=a.id WHERE m.id=NEW.manifest_id;
      SELECT * INTO c FROM app.ai_routes WHERE id=NEW.activation_route_id;
      SELECT * INTO e FROM app.ai_evaluations WHERE id=(r.payload->>'evaluation_id')::uuid;
      IF r.action IS DISTINCT FROM 'ai.route.promote' OR r.maximum_uses<>1 OR r.maximum_spend<>0 OR r.maximum_volume<>1
        OR NOT app.authority_founder(NEW.activation_session_id,true) OR c.id IS NULL OR e.id IS NULL
        OR c.body->>'primary_provider' NOT IN ('fake_openai','fake_anthropic')
        OR c.body->>'environment' IS DISTINCT FROM 'technical' OR e.route_id IS DISTINCT FROM c.id
        OR e.body->>'decision' IS DISTINCT FROM 'technical_pass'
        OR r.payload->>'route_id' IS DISTINCT FROM c.id::text OR r.payload->>'route_hash' IS DISTINCT FROM c.content_hash
        OR r.payload->>'binding_hash' IS DISTINCT FROM e.binding_hash
        OR NOT EXISTS(SELECT 1 FROM app.ai_routes WHERE id=(r.payload->>'rollback_route_id')::uuid)
        OR NOT EXISTS(SELECT 1 FROM app.ai_route_states WHERE state='active' AND route_id=(r.payload->>'current_route_id')::uuid)
        OR EXISTS(SELECT 1 FROM app.approval_uses WHERE manifest_id=NEW.manifest_id) THEN
        RAISE EXCEPTION 'Exact evaluated route authority required' USING ERRCODE='23514'; END IF;
      NEW.use_number=1;
      RETURN NEW;
    END $$;
    CREATE TRIGGER bounded_route_use BEFORE INSERT ON app.approval_uses FOR EACH ROW WHEN (NEW.activation_route_id IS NOT NULL) EXECUTE FUNCTION app.ai_route_use_guard();
    CREATE FUNCTION app.ai_promotion_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE u app.approval_uses; r app.approval_requests; e app.ai_evaluations;
    BEGIN
      IF (NEW.route_id,NEW.workspace_id) IS DISTINCT FROM (OLD.route_id,OLD.workspace_id) THEN RAISE EXCEPTION 'Immutable route identity' USING ERRCODE='23514'; END IF;
      IF NEW.state='active' THEN
        SELECT * INTO u FROM app.approval_uses WHERE activation_route_id=NEW.route_id AND manifest_id=NEW.manifest_id;
        SELECT a.* INTO r FROM app.approval_requests a JOIN app.approval_manifests m ON m.request_id=a.id WHERE m.id=NEW.manifest_id;
        SELECT * INTO e FROM app.ai_evaluations WHERE id=NEW.evaluation_id;
        IF u.id IS NULL OR NOT app.authority_founder(u.activation_session_id,true)
          OR app.authority_validate(u.manifest_id) IS NOT NULL
          OR EXISTS(SELECT 1 FROM app.approval_use_results WHERE use_id=u.id)
          OR e.id IS DISTINCT FROM (r.payload->>'evaluation_id')::uuid
          OR NEW.rollback_route_id IS DISTINCT FROM (r.payload->>'rollback_route_id')::uuid
          OR NEW.approved_by IS DISTINCT FROM app.current_principal_id()
          OR NEW.activated_at IS NULL THEN RAISE EXCEPTION 'Human exact promotion required' USING ERRCODE='23514'; END IF;
      ELSIF NEW.state NOT IN ('evaluated','superseded','disabled') THEN
        RAISE EXCEPTION 'Invalid route transition' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER human_route_promotion BEFORE UPDATE ON app.ai_route_states FOR EACH ROW EXECUTE FUNCTION app.ai_promotion_guard();
    CREATE FUNCTION app.ai_promotion_result_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE u app.approval_uses;
    BEGIN
      SELECT * INTO u FROM app.approval_uses WHERE id=NEW.use_id;
      IF u.activation_route_id IS NOT NULL AND (NEW.result<>'consumed' OR NOT EXISTS(
        SELECT 1 FROM app.ai_route_states WHERE route_id=u.activation_route_id AND state='active' AND manifest_id=u.manifest_id)) THEN
        RAISE EXCEPTION 'Unproven route activation' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER proven_route_result BEFORE INSERT ON app.approval_use_results FOR EACH ROW EXECUTE FUNCTION app.ai_promotion_result_guard();
    REVOKE ALL ON FUNCTION app.ai_route_use_guard(),app.ai_promotion_guard(),app.ai_promotion_result_guard() FROM PUBLIC;
    """
    )


def downgrade() -> None:
    op.execute("""
    DO $$ BEGIN IF EXISTS(SELECT 1 FROM app.approval_uses WHERE activation_route_id IS NOT NULL) THEN RAISE EXCEPTION 'Preserve route decisions'; END IF; END $$;
    DROP TRIGGER bounded_route_use ON app.approval_uses;
    DROP TRIGGER human_route_promotion ON app.ai_route_states;
    DROP TRIGGER proven_route_result ON app.approval_use_results;
    DROP FUNCTION app.ai_route_use_guard(),app.ai_promotion_guard(),app.ai_promotion_result_guard();
    DROP TRIGGER bounded_use ON app.approval_uses;
    CREATE TRIGGER bounded_use BEFORE INSERT ON app.approval_uses FOR EACH ROW EXECUTE FUNCTION app.authority_use_guard();
    ALTER TABLE app.approval_uses DROP CONSTRAINT authority_use_kind,DROP COLUMN activation_route_id;
    ALTER TABLE app.approval_uses ADD CONSTRAINT authority_use_kind CHECK((effect_id IS NOT NULL AND job_id IS NOT NULL AND activation_policy_id IS NULL AND activation_session_id IS NULL)
      OR (effect_id IS NULL AND job_id IS NULL AND activation_policy_id IS NOT NULL AND activation_session_id IS NOT NULL AND spend_reserved=0 AND volume=1));
    DO $$ DECLARE body text; BEGIN
      body=pg_get_functiondef('app.authority_commit_guard()'::regprocedure);
      body=replace(body,'''policy.activate'',''ai.route.promote''','''policy.activate''');
      EXECUTE body;
    END $$;
    """)
