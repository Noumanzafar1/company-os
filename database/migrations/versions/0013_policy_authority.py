"""Phase 5 exact synthetic authority; preserve migrations 0001 through 0012."""

from alembic import op

revision = "0013_policy_authority"
down_revision = "0012_phase4_review_fixes"
branch_labels = None
depends_on = None

# Frozen physical schema. Existing Phase 4 fixtures remain offline test operations.
TABLES = {
    "authority_command_receipts": (
        True,
        "command_type varchar(100) NOT NULL, idempotency_key varchar(128) NOT NULL, request_hash char(64) NOT NULL, response jsonb NOT NULL, UNIQUE(workspace_id,created_by,command_type,idempotency_key)",
    ),
    "policies": (False, "action text NOT NULL UNIQUE, active_version_id uuid"),
    "policy_versions": (
        True,
        "policy_id uuid NOT NULL, version integer NOT NULL CHECK(version>0), rules jsonb NOT NULL, content_hash char(64) NOT NULL, effective_at timestamptz NOT NULL, expires_at timestamptz NOT NULL, session_id uuid, rationale varchar(500) NOT NULL, CHECK(expires_at>effective_at), UNIQUE(workspace_id,policy_id,version)",
    ),
    "authority_test_targets": (
        False,
        "label varchar(100) NOT NULL, suppressed boolean NOT NULL DEFAULT false, rights_valid boolean NOT NULL DEFAULT true",
    ),
    "approval_requests": (
        False,
        "action text NOT NULL, policy_version_id uuid NOT NULL, payload jsonb NOT NULL, payload_hash char(64) NOT NULL, scope_hash char(64) NOT NULL, target_set_hash char(64) NOT NULL, maximum_uses integer NOT NULL CHECK(maximum_uses BETWEEN 1 AND 100), maximum_spend numeric(20,8) NOT NULL CHECK(maximum_spend>=0), maximum_volume integer NOT NULL CHECK(maximum_volume>0), expires_at timestamptz NOT NULL, rationale varchar(500) NOT NULL, correlation_id uuid NOT NULL, supersedes_id uuid, state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','approved','rejected','expired','revoked','superseded')), CHECK(expires_at>created_at)",
    ),
    "approval_targets": (
        True,
        "request_id uuid NOT NULL, target_id uuid NOT NULL, expected_version bigint NOT NULL CHECK(expected_version>0), UNIQUE(workspace_id,request_id,target_id)",
    ),
    "approval_decisions": (
        True,
        "request_id uuid NOT NULL, decision text NOT NULL CHECK(decision IN ('approve','reject','revise','revoke')), session_id uuid NOT NULL, rationale varchar(500) NOT NULL, correlation_id uuid NOT NULL",
    ),
    "approval_manifests": (
        True,
        "request_id uuid NOT NULL, decision_id uuid NOT NULL, scope jsonb NOT NULL, manifest_hash char(64) NOT NULL, starts_at timestamptz NOT NULL, expires_at timestamptz NOT NULL, UNIQUE(workspace_id,request_id), CHECK(expires_at>starts_at)",
    ),
    "authority_freezes": (
        True,
        "action text, rationale varchar(500) NOT NULL, correlation_id uuid NOT NULL",
    ),
    "policy_decisions": (
        True,
        "request_id uuid, policy_version_id uuid, action text NOT NULL, payload_hash char(64) NOT NULL, target_set_hash char(64) NOT NULL, object_versions jsonb NOT NULL, assurance text NOT NULL, result text NOT NULL CHECK(result IN ('ALLOW','DENY','REQUIRE_APPROVAL','QUARANTINE')), reasons text[] NOT NULL, correlation_id uuid NOT NULL",
    ),
    "authority_bindings": (
        True,
        "manifest_id uuid NOT NULL, input_id uuid NOT NULL, payload_hash char(64) NOT NULL, target_set_hash char(64) NOT NULL, UNIQUE(workspace_id,input_id)",
    ),
    "approval_uses": (
        True,
        "manifest_id uuid NOT NULL, effect_id uuid NOT NULL, job_id uuid NOT NULL, use_number integer NOT NULL CHECK(use_number>0), spend_reserved numeric(20,8) NOT NULL CHECK(spend_reserved>=0), volume integer NOT NULL CHECK(volume>0), UNIQUE(workspace_id,effect_id), UNIQUE(workspace_id,manifest_id,use_number)",
    ),
    "approval_use_results": (
        True,
        "use_id uuid NOT NULL, result text NOT NULL CHECK(result IN ('consumed','released')), UNIQUE(workspace_id,use_id)",
    ),
}
REFS = {
    "policies": {"active_version_id": "policy_versions"},
    "policy_versions": {"policy_id": "policies"},
    "approval_requests": {
        "policy_version_id": "policy_versions",
        "supersedes_id": "approval_requests",
    },
    "approval_targets": {"request_id": "approval_requests", "target_id": "authority_test_targets"},
    "approval_decisions": {"request_id": "approval_requests"},
    "approval_manifests": {"request_id": "approval_requests", "decision_id": "approval_decisions"},
    "policy_decisions": {"request_id": "approval_requests", "policy_version_id": "policy_versions"},
    "authority_bindings": {"manifest_id": "approval_manifests", "input_id": "runtime_inputs"},
    "approval_uses": {
        "manifest_id": "approval_manifests",
        "effect_id": "external_effects",
        "job_id": "jobs",
    },
    "approval_use_results": {"use_id": "approval_uses"},
}


def upgrade() -> None:
    for table, (immutable, fields) in TABLES.items():
        mutable = (
            ""
            if immutable
            else ",updated_at timestamptz NOT NULL DEFAULT now(),updated_by uuid NOT NULL REFERENCES app.principals(id),record_version bigint NOT NULL DEFAULT 1 CHECK(record_version>0)"
        )
        # Action uniqueness is tenant-local.
        fields = fields.replace(
            "action text NOT NULL UNIQUE", "action text NOT NULL, UNIQUE(workspace_id,action)"
        )
        op.execute(
            f"CREATE TABLE app.{table}(id uuid PRIMARY KEY,workspace_id uuid NOT NULL REFERENCES app.workspaces(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),created_by uuid NOT NULL REFERENCES app.principals(id),schema_version smallint NOT NULL DEFAULT 1{mutable},{fields},UNIQUE(workspace_id,id))"
        )
        op.execute(
            f"ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY; ALTER TABLE app.{table} FORCE ROW LEVEL SECURITY"
        )
        op.execute(
            f"CREATE POLICY authority_scope ON app.{table} TO company_api,company_worker USING(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id)) WITH CHECK(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id))"
        )
        op.execute(
            f"GRANT SELECT ON app.{table} TO company_api,company_worker; GRANT INSERT{'' if immutable else ',UPDATE'} ON app.{table} TO company_api"
        )
        op.execute(f"CREATE INDEX {table}_chronology ON app.{table}(workspace_id,created_at,id)")
        op.execute(
            f"CREATE TRIGGER authority_history BEFORE UPDATE OR DELETE ON app.{table} FOR EACH ROW EXECUTE FUNCTION app.core_row_guard('{'append' if immutable else 'mutable'}')"
        )
        op.execute(
            f"CREATE TRIGGER authority_actor BEFORE INSERT OR UPDATE ON app.{table} FOR EACH ROW EXECUTE FUNCTION app.runtime_actor_guard('{'append' if immutable else 'mutable'}')"
        )
    for table, refs in REFS.items():
        for column, parent in refs.items():
            op.execute(
                f"ALTER TABLE app.{table} ADD FOREIGN KEY(workspace_id,{column}) REFERENCES app.{parent}(workspace_id,id); CREATE INDEX {table}_{column}_fk ON app.{table}(workspace_id,{column})"
            )
    op.execute("""
    GRANT INSERT ON app.approval_uses,app.approval_use_results,app.policy_decisions TO company_worker;
    CREATE FUNCTION app.authority_founder(sid uuid, mfa boolean) RETURNS boolean
    LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
      SELECT session_user='company_api' AND app.has_active_membership(app.current_principal_id(),app.current_workspace_id())
      AND EXISTS(SELECT 1 FROM app.memberships m JOIN app.roles r ON r.id=m.role_id
        JOIN app.principals p ON p.id=m.principal_id JOIN app.auth_sessions s ON s.principal_id=p.id
        WHERE m.workspace_id=app.current_workspace_id() AND p.id=app.current_principal_id()
        AND p.kind='user' AND p.status='active' AND r.name='founder' AND m.status='active'
        AND (m.expires_at IS NULL OR m.expires_at>clock_timestamp())
        AND s.id=sid AND s.revoked_at IS NULL AND s.expires_at>clock_timestamp()
        AND s.last_seen_at>clock_timestamp()-interval '30 minutes'
        AND (NOT mfa OR (s.assurance='aal2' AND s.mfa_at<=clock_timestamp() AND s.mfa_at>=clock_timestamp()-interval '10 minutes')))
    $$;
    ALTER FUNCTION app.authority_founder(uuid,boolean) OWNER TO company_auth;
    REVOKE ALL ON FUNCTION app.authority_founder(uuid,boolean) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION app.authority_founder(uuid,boolean) TO company_api,company_worker;

    CREATE FUNCTION app.authority_member(p uuid, needs_founder boolean) RETURNS boolean
    LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
      SELECT app.has_active_membership(app.current_principal_id(),app.current_workspace_id()) AND EXISTS(
        SELECT 1 FROM app.memberships m JOIN app.principals x ON x.id=m.principal_id JOIN app.roles r ON r.id=m.role_id
        WHERE m.workspace_id=app.current_workspace_id() AND m.principal_id=p AND m.status='active'
        AND (m.expires_at IS NULL OR m.expires_at>clock_timestamp()) AND x.status='active'
        AND (NOT needs_founder OR (r.name='founder' AND x.kind='user')))
    $$;
    ALTER FUNCTION app.authority_member(uuid,boolean) OWNER TO company_auth;
    REVOKE ALL ON FUNCTION app.authority_member(uuid,boolean) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION app.authority_member(uuid,boolean) TO company_api,company_worker;

    CREATE FUNCTION app.authority_request_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    BEGIN
      IF TG_OP='UPDATE' THEN
        IF (to_jsonb(NEW)-ARRAY['state','record_version','updated_by','updated_at']) IS DISTINCT FROM
           (to_jsonb(OLD)-ARRAY['state','record_version','updated_by','updated_at']) THEN
          RAISE EXCEPTION 'Immutable approval scope' USING ERRCODE='23514'; END IF;
        IF NOT ((OLD.state='pending' AND NEW.state IN ('approved','rejected','expired','superseded'))
          OR (OLD.state='approved' AND NEW.state IN ('revoked','expired','superseded'))) THEN
          RAISE EXCEPTION 'Invalid approval transition' USING ERRCODE='23514'; END IF;
        IF NEW.state='approved' AND NOT EXISTS(SELECT 1 FROM app.approval_manifests WHERE request_id=NEW.id) THEN
          RAISE EXCEPTION 'Manifest required' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER request_scope BEFORE UPDATE ON app.approval_requests FOR EACH ROW EXECUTE FUNCTION app.authority_request_guard();

    CREATE FUNCTION app.authority_grant_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE r app.approval_requests; d app.approval_decisions; v app.policy_versions;
    BEGIN
      IF TG_TABLE_NAME='approval_decisions' THEN
        IF NOT app.authority_founder(NEW.session_id,NEW.decision<>'revoke') THEN
          RAISE EXCEPTION 'Founder assurance required' USING ERRCODE='23514'; END IF;
        SELECT * INTO r FROM app.approval_requests WHERE id=NEW.request_id FOR UPDATE;
        IF (NEW.decision='revoke' AND r.state<>'approved') OR (NEW.decision<>'revoke' AND r.state<>'pending') THEN
          RAISE EXCEPTION 'Invalid decision state' USING ERRCODE='23514'; END IF;
        IF NEW.decision='approve' AND (r.expires_at<=clock_timestamp() OR r.action='runtime.synthetic_binding_decision') THEN
          RAISE EXCEPTION 'Expired or human only' USING ERRCODE='23514'; END IF;
        IF NEW.decision='approve' THEN
          SELECT * INTO v FROM app.policy_versions WHERE id=r.policy_version_id;
          IF NOT EXISTS(SELECT 1 FROM app.policies WHERE id=v.policy_id AND active_version_id=v.id)
            OR v.rules->>'action' IS DISTINCT FROM r.action OR clock_timestamp()>=v.expires_at
            OR r.maximum_uses>(v.rules->>'maximum_uses')::integer
            OR r.maximum_spend>(v.rules->>'maximum_spend')::numeric
            OR r.maximum_volume>(v.rules->>'maximum_volume')::integer
            OR EXTRACT(EPOCH FROM r.expires_at-r.created_at)>(v.rules->>'maximum_expiry_seconds')::integer
            OR (SELECT count(*) FROM app.approval_targets WHERE request_id=r.id) NOT BETWEEN 1 AND (v.rules->>'maximum_targets')::integer THEN
            RAISE EXCEPTION 'Policy envelope exceeded' USING ERRCODE='23514'; END IF;
        END IF;
      ELSIF TG_TABLE_NAME='approval_manifests' THEN
        SELECT * INTO r FROM app.approval_requests WHERE id=NEW.request_id FOR UPDATE;
        SELECT * INTO d FROM app.approval_decisions WHERE id=NEW.decision_id;
        IF d.request_id IS DISTINCT FROM r.id OR d.decision IS DISTINCT FROM 'approve'
          OR d.created_by IS DISTINCT FROM NEW.created_by OR NOT app.authority_founder(d.session_id,true)
          OR NEW.expires_at IS DISTINCT FROM r.expires_at OR r.state<>'pending'
          OR NEW.scope->>'scope_hash' IS DISTINCT FROM r.scope_hash
          OR NEW.scope->>'payload_hash' IS DISTINCT FROM r.payload_hash
          OR NEW.scope->>'target_set_hash' IS DISTINCT FROM r.target_set_hash
          OR (NEW.scope->>'maximum_uses')::integer IS DISTINCT FROM r.maximum_uses
          OR (NEW.scope->>'maximum_spend')::numeric IS DISTINCT FROM r.maximum_spend
          OR (NEW.scope->>'maximum_volume')::integer IS DISTINCT FROM r.maximum_volume
          OR NEW.scope->>'action' IS DISTINCT FROM r.action
          OR NEW.scope->>'policy_version_id' IS DISTINCT FROM r.policy_version_id::text THEN
          RAISE EXCEPTION 'Invalid exact grant' USING ERRCODE='23514'; END IF;
      ELSIF TG_TABLE_NAME='policy_versions' THEN
        IF current_user='company_worker' OR (current_user='company_api' AND NOT app.authority_founder(NEW.session_id,true)) THEN
          RAISE EXCEPTION 'Founder policy assurance required' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER human_grant BEFORE INSERT ON app.approval_decisions FOR EACH ROW EXECUTE FUNCTION app.authority_grant_guard();
    CREATE TRIGGER exact_grant BEFORE INSERT ON app.approval_manifests FOR EACH ROW EXECUTE FUNCTION app.authority_grant_guard();
    CREATE TRIGGER policy_grant BEFORE INSERT ON app.policy_versions FOR EACH ROW EXECUTE FUNCTION app.authority_grant_guard();

    CREATE FUNCTION app.authority_validate(mid uuid) RETURNS text LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE m app.approval_manifests; r app.approval_requests; v app.policy_versions; p app.policies;
    BEGIN
      -- Shared workspace gate serializes freeze/activation and execution.
      PERFORM pg_advisory_xact_lock(hashtextextended(app.current_workspace_id()::text,55));
      SELECT * INTO m FROM app.approval_manifests WHERE id=mid;
      IF NOT FOUND THEN RETURN 'AUTHORITY_NOT_FOUND'; END IF;
      SELECT * INTO r FROM app.approval_requests WHERE id=m.request_id FOR UPDATE;
      SELECT * INTO v FROM app.policy_versions WHERE id=r.policy_version_id;
      SELECT * INTO p FROM app.policies WHERE id=v.policy_id;
      IF r.state<>'approved' THEN RETURN 'AUTHORITY_'||upper(r.state); END IF;
      IF clock_timestamp()<m.starts_at OR clock_timestamp()>=m.expires_at THEN RETURN 'EXPIRED'; END IF;
      IF p.active_version_id IS DISTINCT FROM v.id OR v.expires_at<=clock_timestamp() OR v.effective_at>clock_timestamp() THEN RETURN 'POLICY_CHANGED'; END IF;
      IF r.action='runtime.synthetic_binding_decision' THEN RETURN 'HUMAN_ONLY'; END IF;
      IF EXISTS(SELECT 1 FROM app.authority_freezes WHERE action IS NULL OR action=r.action) THEN RETURN 'EMERGENCY_FREEZE'; END IF;
      IF NOT app.authority_member(r.created_by,false) OR NOT app.authority_member(m.created_by,true) THEN RETURN 'MEMBERSHIP_REVOKED'; END IF;
      PERFORM t.id FROM app.authority_test_targets t JOIN app.approval_targets a ON a.target_id=t.id WHERE a.request_id=r.id ORDER BY t.id FOR SHARE OF t;
      IF NOT EXISTS(SELECT 1 FROM app.approval_targets WHERE request_id=r.id) THEN RETURN 'TARGETS_MISSING'; END IF;
      IF EXISTS(SELECT 1 FROM app.authority_test_targets t JOIN app.approval_targets a ON a.target_id=t.id WHERE a.request_id=r.id AND t.suppressed) THEN RETURN 'SUPPRESSED'; END IF;
      IF EXISTS(SELECT 1 FROM app.authority_test_targets t JOIN app.approval_targets a ON a.target_id=t.id WHERE a.request_id=r.id AND NOT t.rights_valid) THEN RETURN 'RIGHTS_REVOKED'; END IF;
      IF EXISTS(SELECT 1 FROM app.authority_test_targets t JOIN app.approval_targets a ON a.target_id=t.id WHERE a.request_id=r.id AND t.record_version<>a.expected_version) THEN RETURN 'OBJECT_VERSION_CHANGED'; END IF;
      RETURN NULL;
    END $$;
    REVOKE ALL ON FUNCTION app.authority_validate(uuid) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION app.authority_validate(uuid) TO company_api,company_worker;

    CREATE FUNCTION app.authority_use_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE code text; r app.approval_requests; b app.authority_bindings; e app.external_effects; n integer; spent numeric; vol bigint;
    BEGIN
      code=app.authority_validate(NEW.manifest_id);
      IF code IS NOT NULL THEN RAISE EXCEPTION '%',code USING ERRCODE='23514'; END IF;
      SELECT r0.* INTO r FROM app.approval_requests r0 JOIN app.approval_manifests m ON m.request_id=r0.id WHERE m.id=NEW.manifest_id;
      SELECT * INTO e FROM app.external_effects WHERE id=NEW.effect_id;
      SELECT * INTO b FROM app.authority_bindings WHERE input_id=e.request_ref;
      IF b.manifest_id IS DISTINCT FROM NEW.manifest_id OR e.job_id IS DISTINCT FROM NEW.job_id OR e.state<>'prepared'
        OR b.payload_hash IS DISTINCT FROM r.payload_hash OR b.target_set_hash IS DISTINCT FROM r.target_set_hash
        OR NEW.spend_reserved IS DISTINCT FROM (SELECT maximum_usd FROM app.budget_reservations WHERE id=e.reservation_id)
        OR NEW.volume IS DISTINCT FROM (SELECT count(*)::integer FROM app.approval_targets WHERE request_id=r.id) THEN
        RAISE EXCEPTION 'Authority binding mismatch' USING ERRCODE='23514'; END IF;
      SELECT count(*),COALESCE(sum(u.spend_reserved),0),COALESCE(sum(u.volume),0) INTO n,spent,vol
        FROM app.approval_uses u WHERE u.manifest_id=NEW.manifest_id
        AND NOT EXISTS(SELECT 1 FROM app.approval_use_results x WHERE x.use_id=u.id AND x.result='released');
      IF n>=r.maximum_uses OR spent+NEW.spend_reserved>r.maximum_spend OR vol+NEW.volume>r.maximum_volume THEN
        RAISE EXCEPTION 'AUTHORITY_LIMIT' USING ERRCODE='23514'; END IF;
      NEW.use_number=(SELECT COALESCE(max(use_number),0)+1 FROM app.approval_uses WHERE manifest_id=NEW.manifest_id);
      RETURN NEW;
    END $$;
    CREATE TRIGGER bounded_use BEFORE INSERT ON app.approval_uses FOR EACH ROW EXECUTE FUNCTION app.authority_use_guard();

    CREATE FUNCTION app.authority_dispatch_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE b app.authority_bindings; code text;
    BEGIN
      IF NEW.state='dispatching' AND OLD.state='prepared' THEN
        SELECT * INTO b FROM app.authority_bindings WHERE input_id=NEW.request_ref;
        IF FOUND THEN
          code=app.authority_validate(b.manifest_id);
          IF code IS NOT NULL OR NOT EXISTS(SELECT 1 FROM app.approval_uses WHERE effect_id=NEW.id AND manifest_id=b.manifest_id) THEN
            RAISE EXCEPTION 'Dispatch authority denied: %',code USING ERRCODE='23514'; END IF;
        END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER authority_dispatch BEFORE UPDATE ON app.external_effects FOR EACH ROW EXECUTE FUNCTION app.authority_dispatch_guard();
    CREATE FUNCTION app.authority_write_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE r app.approval_requests; e app.external_effects; u app.approval_uses;
    BEGIN
      PERFORM pg_advisory_xact_lock(hashtextextended(NEW.workspace_id::text,55));
      IF TG_TABLE_NAME='approval_targets' THEN
        SELECT * INTO r FROM app.approval_requests WHERE id=NEW.request_id FOR UPDATE;
        IF r.state<>'pending' OR EXISTS(SELECT 1 FROM app.approval_decisions WHERE request_id=r.id)
          OR NOT EXISTS(SELECT 1 FROM app.authority_test_targets WHERE id=NEW.target_id AND record_version=NEW.expected_version) THEN
          RAISE EXCEPTION 'Frozen target scope' USING ERRCODE='23514'; END IF;
      ELSIF TG_TABLE_NAME='authority_bindings' THEN
        SELECT r0.* INTO r FROM app.approval_requests r0 JOIN app.approval_manifests m ON m.request_id=r0.id WHERE m.id=NEW.manifest_id;
        IF NEW.payload_hash IS DISTINCT FROM r.payload_hash OR NEW.target_set_hash IS DISTINCT FROM r.target_set_hash
          OR app.authority_validate(NEW.manifest_id) IS NOT NULL THEN
          RAISE EXCEPTION 'Invalid input authority' USING ERRCODE='23514'; END IF;
      ELSIF TG_TABLE_NAME='policies' THEN
        IF current_user IN ('company_api','company_worker') AND TG_OP='UPDATE' AND NEW.active_version_id IS NOT NULL AND NOT EXISTS(
          SELECT 1 FROM app.policy_versions WHERE id=NEW.active_version_id AND policy_id=NEW.id
          AND app.authority_founder(session_id,true)) THEN
          RAISE EXCEPTION 'Policy activation needs current human authority' USING ERRCODE='23514'; END IF;
      ELSIF TG_TABLE_NAME='approval_use_results' THEN
        SELECT * INTO u FROM app.approval_uses WHERE id=NEW.use_id;
        SELECT * INTO e FROM app.external_effects WHERE id=u.effect_id;
        IF NOT ((NEW.result='consumed' AND e.state='confirmed') OR (NEW.result='released' AND e.state IN ('cancelled','rejected'))) THEN
          RAISE EXCEPTION 'Unproven authority use outcome' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER frozen_targets BEFORE INSERT ON app.approval_targets FOR EACH ROW EXECUTE FUNCTION app.authority_write_guard();
    CREATE TRIGGER binding_scope BEFORE INSERT ON app.authority_bindings FOR EACH ROW EXECUTE FUNCTION app.authority_write_guard();
    CREATE TRIGGER policy_activation BEFORE UPDATE ON app.policies FOR EACH ROW EXECUTE FUNCTION app.authority_write_guard();
    CREATE TRIGGER freeze_serialization BEFORE INSERT ON app.authority_freezes FOR EACH ROW EXECUTE FUNCTION app.authority_write_guard();
    CREATE TRIGGER proven_use_result BEFORE INSERT ON app.approval_use_results FOR EACH ROW EXECUTE FUNCTION app.authority_write_guard();
    CREATE FUNCTION app.authority_effect_result() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    BEGIN
      IF NEW.state IN ('confirmed','rejected','cancelled') THEN
        INSERT INTO app.approval_use_results(id,workspace_id,created_by,use_id,result)
          SELECT gen_random_uuid(),NEW.workspace_id,app.current_principal_id(),u.id,
          CASE WHEN NEW.state='confirmed' THEN 'consumed' ELSE 'released' END
          FROM app.approval_uses u WHERE u.effect_id=NEW.id
          AND NOT EXISTS(SELECT 1 FROM app.approval_use_results x WHERE x.use_id=u.id);
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER authority_effect_result AFTER UPDATE ON app.external_effects FOR EACH ROW EXECUTE FUNCTION app.authority_effect_result();
    REVOKE ALL ON FUNCTION app.authority_write_guard(),app.authority_effect_result() FROM PUBLIC;
    REVOKE ALL ON FUNCTION app.authority_request_guard(),app.authority_grant_guard(),app.authority_use_guard(),app.authority_dispatch_guard() FROM PUBLIC;
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER authority_effect_result ON app.external_effects; DROP FUNCTION app.authority_effect_result(); DROP FUNCTION app.authority_write_guard() CASCADE; DROP TRIGGER authority_dispatch ON app.external_effects; DROP FUNCTION app.authority_dispatch_guard(); DROP FUNCTION app.authority_use_guard() CASCADE; DROP FUNCTION app.authority_validate(uuid); DROP FUNCTION app.authority_grant_guard() CASCADE; DROP FUNCTION app.authority_request_guard() CASCADE; DROP FUNCTION app.authority_founder(uuid,boolean); DROP FUNCTION app.authority_member(uuid,boolean)"
    )
    op.execute(
        "ALTER TABLE app.policies DROP CONSTRAINT policies_workspace_id_active_version_id_fkey"
    )
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE app.{table}")
