"""Exact policy activation, final temporal checks, and unchanged prior authority guards."""

from alembic import op

revision = "0018_phase5_review_fixes"
down_revision = "0017_authority_commit_boundary"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""

ALTER TABLE app.approval_requests ADD COLUMN policy_id uuid, ADD COLUMN candidate_version_id uuid,
 ADD COLUMN expected_policy_record_version bigint, ADD COLUMN expected_active_version_id uuid,
 ADD CONSTRAINT activation_policy_fk FOREIGN KEY(workspace_id,policy_id) REFERENCES app.policies(workspace_id,id),
 ADD CONSTRAINT activation_candidate_fk FOREIGN KEY(workspace_id,candidate_version_id) REFERENCES app.policy_versions(workspace_id,id),
 ADD CONSTRAINT activation_previous_fk FOREIGN KEY(workspace_id,expected_active_version_id) REFERENCES app.policy_versions(workspace_id,id),
 ADD CONSTRAINT activation_request_shape CHECK((action='policy.activate' AND policy_id IS NOT NULL AND candidate_version_id IS NOT NULL
   AND expected_policy_record_version IS NOT NULL AND expected_policy_record_version>0 AND maximum_uses=1 AND maximum_spend=0 AND maximum_volume=1)
   OR (action<>'policy.activate' AND policy_id IS NULL AND candidate_version_id IS NULL AND expected_policy_record_version IS NULL AND expected_active_version_id IS NULL));
CREATE INDEX activation_request_policy ON app.approval_requests(workspace_id,policy_id);
ALTER TABLE app.approval_uses ALTER COLUMN effect_id DROP NOT NULL, ALTER COLUMN job_id DROP NOT NULL,
 ADD COLUMN activation_policy_id uuid, ADD COLUMN activation_session_id uuid REFERENCES app.auth_sessions(id),
 ADD CONSTRAINT activation_use_policy_fk FOREIGN KEY(workspace_id,activation_policy_id) REFERENCES app.policies(workspace_id,id),
 ADD CONSTRAINT authority_use_kind CHECK((effect_id IS NOT NULL AND job_id IS NOT NULL AND activation_policy_id IS NULL AND activation_session_id IS NULL)
   OR (effect_id IS NULL AND job_id IS NULL AND activation_policy_id IS NOT NULL AND activation_session_id IS NOT NULL AND spend_reserved=0 AND volume=1));
CREATE UNIQUE INDEX one_policy_activation_use ON app.approval_uses(workspace_id,manifest_id) WHERE activation_policy_id IS NOT NULL;
GRANT UPDATE ON app.policies TO company_auth;
GRANT EXECUTE ON FUNCTION app.authority_canonical(jsonb) TO company_auth;

CREATE FUNCTION app.authority_candidate_current(rid uuid) RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE r app.approval_requests; p app.policies; c app.policy_versions;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended(app.current_workspace_id()::text,55));
  SELECT * INTO r FROM app.approval_requests WHERE id=rid;
  IF r.action IS DISTINCT FROM 'policy.activate' THEN RETURN 'NOT_POLICY_ACTIVATION'; END IF;
  SELECT * INTO p FROM app.policies WHERE id=r.policy_id FOR UPDATE;
  SELECT * INTO c FROM app.policy_versions WHERE id=r.candidate_version_id;
  IF p.id IS NULL OR c.id IS NULL OR c.policy_id IS DISTINCT FROM p.id THEN RETURN 'CANDIDATE_MISMATCH'; END IF;
  IF p.active_version_id IS DISTINCT FROM r.expected_active_version_id THEN RETURN 'ACTIVE_VERSION_CHANGED'; END IF;
  IF p.record_version IS DISTINCT FROM r.expected_policy_record_version THEN RETURN 'POLICY_RECORD_CHANGED'; END IF;
  IF r.payload->>'action' IS DISTINCT FROM 'policy.activate' OR r.payload->>'workspace_id' IS DISTINCT FROM r.workspace_id::text
    OR r.payload->>'policy_id' IS DISTINCT FROM p.id::text OR (r.payload->>'policy_record_version')::bigint IS DISTINCT FROM p.record_version
    OR (r.payload->>'current_active_version_id')::uuid IS DISTINCT FROM p.active_version_id
    OR r.payload->>'candidate_version_id' IS DISTINCT FROM c.id::text OR (r.payload->>'candidate_version_number')::integer IS DISTINCT FROM c.version
    OR r.payload->>'candidate_content_hash' IS DISTINCT FROM c.content_hash OR r.payload->'rules' IS DISTINCT FROM c.rules
    OR c.rules->>'action' IS DISTINCT FROM p.action
    OR (r.payload->>'candidate_effective_at')::timestamptz IS DISTINCT FROM c.effective_at
    OR (r.payload->>'candidate_expires_at')::timestamptz IS DISTINCT FROM c.expires_at
    OR c.content_hash IS DISTINCT FROM encode(sha256(convert_to(app.authority_canonical(c.rules),'UTF8')),'hex') THEN
    RETURN 'CANDIDATE_MISMATCH'; END IF;
  IF c.effective_at>clock_timestamp() OR c.expires_at<=clock_timestamp() THEN RETURN 'CANDIDATE_NOT_CURRENT'; END IF;
  RETURN NULL;
END $$;
ALTER FUNCTION app.authority_candidate_current(uuid) OWNER TO company_auth;
REVOKE ALL ON FUNCTION app.authority_candidate_current(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.authority_candidate_current(uuid) TO company_api,company_worker;

CREATE FUNCTION app.authority_temporal(mid uuid) RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE m app.approval_manifests; r app.approval_requests; v app.policy_versions; p app.policies; c app.policy_versions;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended(app.current_workspace_id()::text,55));
  SELECT * INTO m FROM app.approval_manifests WHERE id=mid;
  IF NOT FOUND THEN RETURN 'AUTHORITY_NOT_FOUND'; END IF;
  SELECT * INTO r FROM app.approval_requests WHERE id=m.request_id;
  SELECT * INTO v FROM app.policy_versions WHERE id=r.policy_version_id;
  SELECT * INTO p FROM app.policies WHERE id=v.policy_id;
  IF r.state<>'approved' THEN RETURN 'AUTHORITY_'||upper(r.state); END IF;
  IF p.active_version_id IS DISTINCT FROM v.id THEN RETURN 'POLICY_CHANGED'; END IF;
  IF r.action='policy.activate' THEN
    SELECT * INTO c FROM app.policy_versions WHERE id=r.candidate_version_id;
    IF c.effective_at>clock_timestamp() OR c.expires_at<=clock_timestamp() THEN RETURN 'CANDIDATE_NOT_CURRENT'; END IF;
  END IF;
  -- This clock is read AFTER all preceding work, never captured before target validation.
  IF m.starts_at>clock_timestamp() OR m.expires_at<=clock_timestamp() THEN RETURN 'EXPIRED'; END IF;
  IF v.effective_at>clock_timestamp() OR v.expires_at<=clock_timestamp() THEN RETURN 'POLICY_CHANGED'; END IF;
  RETURN NULL;
END $$;
ALTER FUNCTION app.authority_temporal(uuid) OWNER TO company_auth;
REVOKE ALL ON FUNCTION app.authority_temporal(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.authority_temporal(uuid) TO company_api,company_worker;

ALTER FUNCTION app.authority_validate(uuid) RENAME TO authority_validate_before_review;
REVOKE EXECUTE ON FUNCTION app.authority_validate_before_review(uuid) FROM company_api,company_worker;
CREATE FUNCTION app.authority_validate(mid uuid) RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE r app.approval_requests; m app.approval_manifests; code text;
BEGIN
  SELECT r0.* INTO r FROM app.approval_requests r0 JOIN app.approval_manifests m0 ON m0.request_id=r0.id WHERE m0.id=mid;
  IF r.action='policy.activate' THEN
    PERFORM pg_advisory_xact_lock(hashtextextended(app.current_workspace_id()::text,55));
    SELECT * INTO r FROM app.approval_requests WHERE id=r.id FOR UPDATE;
    SELECT * INTO m FROM app.approval_manifests WHERE id=mid;
    IF NOT EXISTS(SELECT 1 FROM app.workspaces WHERE id=app.current_workspace_id() AND status='active') THEN RETURN 'WORKSPACE_NOT_ACTIVE'; END IF;
    IF session_user<>'company_api' OR NOT app.authority_member(app.current_principal_id(),true)
      OR NOT app.authority_member(r.created_by,true) OR NOT app.authority_member(m.created_by,true) THEN RETURN 'EXECUTOR_ROLE_DENIED'; END IF;
    IF EXISTS(SELECT 1 FROM app.authority_freezes WHERE action IS NULL OR action='policy.activate') THEN RETURN 'EMERGENCY_FREEZE'; END IF;
    code=app.authority_temporal(mid);
    IF code IS NOT NULL THEN RETURN code; END IF;
    code=app.authority_candidate_current(r.id);
  ELSE
    -- Preserves every prior workspace, gate, role, membership, target and safety lock/check.
    code=app.authority_validate_before_review(mid);
  END IF;
  IF code IS NOT NULL THEN RETURN code; END IF;
  RETURN app.authority_temporal(mid);
END $$;
ALTER FUNCTION app.authority_validate(uuid) OWNER TO company_auth;
REVOKE ALL ON FUNCTION app.authority_validate(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.authority_validate(uuid) TO company_api,company_worker;

CREATE FUNCTION app.authority_final_clock_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
DECLARE mid uuid; code text;
BEGIN
  IF TG_TABLE_NAME='approval_uses' THEN mid=NEW.manifest_id;
  ELSIF TG_TABLE_NAME='fake_receipts' THEN
    SELECT b.manifest_id INTO mid FROM app.authority_bindings b JOIN app.external_effects e ON e.request_ref=b.input_id WHERE e.id=NEW.effect_id;
  ELSE
    SELECT manifest_id INTO mid FROM app.authority_bindings WHERE input_id=NEW.request_ref;
  END IF;
  IF mid IS NOT NULL THEN
    code=app.authority_temporal(mid);
    IF code IS NOT NULL THEN RAISE EXCEPTION '%',code USING ERRCODE='23514'; END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER zzzz_authority_use_clock BEFORE INSERT ON app.approval_uses FOR EACH ROW EXECUTE FUNCTION app.authority_final_clock_guard();
CREATE TRIGGER zzzz_authority_receipt_clock BEFORE INSERT ON app.fake_receipts FOR EACH ROW EXECUTE FUNCTION app.authority_final_clock_guard();
CREATE TRIGGER zzzz_authority_dispatch_clock BEFORE UPDATE ON app.external_effects FOR EACH ROW WHEN (NEW.state='dispatching' AND OLD.state='prepared') EXECUTE FUNCTION app.authority_final_clock_guard();
REVOKE ALL ON FUNCTION app.authority_final_clock_guard() FROM PUBLIC;

CREATE FUNCTION app.policy_activation_pointer_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
DECLARE u app.approval_uses; r app.approval_requests; code text;
BEGIN
  IF current_user NOT IN ('company_api','company_worker') THEN RETURN NEW; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(NEW.workspace_id::text,55));
  SELECT u0.* INTO u FROM app.approval_uses u0 JOIN app.approval_manifests m ON m.id=u0.manifest_id
    JOIN app.approval_requests a ON a.id=m.request_id WHERE u0.activation_policy_id=NEW.id AND a.candidate_version_id=NEW.active_version_id
    AND a.expected_policy_record_version=OLD.record_version AND a.expected_active_version_id IS NOT DISTINCT FROM OLD.active_version_id;
  IF NOT FOUND OR NOT app.authority_founder(u.activation_session_id,true) OR EXISTS(SELECT 1 FROM app.approval_use_results WHERE use_id=u.id) THEN
    RAISE EXCEPTION 'Exact unused policy activation authority required' USING ERRCODE='23514'; END IF;
  IF TG_WHEN='BEFORE' THEN
    code=app.authority_validate(u.manifest_id);
    IF code IS NOT NULL THEN RAISE EXCEPTION '%',code USING ERRCODE='23514'; END IF;
    code=app.authority_temporal(u.manifest_id);
    IF code IS NOT NULL THEN RAISE EXCEPTION '%',code USING ERRCODE='23514'; END IF;
  ELSE
    INSERT INTO app.approval_use_results(id,workspace_id,created_by,use_id,result)
      VALUES(gen_random_uuid(),NEW.workspace_id,app.current_principal_id(),u.id,'consumed');
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER zzzz_policy_activation BEFORE UPDATE ON app.policies FOR EACH ROW WHEN (NEW.active_version_id IS NOT NULL AND NEW.active_version_id IS DISTINCT FROM OLD.active_version_id) EXECUTE FUNCTION app.policy_activation_pointer_guard();
CREATE TRIGGER policy_activation_result AFTER UPDATE ON app.policies FOR EACH ROW WHEN (NEW.active_version_id IS NOT NULL AND NEW.active_version_id IS DISTINCT FROM OLD.active_version_id) EXECUTE FUNCTION app.policy_activation_pointer_guard();
REVOKE ALL ON FUNCTION app.policy_activation_pointer_guard() FROM PUBLIC;

CREATE OR REPLACE FUNCTION app.authority_grant_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
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
        IF NEW.decision='approve' AND r.action='policy.activate' AND app.authority_candidate_current(r.id) IS NOT NULL THEN
          RAISE EXCEPTION 'Stale policy activation candidate' USING ERRCODE='23514'; END IF;
        IF NEW.decision='approve' THEN
          SELECT * INTO v FROM app.policy_versions WHERE id=r.policy_version_id;
          IF NOT EXISTS(SELECT 1 FROM app.policies WHERE id=v.policy_id AND active_version_id=v.id)
            OR v.rules->>'action' IS DISTINCT FROM r.action OR clock_timestamp()>=v.expires_at
            OR r.maximum_uses>(v.rules->>'maximum_uses')::integer
            OR r.maximum_spend>(v.rules->>'maximum_spend')::numeric
            OR r.maximum_volume>(v.rules->>'maximum_volume')::integer
            OR EXTRACT(EPOCH FROM r.expires_at-r.created_at)>(v.rules->>'maximum_expiry_seconds')::integer
            OR (CASE WHEN r.action='policy.activate' THEN 1 ELSE (SELECT count(*) FROM app.approval_targets WHERE request_id=r.id) END) NOT BETWEEN 1 AND (v.rules->>'maximum_targets')::integer THEN
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
CREATE OR REPLACE FUNCTION app.authority_exact_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE r app.approval_requests; cohort jsonb; m app.approval_manifests; i app.runtime_inputs;
    BEGIN
      IF TG_TABLE_NAME='approval_decisions' THEN
        SELECT * INTO r FROM app.approval_requests WHERE id=NEW.request_id;
      ELSIF TG_TABLE_NAME='approval_manifests' THEN
        SELECT * INTO r FROM app.approval_requests WHERE id=NEW.request_id;
      ELSE
        SELECT * INTO m FROM app.approval_manifests WHERE id=NEW.manifest_id;
        SELECT * INTO r FROM app.approval_requests WHERE id=m.request_id;
        SELECT * INTO i FROM app.runtime_inputs WHERE id=NEW.input_id;
        IF i.logical_key NOT LIKE 'authority:'||m.id::text||':%' OR i.scenario IS DISTINCT FROM r.payload->>'scenario' THEN
          RAISE EXCEPTION 'Runtime authority mismatch' USING ERRCODE='23514'; END IF;
      END IF;
      SELECT COALESCE(jsonb_agg(jsonb_build_object('id',target_id::text,'version',expected_version) ORDER BY target_id),'[]'::jsonb) INTO cohort FROM app.approval_targets WHERE request_id=r.id;
      IF r.action='policy.activate' THEN
        cohort=jsonb_build_array(jsonb_build_object('id',r.policy_id::text,'version',r.expected_policy_record_version));
        IF TG_TABLE_NAME='authority_bindings' THEN
          RAISE EXCEPTION 'Policy activation exact scope mismatch' USING ERRCODE='23514'; END IF;
        IF TG_TABLE_NAME='approval_manifests' THEN
          IF NEW.scope->'policy_change' IS DISTINCT FROM r.payload THEN
            RAISE EXCEPTION 'Policy activation exact scope mismatch' USING ERRCODE='23514'; END IF;
        END IF;
      END IF;
      IF r.target_set_hash IS DISTINCT FROM encode(sha256(convert_to(app.authority_canonical(cohort),'UTF8')),'hex')
        OR r.payload_hash IS DISTINCT FROM encode(sha256(convert_to(app.authority_canonical(r.payload),'UTF8')),'hex') THEN
        RAISE EXCEPTION 'Frozen scope hash mismatch' USING ERRCODE='23514'; END IF;
      IF TG_TABLE_NAME='approval_manifests' THEN
        IF NEW.scope->'targets' IS DISTINCT FROM cohort OR NEW.scope->>'workspace_id' IS DISTINCT FROM NEW.workspace_id::text
          OR NEW.scope->>'approver_id' IS DISTINCT FROM NEW.created_by::text OR NEW.scope->>'assurance' IS DISTINCT FROM 'aal2'
          OR (NEW.scope->>'expires_at')::timestamptz IS DISTINCT FROM NEW.expires_at
          OR NEW.manifest_hash IS DISTINCT FROM encode(sha256(convert_to(app.authority_canonical(NEW.scope),'UTF8')),'hex') THEN
          RAISE EXCEPTION 'Manifest hash mismatch' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END $$;
CREATE OR REPLACE FUNCTION app.authority_use_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE code text; r app.approval_requests; b app.authority_bindings; e app.external_effects; n integer; spent numeric; vol bigint;
    BEGIN
      code=app.authority_validate(NEW.manifest_id);
      IF code IS NOT NULL THEN RAISE EXCEPTION '%',code USING ERRCODE='23514'; END IF;
      SELECT r0.* INTO r FROM app.approval_requests r0 JOIN app.approval_manifests m ON m.request_id=r0.id WHERE m.id=NEW.manifest_id;
      IF r.action='policy.activate' THEN
        IF NEW.activation_policy_id IS DISTINCT FROM r.policy_id OR NEW.effect_id IS NOT NULL OR NEW.job_id IS NOT NULL
          OR NEW.spend_reserved<>0 OR NEW.volume<>1 OR NOT app.authority_founder(NEW.activation_session_id,true)
          OR EXISTS(SELECT 1 FROM app.approval_uses WHERE manifest_id=NEW.manifest_id) THEN
          RAISE EXCEPTION 'Invalid or consumed policy activation use' USING ERRCODE='23514'; END IF;
        NEW.use_number=1;
        RETURN NEW;
      END IF;
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
CREATE OR REPLACE FUNCTION app.authority_write_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
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
      ELSIF TG_TABLE_NAME='approval_use_results' THEN
        SELECT * INTO u FROM app.approval_uses WHERE id=NEW.use_id;
        IF u.activation_policy_id IS NOT NULL THEN
          IF NEW.result<>'consumed' OR NOT EXISTS(SELECT 1 FROM app.policies p JOIN app.approval_manifests m ON m.id=u.manifest_id
            JOIN app.approval_requests a ON a.id=m.request_id WHERE p.id=u.activation_policy_id AND p.active_version_id=a.candidate_version_id
            AND p.record_version=a.expected_policy_record_version+1) THEN
            RAISE EXCEPTION 'Unproven activation outcome' USING ERRCODE='23514'; END IF;
          RETURN NEW;
        END IF;
        SELECT * INTO e FROM app.external_effects WHERE id=u.effect_id;
        IF NOT ((NEW.result='consumed' AND e.state='confirmed') OR (NEW.result='released' AND e.state IN ('cancelled','rejected'))) THEN
          RAISE EXCEPTION 'Unproven authority use outcome' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END $$;
CREATE OR REPLACE FUNCTION app.authority_commit_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE governed boolean;
    BEGIN
      IF TG_TABLE_NAME='approval_decisions' THEN
        IF NOT EXISTS(SELECT 1 FROM app.workspaces WHERE id=NEW.workspace_id AND status='active') THEN
          RAISE EXCEPTION 'Workspace not active' USING ERRCODE='23514'; END IF;
        IF NOT EXISTS(SELECT 1 FROM app.approval_requests WHERE id=NEW.request_id
          AND action IN ('runtime.synthetic_external_action','runtime.synthetic_batch_action','policy.activate')) THEN
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
CREATE OR REPLACE FUNCTION app.authority_event_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE r app.approval_requests; expected_type text;
    BEGIN
      SELECT * INTO r FROM app.approval_requests WHERE id=NEW.aggregate_id AND workspace_id=NEW.workspace_id FOR SHARE;
      expected_type=CASE r.state WHEN 'pending' THEN 'approval.requested' WHEN 'approved' THEN 'approval.granted' WHEN 'rejected' THEN 'approval.rejected' WHEN 'revoked' THEN 'approval.revoked' WHEN 'superseded' THEN 'approval.invalidated' WHEN 'expired' THEN 'approval.expired' END;
      IF NEW.event_type='policy.activated' AND r.action='policy.activate' AND EXISTS(
        SELECT 1 FROM app.approval_manifests m JOIN app.approval_uses u ON u.manifest_id=m.id JOIN app.approval_use_results x ON x.use_id=u.id
        JOIN app.policies p ON p.id=u.activation_policy_id WHERE m.request_id=r.id AND x.result='consumed'
        AND p.active_version_id=r.candidate_version_id AND p.record_version=r.expected_policy_record_version+1) THEN
        expected_type='policy.activated'; END IF;
      IF r.id IS NULL OR NEW.schema_version<>2 OR NEW.aggregate_version<>r.record_version OR NEW.actor_id<>NEW.created_by
        OR NEW.event_type IS DISTINCT FROM expected_type OR NEW.payload<>jsonb_build_object('approval_id',r.id::text,'payload_hash',r.payload_hash,'scope_hash',r.scope_hash,'state',r.state) THEN
        RAISE EXCEPTION 'Invalid approval event' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
"""

DOWNGRADE_SQL = r"""

DO $$ BEGIN IF EXISTS(SELECT 1 FROM app.approval_requests WHERE action='policy.activate') THEN
 RAISE EXCEPTION 'Policy activation history exists; preserve evidence and restore matched backup for rollback'; END IF; END $$;
DROP FUNCTION app.policy_activation_pointer_guard() CASCADE;
DROP FUNCTION app.authority_final_clock_guard() CASCADE;
DROP FUNCTION app.authority_validate(uuid);
ALTER FUNCTION app.authority_validate_before_review(uuid) RENAME TO authority_validate;
GRANT EXECUTE ON FUNCTION app.authority_validate(uuid) TO company_api,company_worker;
DROP FUNCTION app.authority_temporal(uuid);
DROP FUNCTION app.authority_candidate_current(uuid);
REVOKE UPDATE ON app.policies FROM company_auth;
REVOKE EXECUTE ON FUNCTION app.authority_canonical(jsonb) FROM company_auth;
ALTER TABLE app.approval_uses DROP CONSTRAINT authority_use_kind, DROP COLUMN activation_policy_id CASCADE,
 DROP COLUMN activation_session_id, ALTER COLUMN effect_id SET NOT NULL, ALTER COLUMN job_id SET NOT NULL;
ALTER TABLE app.approval_requests DROP CONSTRAINT activation_request_shape, DROP COLUMN policy_id CASCADE,
 DROP COLUMN candidate_version_id, DROP COLUMN expected_policy_record_version, DROP COLUMN expected_active_version_id;

CREATE OR REPLACE FUNCTION app.authority_grant_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
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
CREATE OR REPLACE FUNCTION app.authority_exact_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE r app.approval_requests; cohort jsonb; m app.approval_manifests; i app.runtime_inputs;
    BEGIN
      IF TG_TABLE_NAME='approval_decisions' THEN
        SELECT * INTO r FROM app.approval_requests WHERE id=NEW.request_id;
      ELSIF TG_TABLE_NAME='approval_manifests' THEN
        SELECT * INTO r FROM app.approval_requests WHERE id=NEW.request_id;
      ELSE
        SELECT * INTO m FROM app.approval_manifests WHERE id=NEW.manifest_id;
        SELECT * INTO r FROM app.approval_requests WHERE id=m.request_id;
        SELECT * INTO i FROM app.runtime_inputs WHERE id=NEW.input_id;
        IF i.logical_key NOT LIKE 'authority:'||m.id::text||':%' OR i.scenario IS DISTINCT FROM r.payload->>'scenario' THEN
          RAISE EXCEPTION 'Runtime authority mismatch' USING ERRCODE='23514'; END IF;
      END IF;
      SELECT COALESCE(jsonb_agg(jsonb_build_object('id',target_id::text,'version',expected_version) ORDER BY target_id),'[]'::jsonb) INTO cohort FROM app.approval_targets WHERE request_id=r.id;
      IF r.target_set_hash IS DISTINCT FROM encode(sha256(convert_to(app.authority_canonical(cohort),'UTF8')),'hex')
        OR r.payload_hash IS DISTINCT FROM encode(sha256(convert_to(app.authority_canonical(r.payload),'UTF8')),'hex') THEN
        RAISE EXCEPTION 'Frozen scope hash mismatch' USING ERRCODE='23514'; END IF;
      IF TG_TABLE_NAME='approval_manifests' THEN
        IF NEW.scope->'targets' IS DISTINCT FROM cohort OR NEW.scope->>'workspace_id' IS DISTINCT FROM NEW.workspace_id::text
          OR NEW.scope->>'approver_id' IS DISTINCT FROM NEW.created_by::text OR NEW.scope->>'assurance' IS DISTINCT FROM 'aal2'
          OR (NEW.scope->>'expires_at')::timestamptz IS DISTINCT FROM NEW.expires_at
          OR NEW.manifest_hash IS DISTINCT FROM encode(sha256(convert_to(app.authority_canonical(NEW.scope),'UTF8')),'hex') THEN
          RAISE EXCEPTION 'Manifest hash mismatch' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END $$;
CREATE OR REPLACE FUNCTION app.authority_use_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
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
CREATE OR REPLACE FUNCTION app.authority_write_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
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
CREATE OR REPLACE FUNCTION app.authority_commit_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
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
CREATE OR REPLACE FUNCTION app.authority_event_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE r app.approval_requests; expected_type text;
    BEGIN
      SELECT * INTO r FROM app.approval_requests WHERE id=NEW.aggregate_id AND workspace_id=NEW.workspace_id FOR SHARE;
      expected_type=CASE r.state WHEN 'pending' THEN 'approval.requested' WHEN 'approved' THEN 'approval.granted' WHEN 'rejected' THEN 'approval.rejected' WHEN 'revoked' THEN 'approval.revoked' WHEN 'superseded' THEN 'approval.invalidated' WHEN 'expired' THEN 'approval.expired' END;
      IF r.id IS NULL OR NEW.schema_version<>2 OR NEW.aggregate_version<>r.record_version OR NEW.actor_id<>NEW.created_by
        OR NEW.event_type IS DISTINCT FROM expected_type OR NEW.payload<>jsonb_build_object('approval_id',r.id::text,'payload_hash',r.payload_hash,'scope_hash',r.scope_hash,'state',r.state) THEN
        RAISE EXCEPTION 'Invalid approval event' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
