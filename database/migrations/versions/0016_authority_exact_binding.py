"""Verify exact cohort, canonical manifest hash and immutable runtime binding in SQL."""

from alembic import op

revision = "0016_authority_exact_binding"
down_revision = "0015_authority_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE FUNCTION app.authority_canonical(v jsonb) RETURNS text LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,app AS $$
    DECLARE result text;
    BEGIN
      CASE jsonb_typeof(v)
      WHEN 'object' THEN SELECT '{'||COALESCE(string_agg(to_jsonb(key)::text||':'||app.authority_canonical(value),',' ORDER BY key COLLATE "C"),'')||'}' INTO result FROM jsonb_each(v);
      WHEN 'array' THEN SELECT '['||COALESCE(string_agg(app.authority_canonical(value),',' ORDER BY ordinal),'')||']' INTO result FROM jsonb_array_elements(v) WITH ORDINALITY a(value,ordinal);
      ELSE result=v::text;
      END CASE;
      RETURN result;
    END $$;
    CREATE FUNCTION app.authority_exact_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
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
    CREATE TRIGGER exact_decision_scope BEFORE INSERT ON app.approval_decisions FOR EACH ROW WHEN (NEW.decision='approve') EXECUTE FUNCTION app.authority_exact_guard();
    CREATE TRIGGER exact_manifest_scope BEFORE INSERT ON app.approval_manifests FOR EACH ROW EXECUTE FUNCTION app.authority_exact_guard();
    CREATE TRIGGER exact_runtime_binding BEFORE INSERT ON app.authority_bindings FOR EACH ROW EXECUTE FUNCTION app.authority_exact_guard();
    REVOKE ALL ON FUNCTION app.authority_canonical(jsonb),app.authority_exact_guard() FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION app.authority_canonical(jsonb) TO company_api,company_worker;
    """)


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION app.authority_exact_guard() CASCADE; DROP FUNCTION app.authority_canonical(jsonb)"
    )
