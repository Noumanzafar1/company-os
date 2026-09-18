"""Enforce governed input ownership and current budget at SQL commitment."""

from alembic import op

revision = "0017_authority_commit_boundary"
down_revision = "0016_authority_exact_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER FUNCTION app.authority_validate(uuid) RENAME TO authority_validate_v1;
    CREATE FUNCTION app.authority_validate(mid uuid) RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
    DECLARE code text; rules jsonb;
    BEGIN
      IF NOT EXISTS(SELECT 1 FROM app.workspaces WHERE id=app.current_workspace_id() AND status='active') THEN
        RETURN 'WORKSPACE_NOT_ACTIVE'; END IF;
      code=app.authority_validate_v1(mid);
      IF code IS NOT NULL THEN RETURN code; END IF;
      SELECT v.rules INTO rules FROM app.policy_versions v JOIN app.approval_requests r ON r.policy_version_id=v.id
        JOIN app.approval_manifests m ON m.request_id=r.id WHERE m.id=mid;
      IF NOT EXISTS(SELECT 1 FROM app.memberships m JOIN app.principals p ON p.id=m.principal_id JOIN app.roles r ON r.id=m.role_id
        WHERE m.workspace_id=app.current_workspace_id() AND p.id=app.current_principal_id() AND m.status='active'
        AND (m.expires_at IS NULL OR m.expires_at>clock_timestamp())
        AND ((session_user='company_worker' AND p.kind='service') OR (p.kind='user' AND rules->'permitted_roles' ? r.name))) THEN
        RETURN 'EXECUTOR_ROLE_DENIED'; END IF;
      RETURN NULL;
    END $$;
    ALTER FUNCTION app.authority_validate(uuid) OWNER TO company_auth;
    REVOKE ALL ON FUNCTION app.authority_validate(uuid) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION app.authority_validate(uuid) TO company_api,company_worker;
    REVOKE EXECUTE ON FUNCTION app.authority_validate_v1(uuid) FROM company_api,company_worker;
    CREATE FUNCTION app.authority_commit_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE governed boolean;
    BEGIN
      IF TG_TABLE_NAME='approval_decisions' THEN
        IF NOT EXISTS(SELECT 1 FROM app.workspaces WHERE id=NEW.workspace_id AND status='active') THEN
          RAISE EXCEPTION 'Workspace not active' USING ERRCODE='23514'; END IF;
        IF NOT EXISTS(SELECT 1 FROM app.approval_requests WHERE id=NEW.request_id
          AND action IN ('runtime.synthetic_external_action','runtime.synthetic_batch_action')) THEN
          RAISE EXCEPTION 'Action has no material executor' USING ERRCODE='23514'; END IF;
        RETURN NEW;
      END IF;
      IF TG_TABLE_NAME='authority_bindings' THEN
        IF EXISTS(SELECT 1 FROM app.jobs WHERE input_ref=NEW.input_id) THEN
          RAISE EXCEPTION 'Cannot attach retroactive authority' USING ERRCODE='23514'; END IF;
        RETURN NEW;
      END IF;
      SELECT EXISTS(SELECT 1 FROM app.authority_bindings WHERE input_id=NEW.request_ref) INTO governed;
      IF TG_OP='INSERT' THEN
        IF NOT governed AND EXISTS(SELECT 1 FROM app.runtime_inputs WHERE id=NEW.request_ref AND logical_key LIKE 'authority:%') THEN
          RAISE EXCEPTION 'Governed input missing authority' USING ERRCODE='23514'; END IF;
      ELSIF governed AND NEW.state='dispatching' AND OLD.state='prepared' THEN
        PERFORM b.id FROM app.budgets b WHERE b.id=(SELECT budget_id FROM app.budget_reservations WHERE id=NEW.reservation_id)
          OR EXISTS(SELECT 1 FROM app.reservation_budget_caps c WHERE c.reservation_id=NEW.reservation_id AND c.budget_id=b.id) ORDER BY b.id FOR SHARE;
        IF NOT EXISTS(SELECT 1 FROM app.budget_reservations WHERE id=NEW.reservation_id AND state='reserved')
          OR EXISTS(SELECT 1 FROM app.budgets b WHERE (b.id=(SELECT budget_id FROM app.budget_reservations WHERE id=NEW.reservation_id)
            OR EXISTS(SELECT 1 FROM app.reservation_budget_caps c WHERE c.reservation_id=NEW.reservation_id AND c.budget_id=b.id))
            AND (b.status<>'active' OR b.period_start>clock_timestamp() OR b.period_end<=clock_timestamp() OR b.spent_usd+b.reserved_usd>b.limit_usd))
          OR NOT app.runtime_company_cap_ok() THEN
          RAISE EXCEPTION 'Current dispatch budget blocked' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER authority_commit BEFORE INSERT OR UPDATE ON app.external_effects FOR EACH ROW EXECUTE FUNCTION app.authority_commit_guard();
    CREATE TRIGGER authority_not_retroactive BEFORE INSERT ON app.authority_bindings FOR EACH ROW EXECUTE FUNCTION app.authority_commit_guard();
    CREATE TRIGGER authority_workspace_active BEFORE INSERT ON app.approval_decisions FOR EACH ROW WHEN (NEW.decision='approve') EXECUTE FUNCTION app.authority_commit_guard();
    REVOKE ALL ON FUNCTION app.authority_commit_guard() FROM PUBLIC;
    """)


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION app.authority_commit_guard() CASCADE; DROP FUNCTION app.authority_validate(uuid); ALTER FUNCTION app.authority_validate_v1(uuid) RENAME TO authority_validate; GRANT EXECUTE ON FUNCTION app.authority_validate(uuid) TO company_api,company_worker"
    )
