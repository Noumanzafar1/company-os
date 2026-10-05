"""Closed, founder-authorized test routes; no production provider enablement."""

from alembic import op

revision = "0027_phase6b_live_preflight"
down_revision = "0026_phase6b_review_fixes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE app.ai_provider_connections ADD COLUMN connection_version bigint NOT NULL DEFAULT 1;
    DO $$ DECLARE c record; BEGIN
      FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='app.ai_provider_connections'::regclass
        AND contype='c' AND (pg_get_constraintdef(oid) LIKE '%credential_ref%' OR pg_get_constraintdef(oid) LIKE '%fake_%') LOOP
        EXECUTE format('ALTER TABLE app.ai_provider_connections DROP CONSTRAINT %I',c.conname);
      END LOOP;
    END $$;
    ALTER TABLE app.ai_provider_connections ADD CONSTRAINT preflight_connection CHECK(
      (provider IN ('fake_openai','fake_anthropic') AND credential_ref IS NULL)
      OR (provider IN ('openai','anthropic') AND (
        (status IN ('unconfigured','disabled') AND credential_ref IS NULL)
        OR (status='testing' AND credential_ref IS NOT NULL
          AND credential_ref='preflight:'||workspace_id::text||':'||provider))));
    CREATE TABLE app.ai_preflight_gates(
      id uuid PRIMARY KEY,workspace_id uuid NOT NULL REFERENCES app.workspaces(id),
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),created_by uuid NOT NULL REFERENCES app.principals(id),
      schema_version smallint NOT NULL DEFAULT 1,session_id uuid NOT NULL REFERENCES app.auth_sessions(id),
      budget_id uuid NOT NULL,expires_at timestamptz NOT NULL,UNIQUE(workspace_id,id),
      FOREIGN KEY(workspace_id,budget_id) REFERENCES app.budgets(workspace_id,id));
    CREATE TABLE app.ai_preflight_routes(
      id uuid PRIMARY KEY,workspace_id uuid NOT NULL REFERENCES app.workspaces(id),
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),created_by uuid NOT NULL REFERENCES app.principals(id),
      schema_version smallint NOT NULL DEFAULT 1,gate_id uuid NOT NULL,route_id uuid NOT NULL,
      connection_id uuid NOT NULL,connection_version bigint NOT NULL,report jsonb NOT NULL CHECK(octet_length(report::text)<=8192),
      provider text NOT NULL CHECK(provider IN ('openai','anthropic')),UNIQUE(workspace_id,id),
      UNIQUE(workspace_id,gate_id,provider),UNIQUE(workspace_id,route_id),
      FOREIGN KEY(workspace_id,gate_id) REFERENCES app.ai_preflight_gates(workspace_id,id),
      FOREIGN KEY(workspace_id,route_id) REFERENCES app.ai_routes(workspace_id,id),
      FOREIGN KEY(workspace_id,connection_id) REFERENCES app.ai_provider_connections(workspace_id,id));
    ALTER TABLE app.agent_runs ADD COLUMN preflight_id uuid,
      ADD CONSTRAINT preflight_run_fk FOREIGN KEY(workspace_id,preflight_id) REFERENCES app.ai_preflight_routes(workspace_id,id);
    CREATE UNIQUE INDEX one_preflight_task ON app.agent_runs(preflight_id) WHERE preflight_id IS NOT NULL;
    """)
    for table in ("ai_preflight_gates", "ai_preflight_routes"):
        op.execute(f"""
        ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE app.{table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY preflight_scope ON app.{table} TO company_api,company_worker,company_auth
          USING(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id))
          WITH CHECK(workspace_id=app.current_workspace_id() AND created_by=app.current_principal_id() AND app.has_active_membership(app.current_principal_id(),workspace_id));
        GRANT SELECT ON app.{table} TO company_api,company_worker,company_auth;
        GRANT INSERT ON app.{table} TO company_auth;
        CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON app.{table} FOR EACH ROW EXECUTE FUNCTION app.core_row_guard('append');
        """)
    # company_auth already has scoped SELECT/UPDATE on AI configuration for the
    # accepted freshness helper. These new writes are reachable only by closed functions.
    for table, privileges in (("budgets", "SELECT,INSERT"), ("authority_test_targets", "INSERT")):
        op.execute(f"""
        GRANT {privileges} ON app.{table} TO company_auth;
        CREATE POLICY preflight_provision ON app.{table} TO company_auth
          USING(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id))
          WITH CHECK(workspace_id=app.current_workspace_id() AND created_by=app.current_principal_id() AND app.has_active_membership(app.current_principal_id(),workspace_id));
        """)
    op.execute("""
    GRANT INSERT ON app.ai_registry,app.ai_routes,app.ai_route_states TO company_auth;
    GRANT UPDATE ON app.budgets TO company_auth;
    GRANT SELECT ON app.model_runs TO company_auth;
    CREATE POLICY preflight_internal ON app.model_runs TO company_auth USING(
      workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id));
    CREATE FUNCTION app.preflight_connection_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    BEGIN
      IF TG_OP='DELETE' OR current_user<>'company_auth' OR NEW.provider NOT IN ('openai','anthropic')
        OR NEW.status<>'testing' OR NEW.connection_version<>OLD.connection_version+1
        OR (to_jsonb(NEW)-ARRAY['status','credential_ref','report','connection_version']) IS DISTINCT FROM
           (to_jsonb(OLD)-ARRAY['status','credential_ref','report','connection_version']) THEN
        RAISE EXCEPTION 'Closed preflight provisioning only' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    DROP TRIGGER ai_history ON app.ai_provider_connections;
    CREATE TRIGGER ai_history BEFORE UPDATE OR DELETE ON app.ai_provider_connections FOR EACH ROW EXECUTE FUNCTION app.preflight_connection_guard();

    CREATE FUNCTION app.preflight_gate(sid uuid,amount numeric,expiry timestamptz) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
    DECLARE g uuid=gen_random_uuid(); b uuid=gen_random_uuid(); w uuid=app.current_workspace_id(); p uuid=app.current_principal_id();
    BEGIN
      PERFORM pg_advisory_xact_lock(hashtextextended(w::text,55));
      IF NOT app.authority_founder(sid,true) OR amount IS NULL OR amount<=0 OR amount>100
        OR expiry IS NULL OR expiry<=clock_timestamp() OR expiry>clock_timestamp()+interval '1 hour' THEN
        RAISE EXCEPTION 'Founder bounded preflight authorization required' USING ERRCODE='23514'; END IF;
      INSERT INTO app.budgets(id,workspace_id,created_by,updated_by,period_start,period_end,category,limit_usd,status)
        VALUES(b,w,p,p,clock_timestamp(),expiry,'ai_live_preflight',amount,'active');
      INSERT INTO app.ai_preflight_gates(id,workspace_id,created_by,session_id,budget_id,expires_at) VALUES(g,w,p,sid,b,expiry);
      RETURN g;
    END $$;

    CREATE FUNCTION app.preflight_provision(sid uuid,gid uuid,cid uuid,expected bigint,r jsonb,price jsonb,report jsonb) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
    DECLARE w uuid=app.current_workspace_id(); p uuid=app.current_principal_id(); c app.ai_provider_connections;
      g app.ai_preflight_gates; rid uuid=(r->>'route_id')::uuid; pid uuid=(r->>'price_config_version')::uuid;
      target uuid=gen_random_uuid(); link uuid=gen_random_uuid();
    BEGIN
      PERFORM pg_advisory_xact_lock(hashtextextended(w::text,55));
      SELECT * INTO g FROM app.ai_preflight_gates WHERE id=gid;
      SELECT * INTO c FROM app.ai_provider_connections WHERE id=cid FOR UPDATE;
      IF NOT app.authority_founder(sid,true) OR g.id IS NULL OR g.created_by<>p OR g.expires_at<=clock_timestamp()
        OR c.id IS NULL OR c.connection_version IS DISTINCT FROM expected OR c.provider NOT IN ('openai','anthropic')
        OR r->>'selection' IS DISTINCT FROM 'preflight' OR r->>'environment' IS DISTINCT FROM 'technical'
        OR r->>'primary_provider' IS DISTINCT FROM c.provider OR r->>'region_policy' IS DISTINCT FROM 'preflight_required'
        OR r->>'fallback_provider' IS NOT NULL OR r->>'fallback_model_id' IS NOT NULL
        OR report->>'provider' IS DISTINCT FROM c.provider OR report->>'environment' IS DISTINCT FROM 'test'
        OR report->>'model_id' IS DISTINCT FROM r->>'primary_model_id'
        OR report->>'credential_ref' IS DISTINCT FROM 'preflight:'||w::text||':'||c.provider
        OR COALESCE(report->>'credential_binding' !~ '^sha256-v1:[0-9a-f]{64}$',true)
        OR report->>'external_account_id' IS NULL OR report->>'sdk_version' IS NULL
        OR NOT (report @> '{"account_verified": true,"structured_output": true,"billing_verified": true,"retention_approved": true,"region_approved": true,"rates_verified": true}')
        OR COALESCE((report->>'checked_at')::timestamptz>clock_timestamp(),true)
        OR COALESCE((report->>'expires_at')::timestamptz<=clock_timestamp(),true)
        OR COALESCE((report->>'requests_per_minute')::int<=0,true)
        OR COALESCE((report->>'input_token_limit')::int<(r->>'max_input_tokens')::int,true)
        OR COALESCE((report->>'output_token_limit')::int<(r->>'max_output_tokens')::int,true)
        OR price->>'provider' IS DISTINCT FROM c.provider OR price->>'model_id' IS DISTINCT FROM r->>'primary_model_id'
        OR COALESCE((price->>'verified_at')::timestamptz>clock_timestamp(),true)
        OR COALESCE((price->>'expires_at')::timestamptz<=clock_timestamp(),true)
        OR price->>'source' IS NULL
        OR NOT EXISTS(SELECT 1 FROM app.ai_registry WHERE id=(r->>'prompt_version')::uuid AND kind='prompt')
        OR NOT EXISTS(SELECT 1 FROM app.ai_registry WHERE id=(r->>'schema_version')::uuid AND kind='schema') THEN
        RAISE EXCEPTION 'Exact verified test configuration required' USING ERRCODE='23514'; END IF;
      INSERT INTO app.ai_registry(id,workspace_id,created_by,kind,name,version,body,content_hash)
        VALUES(pid,w,p,'price','preflight:'||pid,1,price,repeat('0',64));
      INSERT INTO app.authority_test_targets(id,workspace_id,created_by,updated_by,label)
        VALUES(target,w,p,p,'Synthetic live preflight');
      INSERT INTO app.ai_routes(id,workspace_id,created_by,version,body,content_hash,prompt_id,schema_id,price_id,target_id)
        VALUES(rid,w,p,(r->>'version')::int,r,repeat('0',64),(r->>'prompt_version')::uuid,(r->>'schema_version')::uuid,pid,target);
      INSERT INTO app.ai_route_states(id,workspace_id,created_by,updated_by,route_id,state)
        VALUES(gen_random_uuid(),w,p,p,rid,'draft');
      UPDATE app.ai_provider_connections SET status='testing',credential_ref=preflight_provision.report->>'credential_ref',report=preflight_provision.report,
        connection_version=connection_version+1 WHERE id=cid;
      INSERT INTO app.ai_preflight_routes(id,workspace_id,created_by,gate_id,route_id,connection_id,connection_version,report,provider)
        VALUES(link,w,p,gid,rid,cid,expected+1,report,c.provider);
      RETURN link;
    END $$;
    """)
    # Hashes are supplied separately and validated in application before dispatch;
    # immutable records must have the same canonical Python JSON hash as Gate A.
    op.execute("""
    CREATE FUNCTION app.preflight_hash() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    BEGIN
      IF current_user='company_auth' THEN
        NEW.content_hash=current_setting(CASE WHEN TG_TABLE_NAME='ai_routes' THEN 'app.preflight_route_hash' ELSE 'app.preflight_price_hash' END);
        IF NEW.content_hash !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'Configuration hash required'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER preflight_hash BEFORE INSERT ON app.ai_routes FOR EACH ROW EXECUTE FUNCTION app.preflight_hash();
    CREATE TRIGGER preflight_hash BEFORE INSERT ON app.ai_registry FOR EACH ROW EXECUTE FUNCTION app.preflight_hash();

    CREATE FUNCTION app.preflight_bound_task() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE r app.ai_routes; l app.ai_preflight_routes;
    BEGIN
      SELECT * INTO r FROM app.ai_routes WHERE id=NEW.route_id;
      IF NEW.preflight_id IS NULL THEN
        IF r.body->>'primary_provider' NOT IN ('fake_openai','fake_anthropic') OR COALESCE(NEW.task->>'execution_mode','ordinary')<>'ordinary' THEN
          RAISE EXCEPTION 'Ordinary path is fake only' USING ERRCODE='23514'; END IF;
      ELSE
        SELECT * INTO l FROM app.ai_preflight_routes WHERE id=NEW.preflight_id;
        IF l.id IS NULL OR l.route_id<>NEW.route_id OR current_user<>'company_api'
          OR NOT app.authority_founder(NULLIF(current_setting('app.preflight_session',true),'')::uuid,true)
          OR NEW.task->>'execution_mode' IS DISTINCT FROM 'live_preflight' OR NEW.task->>'sensitivity' IS DISTINCT FROM 'synthetic'
          OR NEW.task->>'max_model_calls' IS DISTINCT FROM '1' OR NEW.scenario<>'success' OR NEW.evaluation
          OR NEW.task->'allowed_tools' IS DISTINCT FROM '[]'::jsonb THEN
          RAISE EXCEPTION 'Closed founder preflight task required' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER preflight_task BEFORE INSERT ON app.agent_runs FOR EACH ROW EXECUTE FUNCTION app.preflight_bound_task();
    CREATE FUNCTION app.preflight_route_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    BEGIN
      IF EXISTS(SELECT 1 FROM app.ai_routes WHERE id=NEW.route_id AND body->>'primary_provider' IN ('openai','anthropic'))
        AND NEW.state NOT IN ('draft','disabled') THEN RAISE EXCEPTION 'Real route cannot be active' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER preflight_route BEFORE INSERT OR UPDATE ON app.ai_route_states FOR EACH ROW EXECUTE FUNCTION app.preflight_route_guard();

    CREATE FUNCTION app.preflight_current(lid uuid) RETURNS boolean LANGUAGE sql VOLATILE SET search_path=pg_catalog,app AS $$
      SELECT EXISTS(SELECT 1 FROM app.ai_preflight_routes l JOIN app.ai_preflight_gates g ON g.id=l.gate_id
        JOIN app.budgets b ON b.id=g.budget_id JOIN app.ai_provider_connections c ON c.id=l.connection_id
        JOIN app.ai_route_states s ON s.route_id=l.route_id
        JOIN app.ai_routes r ON r.id=l.route_id JOIN app.ai_registry price ON price.id=r.price_id
        WHERE l.id=lid AND g.expires_at>clock_timestamp() AND app.authority_member(g.created_by,true)
        AND b.status='active' AND b.period_start<=clock_timestamp() AND b.period_end>clock_timestamp()
        AND s.state='draft' AND c.status='testing' AND c.connection_version=l.connection_version
        AND c.report=l.report AND c.credential_ref=l.report->>'credential_ref'
        AND (price.body->>'verified_at')::timestamptz<=clock_timestamp() AND (price.body->>'expires_at')::timestamptz>clock_timestamp()
        AND (l.report->>'checked_at')::timestamptz<=clock_timestamp() AND (l.report->>'expires_at')::timestamptz>clock_timestamp());
    $$;
    DO $$ DECLARE body text; BEGIN
      body=pg_get_functiondef('app.ai_call_binding()'::regprocedure);
      IF position('OR NEW.provider NOT IN (''fake_openai'',''fake_anthropic'')' IN body)=0 THEN RAISE EXCEPTION 'Unexpected call guard'; END IF;
      body=replace(body,'OR NEW.provider NOT IN (''fake_openai'',''fake_anthropic'')',
        'OR (a.preflight_id IS NULL AND NEW.provider NOT IN (''fake_openai'',''fake_anthropic''))');
      EXECUTE body;
    END $$;
    CREATE FUNCTION app.preflight_call_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE a app.agent_runs; l app.ai_preflight_routes; g app.ai_preflight_gates;
    BEGIN
      SELECT * INTO a FROM app.agent_runs WHERE id=NEW.agent_run_id;
      IF a.preflight_id IS NOT NULL THEN
        SELECT * INTO l FROM app.ai_preflight_routes WHERE id=a.preflight_id;
        SELECT * INTO g FROM app.ai_preflight_gates WHERE id=l.gate_id;
        PERFORM pg_advisory_xact_lock(410053);
        IF NOT app.preflight_current(l.id) OR NEW.provider IS DISTINCT FROM l.provider OR NEW.ordinal<>1
          OR EXISTS(SELECT 1 FROM app.model_runs WHERE agent_run_id=a.id)
          OR NOT EXISTS(SELECT 1 FROM app.budget_reservations WHERE id=NEW.reservation_id AND budget_id=g.budget_id
            AND maximum_usd=NEW.estimated_usd AND state='reserved') THEN
          RAISE EXCEPTION 'One reserved current preflight call required' USING ERRCODE='23514'; END IF;
      ELSIF EXISTS(SELECT 1 FROM app.budget_reservations r JOIN app.budgets b ON b.id=r.budget_id
        WHERE r.id=NEW.reservation_id AND b.category='ai_live_preflight') THEN
        RAISE EXCEPTION 'Fake spend cannot consume live budget' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER preflight_call BEFORE INSERT ON app.model_runs FOR EACH ROW EXECUTE FUNCTION app.preflight_call_guard();
    CREATE FUNCTION app.preflight_budget_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    BEGIN
      IF OLD.category='ai_live_preflight' AND
        (NEW.limit_usd,NEW.period_start,NEW.period_end,NEW.category,NEW.workspace_id) IS DISTINCT FROM
        (OLD.limit_usd,OLD.period_start,OLD.period_end,OLD.category,OLD.workspace_id) THEN
        RAISE EXCEPTION 'Immutable live preflight ceiling' USING ERRCODE='23514'; END IF;
      IF OLD.category<>'ai_live_preflight' AND NEW.category='ai_live_preflight' THEN
        RAISE EXCEPTION 'Founder provisioning required' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER preflight_budget BEFORE UPDATE ON app.budgets FOR EACH ROW EXECUTE FUNCTION app.preflight_budget_guard();
    CREATE FUNCTION app.preflight_exposure_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE bid uuid; b app.budgets; reserved numeric; spent numeric;
    BEGIN
      bid=CASE WHEN TG_TABLE_NAME='budgets' THEN NEW.id ELSE (to_jsonb(NEW)->>'budget_id')::uuid END;
      SELECT * INTO b FROM app.budgets WHERE id=bid FOR UPDATE;
      IF b.category='ai_live_preflight' THEN
        SELECT COALESCE(sum(maximum_usd) FILTER(WHERE state IN ('reserved','uncertain')),0),
          COALESCE(sum(actual_usd) FILTER(WHERE state IN ('settled','released')),0)
          INTO reserved,spent FROM app.budget_reservations WHERE budget_id=bid;
        IF b.reserved_usd<>reserved OR b.spent_usd<>spent OR reserved+spent>b.limit_usd
          OR NOT EXISTS(SELECT 1 FROM app.ai_preflight_gates WHERE budget_id=bid)
          OR EXISTS(SELECT 1 FROM app.budget_reservations br WHERE br.budget_id=bid AND NOT EXISTS(
            SELECT 1 FROM app.model_runs m JOIN app.agent_runs a ON a.id=m.agent_run_id
            JOIN app.ai_preflight_routes l ON l.id=a.preflight_id JOIN app.ai_preflight_gates g ON g.id=l.gate_id
            WHERE m.reservation_id=br.id AND g.budget_id=bid AND m.provider=l.provider AND m.ordinal=1)) THEN
          RAISE EXCEPTION 'Exact durable preflight exposure required' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NULL;
    END $$;
    CREATE CONSTRAINT TRIGGER preflight_exposure AFTER INSERT OR UPDATE ON app.budgets
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION app.preflight_exposure_guard();
    CREATE CONSTRAINT TRIGGER preflight_exposure AFTER INSERT OR UPDATE ON app.budget_reservations
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION app.preflight_exposure_guard();
    ALTER FUNCTION app.preflight_gate(uuid,numeric,timestamptz) OWNER TO company_auth;
    ALTER FUNCTION app.preflight_provision(uuid,uuid,uuid,bigint,jsonb,jsonb,jsonb) OWNER TO company_auth;
    REVOKE ALL ON FUNCTION app.preflight_gate(uuid,numeric,timestamptz),app.preflight_provision(uuid,uuid,uuid,bigint,jsonb,jsonb,jsonb),
      app.preflight_connection_guard(),app.preflight_hash(),app.preflight_bound_task(),app.preflight_route_guard(),app.preflight_current(uuid),app.preflight_call_guard(),app.preflight_budget_guard(),app.preflight_exposure_guard() FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION app.preflight_gate(uuid,numeric,timestamptz),app.preflight_provision(uuid,uuid,uuid,bigint,jsonb,jsonb,jsonb) TO company_api;
    GRANT EXECUTE ON FUNCTION app.preflight_current(uuid) TO company_api,company_worker;
    """)


def downgrade() -> None:
    op.execute("""
    DO $$ BEGIN IF EXISTS(SELECT 1 FROM app.ai_preflight_gates) OR EXISTS(SELECT 1 FROM app.ai_provider_connections WHERE status='testing') THEN
      RAISE EXCEPTION 'Preserve preflight authorization/history; restore matched backup'; END IF; END $$;
    DROP TRIGGER preflight_call ON app.model_runs;
    DROP TRIGGER preflight_budget ON app.budgets;
    DROP TRIGGER preflight_exposure ON app.budgets;
    DROP TRIGGER preflight_exposure ON app.budget_reservations;
    DROP FUNCTION app.preflight_exposure_guard();
    DROP FUNCTION app.preflight_budget_guard();
    DROP TRIGGER preflight_task ON app.agent_runs;
    DROP TRIGGER preflight_route ON app.ai_route_states;
    DROP TRIGGER preflight_hash ON app.ai_routes;
    DROP TRIGGER preflight_hash ON app.ai_registry;
    DROP FUNCTION app.preflight_call_guard(),app.preflight_bound_task(),app.preflight_route_guard(),app.preflight_hash(),app.preflight_current(uuid);
    DROP FUNCTION app.preflight_provision(uuid,uuid,uuid,bigint,jsonb,jsonb,jsonb),app.preflight_gate(uuid,numeric,timestamptz);
    DO $$ DECLARE body text; BEGIN
      body=pg_get_functiondef('app.ai_call_binding()'::regprocedure);
      EXECUTE replace(body,'OR (a.preflight_id IS NULL AND NEW.provider NOT IN (''fake_openai'',''fake_anthropic''))',
        'OR NEW.provider NOT IN (''fake_openai'',''fake_anthropic'')');
    END $$;
    ALTER TABLE app.agent_runs DROP COLUMN preflight_id;
    DROP TABLE app.ai_preflight_routes,app.ai_preflight_gates;
    DROP TRIGGER ai_history ON app.ai_provider_connections;
    DROP FUNCTION app.preflight_connection_guard();
    CREATE TRIGGER ai_history BEFORE UPDATE OR DELETE ON app.ai_provider_connections FOR EACH ROW EXECUTE FUNCTION app.core_row_guard('append');
    ALTER TABLE app.ai_provider_connections DROP CONSTRAINT preflight_connection,DROP COLUMN connection_version,
      ADD CHECK(provider IN ('fake_openai','fake_anthropic','openai','anthropic')),
      ADD CHECK(provider LIKE 'fake_%' OR status IN ('unconfigured','disabled')),ADD CHECK(credential_ref IS NULL);
    REVOKE INSERT ON app.ai_registry,app.ai_routes,app.ai_route_states FROM company_auth;
    REVOKE UPDATE ON app.budgets FROM company_auth;
    DROP POLICY preflight_internal ON app.model_runs;
    REVOKE SELECT ON app.model_runs FROM company_auth;
    """)
    # 0014 already granted SELECT/UPDATE on authority_test_targets. Preserve both.
    for table, privileges in (("budgets", "SELECT,INSERT"), ("authority_test_targets", "INSERT")):
        op.execute(
            f"DROP POLICY preflight_provision ON app.{table}; REVOKE {privileges} ON app.{table} FROM company_auth"
        )
