"""Lock and revalidate immutable evaluation dependencies through route activation."""

from alembic import op
from sqlalchemy import text

revision = "0026_phase6b_review_fixes"
down_revision = "0025_ai_evaluation_freshness"
branch_labels = None
depends_on = None

TABLES = (
    "ai_evaluation_batches",
    "ai_evaluations",
    "agent_runs",
    "context_packs",
    "ai_fixture_sources",
    "ai_routes",
    "ai_route_states",
    "ai_registry",
    "ai_provider_connections",
)
LOCK_TABLES = (
    "workspaces",
    "principals",
    "memberships",
    "service_identities",
    "ai_fixture_sources",
    "ai_route_states",
    "ai_provider_connections",
)


def extend(name: str, before: str, after: str) -> None:
    body = (
        op.get_bind()
        .execute(text(f"SELECT pg_get_functiondef('app.{name}()'::regprocedure)"))
        .scalar_one()
    )
    if body.count(before) != 1:
        raise RuntimeError("Unexpected AI guard definition")
    op.execute(body.replace(before, after))


USE_CHECK = """IF NOT app.ai_evaluation_current(e.id) THEN
        RAISE EXCEPTION 'EVALUATION_STALE' USING ERRCODE='23514'; END IF;
      NEW.use_number=1;"""
ACTIVATE_CHECK = """IF NOT app.ai_evaluation_current(NEW.evaluation_id) THEN
          RAISE EXCEPTION 'EVALUATION_STALE' USING ERRCODE='23514'; END IF;
        SELECT * INTO u FROM app.approval_uses"""


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"GRANT SELECT ON app.{table} TO company_auth")
        op.execute(f"""CREATE POLICY ai_freshness_scope ON app.{table} TO company_auth
          USING(workspace_id=app.current_workspace_id()
            AND app.has_active_membership(app.current_principal_id(),workspace_id))""")
    for table in LOCK_TABLES:
        # PostgreSQL requires UPDATE privilege for SELECT FOR SHARE. Only this
        # non-login function owner receives it; no runtime-role grant changes.
        op.execute(f"GRANT UPDATE ON app.{table} TO company_auth")
    op.execute(r"""
    CREATE FUNCTION app.ai_evaluation_inputs(bid uuid)
    RETURNS TABLE(run_id uuid, context_current boolean)
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
    DECLARE b app.ai_evaluation_batches; d app.ai_registry; a app.agent_runs;
      c app.context_packs; s app.ai_fixture_sources; r app.ai_routes;
      ids uuid[]; actors uuid[]; item jsonb; valid boolean; w uuid=app.current_workspace_id();
    BEGIN
      -- Same workspace authority gate as proposal/activation and policy changes.
      PERFORM pg_advisory_xact_lock(hashtextextended(w::text,55));
      IF NOT app.has_active_membership(app.current_principal_id(),w) THEN
        RETURN QUERY SELECT NULL::uuid,false; RETURN; END IF;
      SELECT * INTO b FROM app.ai_evaluation_batches WHERE id=bid;
      SELECT * INTO d FROM app.ai_registry WHERE id=(b.body->>'dataset')::uuid;
      IF b.id IS NULL OR d.kind IS DISTINCT FROM 'dataset'
        OR d.content_hash IS DISTINCT FROM encode(sha256(convert_to(app.authority_canonical(d.body),'UTF8')),'hex')
        OR jsonb_array_length(b.body->'runs'->'candidate') IS DISTINCT FROM jsonb_array_length(d.body->'cases')
        OR jsonb_array_length(b.body->'runs'->'current') IS DISTINCT FROM jsonb_array_length(d.body->'cases')
        OR jsonb_array_length(d.body->'cases')<1 THEN
        RETURN QUERY SELECT NULL::uuid,false; RETURN; END IF;
      SELECT array_agg(value::uuid ORDER BY value::uuid) INTO ids
        FROM jsonb_array_elements_text((b.body->'runs'->'candidate')||(b.body->'runs'->'current'));
      IF cardinality(ids)<>(SELECT count(DISTINCT x) FROM unnest(ids) x)
        OR cardinality(ids)<>(SELECT count(*) FROM app.agent_runs WHERE id=ANY(ids)) THEN
        RETURN QUERY SELECT NULL::uuid,false; RETURN; END IF;
      SELECT array_agg(DISTINCT p ORDER BY p) INTO actors FROM (
        SELECT requester_id p FROM app.context_packs WHERE id IN
          (SELECT context_id FROM app.agent_runs WHERE id=ANY(ids))
        UNION SELECT app.current_principal_id()) actor;
      -- Global identity rows first, then scoped mutable rows in stable UUID order.
      -- Locks last until commit, including the final activation/result triggers.
      PERFORM id FROM app.workspaces WHERE id=w FOR SHARE;
      PERFORM id FROM app.principals WHERE id=ANY(actors) ORDER BY id FOR SHARE;
      PERFORM id FROM app.memberships WHERE workspace_id=w AND principal_id=ANY(actors) ORDER BY id FOR SHARE;
      PERFORM id FROM app.service_identities WHERE principal_id=ANY(actors) ORDER BY id FOR SHARE;
      PERFORM id FROM app.policies WHERE id IN (SELECT policy_id FROM app.policy_versions
        WHERE id IN (SELECT (task->>'policy_version_id')::uuid FROM app.agent_runs WHERE id=ANY(ids))) ORDER BY id FOR SHARE;
      PERFORM id FROM app.ai_route_states WHERE route_id IN
        (SELECT route_id FROM app.agent_runs WHERE id=ANY(ids)) ORDER BY id FOR SHARE;
      PERFORM id FROM app.ai_fixture_sources WHERE id IN (SELECT source_id FROM app.context_packs
        WHERE id IN (SELECT context_id FROM app.agent_runs WHERE id=ANY(ids))) ORDER BY id FOR SHARE;
      PERFORM id FROM app.ai_provider_connections ORDER BY id FOR SHARE;
      FOR item IN SELECT jsonb_build_object('id',v.value,'route',b.body->>label,'scenario',d.body->'cases'->(v.ordinality::integer-1))
        FROM unnest(ARRAY['candidate','current']) label,
          LATERAL jsonb_array_elements_text(b.body->'runs'->label) WITH ORDINALITY v LOOP
        SELECT * INTO a FROM app.agent_runs WHERE id=(item->>'id')::uuid;
        SELECT * INTO c FROM app.context_packs WHERE id=a.context_id;
        SELECT * INTO s FROM app.ai_fixture_sources WHERE id=c.source_id;
        SELECT * INTO r FROM app.ai_routes WHERE id=a.route_id;
        valid= a.evaluation AND a.route_id::text=item->>'route' AND a.scenario=item->>'scenario'
          AND a.task->>'context_pack_id'=c.id::text AND a.task->>'workspace_id'=w::text
          AND c.body->>'id'=c.id::text AND c.body->>'workspace_id'=w::text
          AND c.body->>'policy_version'=a.task->>'policy_version_id'
          AND c.content_hash=c.body->>'content_hash'
          AND c.content_hash=encode(sha256(convert_to(app.authority_canonical(c.body-'content_hash'),'UTF8')),'hex')
          AND EXISTS(SELECT 1 FROM app.workspaces WHERE id=w AND status='active' AND authz_epoch=(c.body->>'authz_epoch')::bigint)
          AND app.has_active_membership(app.current_principal_id(),w)
          AND EXISTS(SELECT 1 FROM app.memberships m JOIN app.principals p ON p.id=m.principal_id
            LEFT JOIN app.service_identities si ON si.principal_id=p.id
            WHERE m.workspace_id=w AND m.principal_id=c.requester_id AND m.status='active'
              AND (m.expires_at IS NULL OR m.expires_at>clock_timestamp()) AND p.status='active'
              AND (p.kind='user' OR si.expires_at>clock_timestamp()))
          AND s.state='approved' AND s.rights_valid AND s.expires_at>clock_timestamp() AND s.observed_at<=clock_timestamp()
          AND c.body->'evidence'->0->'ref'->>'id'=s.evidence_id::text
          AND (c.body->'evidence'->0->'ref'->>'version')::bigint=s.record_version
          AND (c.body->'document_permission_epochs'->>s.document_id::text)::bigint=s.permission_epoch
          AND (c.body->>'expires_at')::timestamptz>clock_timestamp()
          AND EXISTS(SELECT 1 FROM app.policies p JOIN app.policy_versions v ON v.id=p.active_version_id
            WHERE v.id=(a.task->>'policy_version_id')::uuid AND v.effective_at<=clock_timestamp() AND v.expires_at>clock_timestamp())
          AND NOT EXISTS(SELECT 1 FROM app.authority_freezes WHERE action IS NULL OR action='ai.route.promote')
          AND EXISTS(SELECT 1 FROM app.ai_route_states WHERE route_id=r.id AND state IN ('active','draft','evaluated','superseded'))
          AND r.content_hash=encode(sha256(convert_to(app.authority_canonical(r.body),'UTF8')),'hex')
          AND r.prompt_id::text=r.body->>'prompt_version' AND r.schema_id::text=r.body->>'schema_version'
          AND r.price_id::text=r.body->>'price_config_version'
          AND (SELECT count(*) FROM app.ai_registry g WHERE g.id IN (r.prompt_id,r.schema_id,r.price_id)
            AND g.content_hash=encode(sha256(convert_to(app.authority_canonical(g.body),'UTF8')),'hex'))=3
          AND EXISTS(SELECT 1 FROM app.ai_registry WHERE id=r.price_id
            AND body->>'provider'=r.body->>'primary_provider' AND body->>'model_id'=r.body->>'primary_model_id'
            AND (body->>'expires_at')::timestamptz>clock_timestamp())
          AND EXISTS(SELECT 1 FROM app.ai_provider_connections WHERE provider=r.body->>'primary_provider'
            AND status='enabled' AND provider IN ('fake_openai','fake_anthropic'));
        RETURN QUERY SELECT a.id,coalesce(valid,false);
      END LOOP;
    END $$;
    ALTER FUNCTION app.ai_evaluation_inputs(uuid) OWNER TO company_auth;
    REVOKE ALL ON FUNCTION app.ai_evaluation_inputs(uuid) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION app.ai_evaluation_inputs(uuid) TO company_api,company_worker;

    CREATE FUNCTION app.ai_evaluation_current(eid uuid) RETURNS boolean
    LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE e app.ai_evaluations; b app.ai_evaluation_batches; r app.ai_routes; d app.ai_registry; ok boolean;
    BEGIN
      SELECT * INTO e FROM app.ai_evaluations WHERE id=eid;
      SELECT * INTO b FROM app.ai_evaluation_batches WHERE id=e.batch_id;
      SELECT * INTO r FROM app.ai_routes WHERE id=e.route_id;
      SELECT * INTO d FROM app.ai_registry WHERE id=e.dataset_id;
      IF e.id IS NULL OR b.id IS NULL OR r.id IS NULL OR d.id IS NULL
        OR e.route_id::text IS DISTINCT FROM b.body->>'candidate'
        OR e.current_route_id::text IS DISTINCT FROM b.body->>'current'
        OR e.dataset_id::text IS DISTINCT FROM b.body->>'dataset'
        OR e.binding_hash IS DISTINCT FROM encode(sha256(convert_to(app.authority_canonical(
          jsonb_build_object('route',r.content_hash,'dataset',d.content_hash)),'UTF8')),'hex')
        OR e.body->>'decision' IS DISTINCT FROM 'technical_pass'
        OR e.current_result->>'decision' IS DISTINCT FROM 'technical_pass' THEN RETURN false; END IF;
      SELECT bool_and(context_current) INTO ok FROM app.ai_evaluation_inputs(e.batch_id);
      RETURN coalesce(ok,false);
    END $$;
    REVOKE ALL ON FUNCTION app.ai_evaluation_current(uuid) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION app.ai_evaluation_current(uuid),app.authority_canonical(jsonb) TO company_api,company_worker;
    """)
    extend("ai_route_use_guard", "NEW.use_number=1;", USE_CHECK)
    extend("ai_promotion_guard", "SELECT * INTO u FROM app.approval_uses", ACTIVATE_CHECK)
    op.execute("""
    CREATE FUNCTION app.ai_evaluation_commit_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    BEGIN
      IF (TG_TABLE_NAME='ai_route_states' AND NEW.state='active') THEN
        IF NOT app.ai_evaluation_current(NEW.evaluation_id) THEN
          RAISE EXCEPTION 'EVALUATION_STALE' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    REVOKE ALL ON FUNCTION app.ai_evaluation_commit_guard() FROM PUBLIC;
    CREATE CONSTRAINT TRIGGER ai_evaluation_final_clock AFTER UPDATE ON app.ai_route_states
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION app.ai_evaluation_commit_guard();
    """)


def downgrade() -> None:
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM app.ai_evaluations)
      OR EXISTS(SELECT 1 FROM app.approval_uses WHERE activation_route_id IS NOT NULL)
      THEN RAISE EXCEPTION 'Preserve evaluation freshness history: restore matched baseline backup'; END IF; END $$;
      DROP TRIGGER ai_evaluation_final_clock ON app.ai_route_states;
      DROP FUNCTION app.ai_evaluation_commit_guard();""")
    extend("ai_route_use_guard", USE_CHECK, "NEW.use_number=1;")
    extend("ai_promotion_guard", ACTIVATE_CHECK, "SELECT * INTO u FROM app.approval_uses")
    op.execute("DROP FUNCTION app.ai_evaluation_current(uuid),app.ai_evaluation_inputs(uuid)")
    for table in TABLES:
        op.execute(
            f"DROP POLICY ai_freshness_scope ON app.{table}; REVOKE SELECT ON app.{table} FROM company_auth"
        )
    for table in LOCK_TABLES:
        op.execute(f"REVOKE UPDATE ON app.{table} FROM company_auth")
