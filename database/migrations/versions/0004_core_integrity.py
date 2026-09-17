"""Tighten Phase 3 actor and reference invariants without changing applied SQL."""

from alembic import op

revision = "0004_core_integrity"
down_revision = "0003_core_business_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE FUNCTION app.core_principal_member(p uuid,w uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
      SELECT w=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),w)
      AND EXISTS(SELECT 1 FROM app.memberships m JOIN app.principals pr ON pr.id=m.principal_id
       WHERE m.workspace_id=w AND m.principal_id=p AND m.status='active'
       AND (m.expires_at IS NULL OR m.expires_at>now()) AND pr.status='active');
    $$;
    ALTER FUNCTION app.core_principal_member(uuid,uuid) OWNER TO company_auth;
    REVOKE ALL ON FUNCTION app.core_principal_member(uuid,uuid) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION app.core_principal_member(uuid,uuid) TO company_api;

    CREATE FUNCTION app.core_actor_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    BEGIN
      IF current_user='company_api' THEN
        IF TG_OP='INSERT' AND (NEW.created_by<>app.current_principal_id() OR NOT app.core_principal_member(NEW.created_by,NEW.workspace_id)) THEN
          RAISE EXCEPTION 'Invalid workspace actor' USING ERRCODE='23514';
        END IF;
        IF TG_TABLE_NAME='leads' THEN
          IF NOT app.core_principal_member(NEW.owner_principal_id,NEW.workspace_id) THEN
            RAISE EXCEPTION 'Invalid workspace owner' USING ERRCODE='23514';
          END IF;
        ELSIF TG_TABLE_NAME='document_grants' THEN
          IF NOT app.core_principal_member(NEW.principal_id,NEW.workspace_id) THEN
            RAISE EXCEPTION 'Invalid document grantee' USING ERRCODE='23514';
          END IF;
        END IF;
      END IF;
      RETURN NEW;
    END $$;

    DO $$ DECLARE t text; BEGIN
      FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='app' AND tablename NOT IN
      ('principals','users','service_identities','roles','role_permissions','workspaces','memberships','auth_sessions','audit_entries') LOOP
        EXECUTE format('DROP POLICY tenant_scope ON app.%I',t);
        EXECUTE format('CREATE POLICY tenant_scope ON app.%I TO company_api USING(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id)) WITH CHECK(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id))',t);
        EXECUTE format('CREATE TRIGGER core_actor BEFORE INSERT OR UPDATE ON app.%I FOR EACH ROW EXECUTE FUNCTION app.core_actor_guard()',t);
      END LOOP;
    END $$;
    REVOKE UPDATE ON app.resources FROM company_api;

    CREATE FUNCTION app.core_support_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE subject uuid; resource_kind text; required_decision text;
    BEGIN
      IF TG_TABLE_NAME='score_evidence' THEN
        SELECT s.subject_id,r.resource_type INTO subject,resource_kind FROM app.score_components c
          JOIN app.scores s ON s.workspace_id=c.workspace_id AND s.id=c.score_id
          JOIN app.resources r ON r.workspace_id=s.workspace_id AND r.id=s.subject_id
          WHERE c.workspace_id=NEW.workspace_id AND c.id=NEW.score_component_id;
        IF resource_kind='lead' THEN SELECT account_id INTO subject FROM app.leads WHERE workspace_id=NEW.workspace_id AND id=subject; END IF;
        IF NOT EXISTS(SELECT 1 FROM app.evidence WHERE workspace_id=NEW.workspace_id AND id=NEW.evidence_id AND subject_id=subject) THEN
          RAISE EXCEPTION 'Score support subject mismatch' USING ERRCODE='23514';
        END IF;
      ELSIF TG_TABLE_NAME='leads' THEN
        IF NEW.latest_score_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM app.scores WHERE workspace_id=NEW.workspace_id AND id=NEW.latest_score_id AND subject_id=NEW.id AND icp_version_id=NEW.icp_version_id) THEN
          RAISE EXCEPTION 'Lead score mismatch' USING ERRCODE='23514';
        END IF;
      ELSIF TG_TABLE_NAME='evidence' THEN
        IF NEW.supersedes_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM app.evidence WHERE workspace_id=NEW.workspace_id AND id=NEW.supersedes_id AND subject_id=NEW.subject_id AND fact_key=NEW.fact_key) THEN
          RAISE EXCEPTION 'Supersession mismatch' USING ERRCODE='23514';
        END IF;
      ELSIF TG_TABLE_NAME='evidence_retractions' THEN
        IF NEW.replacement_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM app.evidence a JOIN app.evidence b ON b.workspace_id=a.workspace_id AND b.subject_id=a.subject_id AND b.fact_key=a.fact_key WHERE a.workspace_id=NEW.workspace_id AND a.id=NEW.evidence_id AND b.id=NEW.replacement_id) THEN
          RAISE EXCEPTION 'Replacement mismatch' USING ERRCODE='23514';
        END IF;
      ELSIF TG_TABLE_NAME='signals' THEN
        IF NOT EXISTS(SELECT 1 FROM app.resources WHERE workspace_id=NEW.workspace_id AND id=NEW.subject_id AND resource_type IN ('account','person')) THEN
          RAISE EXCEPTION 'Invalid signal subject type' USING ERRCODE='23514';
        END IF;
      ELSIF TG_TABLE_NAME='identity_merges' THEN
        IF NOT EXISTS(SELECT 1 FROM app.decisions WHERE workspace_id=NEW.workspace_id AND id=NEW.decision_id AND subject_id=NEW.retired_id AND decision_type='identity_merge' AND outcome='approve') THEN
          RAISE EXCEPTION 'Reviewed merge decision required' USING ERRCODE='23514';
        END IF;
      ELSIF TG_TABLE_NAME='identity_merge_reversals' THEN
        SELECT retired_id INTO subject FROM app.identity_merges WHERE workspace_id=NEW.workspace_id AND id=NEW.merge_id;
        IF NOT EXISTS(SELECT 1 FROM app.decisions WHERE workspace_id=NEW.workspace_id AND id=NEW.decision_id AND subject_id=subject AND decision_type='identity_reversal' AND outcome='approve') THEN
          RAISE EXCEPTION 'Reviewed reversal decision required' USING ERRCODE='23514';
        END IF;
      END IF;
      RETURN NEW;
    END $$;
    DO $$ DECLARE t text; BEGIN
      FOREACH t IN ARRAY ARRAY['score_evidence','leads','evidence','evidence_retractions','signals','identity_merges','identity_merge_reversals'] LOOP
        EXECUTE format('CREATE TRIGGER core_support BEFORE INSERT OR UPDATE ON app.%I FOR EACH ROW EXECUTE FUNCTION app.core_support_guard()',t);
      END LOOP;
    END $$;
    REVOKE ALL ON FUNCTION app.core_actor_guard(),app.core_support_guard() FROM PUBLIC;
    """)


def downgrade() -> None:
    op.execute("""
    DO $$ DECLARE t text; BEGIN
      FOREACH t IN ARRAY ARRAY['score_evidence','leads','evidence','evidence_retractions','signals','identity_merges','identity_merge_reversals'] LOOP
        EXECUTE format('DROP TRIGGER core_support ON app.%I',t);
      END LOOP;
      FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='app' AND tablename NOT IN
      ('principals','users','service_identities','roles','role_permissions','workspaces','memberships','auth_sessions','audit_entries') LOOP
        EXECUTE format('DROP TRIGGER core_actor ON app.%I',t);
        EXECUTE format('DROP POLICY tenant_scope ON app.%I',t);
        EXECUTE format('CREATE POLICY tenant_scope ON app.%I TO company_api USING(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id)) WITH CHECK(workspace_id=app.current_workspace_id() AND created_by=app.current_principal_id() AND app.has_active_membership(app.current_principal_id(),workspace_id))',t);
      END LOOP;
    END $$;
    GRANT UPDATE ON app.resources TO company_api;
    DROP FUNCTION app.core_actor_guard();
    DROP FUNCTION app.core_support_guard();
    DROP FUNCTION app.core_principal_member(uuid,uuid);
    """)
