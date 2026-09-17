CREATE SCHEMA app;
GRANT SELECT ON public.alembic_version TO company_api,company_worker;
REVOKE ALL ON SCHEMA app FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA app TO company_api, company_worker, company_auth;
ALTER DEFAULT PRIVILEGES IN SCHEMA app REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

CREATE TABLE app.principals (
 id uuid PRIMARY KEY, kind text NOT NULL CHECK (kind IN ('user','service')),
 status text NOT NULL CHECK (status IN ('active','disabled')),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 record_version bigint NOT NULL DEFAULT 1 CHECK(record_version > 0),
 schema_version smallint NOT NULL DEFAULT 1 CHECK(schema_version > 0),
 created_by uuid NOT NULL REFERENCES app.principals(id) DEFERRABLE INITIALLY DEFERRED,
 updated_by uuid NOT NULL REFERENCES app.principals(id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE app.users (
 id uuid PRIMARY KEY, principal_id uuid NOT NULL UNIQUE REFERENCES app.principals(id),
 auth_subject varchar(500) NOT NULL UNIQUE, display_name varchar(500) NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 record_version bigint NOT NULL DEFAULT 1 CHECK(record_version > 0),
 schema_version smallint NOT NULL DEFAULT 1 CHECK(schema_version > 0),
 created_by uuid NOT NULL REFERENCES app.principals(id), updated_by uuid NOT NULL REFERENCES app.principals(id)
);
CREATE TABLE app.service_identities (
 id uuid PRIMARY KEY, principal_id uuid NOT NULL UNIQUE REFERENCES app.principals(id),
 name varchar(500) NOT NULL UNIQUE, token_key_ref varchar(500) NOT NULL,
 expires_at timestamptz NOT NULL, capability_profile varchar(500) NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 record_version bigint NOT NULL DEFAULT 1 CHECK(record_version > 0),
 schema_version smallint NOT NULL DEFAULT 1 CHECK(schema_version > 0),
 created_by uuid NOT NULL REFERENCES app.principals(id), updated_by uuid NOT NULL REFERENCES app.principals(id)
);
CREATE INDEX service_expiry ON app.service_identities(expires_at);
CREATE TABLE app.roles (
 id uuid PRIMARY KEY, name varchar(100) NOT NULL UNIQUE,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 record_version bigint NOT NULL DEFAULT 1 CHECK(record_version > 0), schema_version smallint NOT NULL DEFAULT 1 CHECK(schema_version > 0),
 created_by uuid NOT NULL REFERENCES app.principals(id), updated_by uuid NOT NULL REFERENCES app.principals(id)
);
CREATE TABLE app.role_permissions (
 id uuid PRIMARY KEY, role_id uuid NOT NULL REFERENCES app.roles(id),
 permission varchar(100) NOT NULL CHECK(permission IN ('workspace.read','system.read','approval.grant')),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 record_version bigint NOT NULL DEFAULT 1 CHECK(record_version > 0), schema_version smallint NOT NULL DEFAULT 1 CHECK(schema_version > 0),
 created_by uuid NOT NULL REFERENCES app.principals(id), updated_by uuid NOT NULL REFERENCES app.principals(id),
 UNIQUE(role_id,permission)
);
CREATE TABLE app.workspaces (
 id uuid PRIMARY KEY, name varchar(500) NOT NULL UNIQUE,
 kind text NOT NULL CHECK(kind IN ('acquisition','client_delivery','partners')),
 status text NOT NULL CHECK(status IN ('active','paused','closing','closed')),
 timezone varchar(100) NOT NULL, authz_epoch bigint NOT NULL DEFAULT 1 CHECK(authz_epoch > 0),
 retention_profile jsonb NOT NULL, region_policy jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 record_version bigint NOT NULL DEFAULT 1 CHECK(record_version > 0), schema_version smallint NOT NULL DEFAULT 1 CHECK(schema_version > 0),
 created_by uuid NOT NULL REFERENCES app.principals(id), updated_by uuid NOT NULL REFERENCES app.principals(id),
 CHECK(jsonb_typeof(retention_profile) = 'object'), CHECK(jsonb_typeof(region_policy) = 'object')
);
CREATE INDEX workspace_status ON app.workspaces(status);
CREATE TABLE app.memberships (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES app.workspaces(id),
 principal_id uuid NOT NULL REFERENCES app.principals(id), role_id uuid NOT NULL REFERENCES app.roles(id),
 status text NOT NULL CHECK(status IN ('active','revoked')), expires_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 record_version bigint NOT NULL DEFAULT 1 CHECK(record_version > 0), schema_version smallint NOT NULL DEFAULT 1 CHECK(schema_version > 0),
 created_by uuid NOT NULL REFERENCES app.principals(id), updated_by uuid NOT NULL REFERENCES app.principals(id),
 UNIQUE(workspace_id,id), UNIQUE(workspace_id,principal_id,role_id)
);
CREATE INDEX membership_principal ON app.memberships(principal_id);
CREATE INDEX membership_role ON app.memberships(role_id);
CREATE INDEX membership_updated ON app.memberships(workspace_id,updated_at,id);

-- Opaque server session hashes only; raw tokens never persist in PostgreSQL.
CREATE TABLE app.auth_sessions (
 id uuid PRIMARY KEY, principal_id uuid NOT NULL REFERENCES app.principals(id),
 token_hash char(64) NOT NULL UNIQUE, csrf_hash char(64) NOT NULL,
 assurance text NOT NULL CHECK(assurance IN ('aal1','aal2')), mfa_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(), last_seen_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL, revoked_at timestamptz, schema_version smallint NOT NULL DEFAULT 1,
 CHECK(expires_at > created_at AND expires_at <= created_at + interval '12 hours')
);
CREATE INDEX session_principal ON app.auth_sessions(principal_id);
CREATE INDEX session_expiry ON app.auth_sessions(expires_at);
CREATE TABLE app.audit_entries (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES app.workspaces(id),
 created_at timestamptz NOT NULL DEFAULT now(), schema_version smallint NOT NULL DEFAULT 1,
 created_by uuid NOT NULL REFERENCES app.principals(id), occurred_at timestamptz NOT NULL DEFAULT now(),
 actor_id uuid NOT NULL REFERENCES app.principals(id), actor_type text NOT NULL CHECK(actor_type IN ('user','service')),
 action_type varchar(100) NOT NULL, target_type varchar(100) NOT NULL, target_id uuid NOT NULL,
 request_id uuid NOT NULL, correlation_id uuid NOT NULL, command_id uuid NOT NULL,
 decision text NOT NULL CHECK(decision IN ('allow','deny','require_approval','quarantine')),
 outcome varchar(100) NOT NULL, change_summary varchar(500) NOT NULL,
 payload_hash char(64) NOT NULL, policy_version varchar(100) NOT NULL,
 UNIQUE(workspace_id,id)
);
CREATE INDEX audit_created ON app.audit_entries(workspace_id,created_at,id);

-- Every table has FORCE RLS, including global identity/session directories.
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['principals','users','service_identities','roles','role_permissions','workspaces','memberships','auth_sessions','audit_entries'] LOOP
  EXECUTE format('ALTER TABLE app.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE app.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY identity_guard ON app.%I TO company_auth USING (true) WITH CHECK (true)',t);
 END LOOP;
END $$;
GRANT SELECT ON app.principals, app.users, app.service_identities, app.roles, app.role_permissions, app.workspaces, app.memberships TO company_auth;
GRANT SELECT,INSERT,UPDATE ON app.auth_sessions TO company_auth;
GRANT INSERT ON app.audit_entries TO company_auth;

CREATE FUNCTION app.current_principal_id() RETURNS uuid LANGUAGE sql STABLE
RETURN nullif(current_setting('app.principal_id',true),'')::uuid;
CREATE FUNCTION app.current_workspace_id() RETURNS uuid LANGUAGE sql STABLE
RETURN nullif(current_setting('app.workspace_id',true),'')::uuid;

CREATE FUNCTION app.has_active_membership(p uuid, w uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, app AS $$
 SELECT p = app.current_principal_id() AND EXISTS (
 SELECT 1 FROM app.memberships m JOIN app.principals pr ON pr.id=m.principal_id
 JOIN app.workspaces ws ON ws.id=m.workspace_id
 LEFT JOIN app.service_identities si ON si.principal_id=pr.id
 WHERE m.principal_id=p AND m.workspace_id=w AND m.status='active'
 AND (m.expires_at IS NULL OR m.expires_at > now()) AND pr.status='active'
 AND (pr.kind='user' OR si.expires_at > now()) AND ws.status IN ('active','paused')
 AND ws.authz_epoch=nullif(current_setting('app.authz_epoch',true),'')::bigint)
$$;
ALTER FUNCTION app.has_active_membership(uuid,uuid) OWNER TO company_auth;

CREATE POLICY workspace_scope ON app.workspaces TO company_api,company_worker
 USING(id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),id));
CREATE POLICY membership_scope ON app.memberships TO company_api,company_worker
 USING(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id));
CREATE POLICY audit_scope ON app.audit_entries TO company_api,company_worker
 USING(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id))
 WITH CHECK(workspace_id=app.current_workspace_id() AND actor_id=app.current_principal_id()
 AND created_by=app.current_principal_id() AND app.has_active_membership(app.current_principal_id(),workspace_id));
GRANT SELECT ON app.workspaces,app.memberships,app.audit_entries TO company_api;
GRANT INSERT ON app.audit_entries TO company_api;
-- Worker intentionally has no business table grants in Phase 2.

CREATE FUNCTION app.profile() RETURNS TABLE(principal_id uuid,display_name text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT p.id,u.display_name::text FROM app.principals p JOIN app.users u ON u.principal_id=p.id
 WHERE p.id=app.current_principal_id() AND p.status='active'
$$;
CREATE FUNCTION app.authorized_workspaces() RETURNS TABLE(id uuid,name text,kind text,authz_epoch bigint,record_version bigint,roles text[],permissions text[])
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 SELECT w.id,w.name::text,w.kind,w.authz_epoch,w.record_version,
 array_agg(DISTINCT r.name::text),array_agg(DISTINCT rp.permission::text)
 FROM app.workspaces w JOIN app.memberships m ON m.workspace_id=w.id
 JOIN app.principals p ON p.id=m.principal_id JOIN app.roles r ON r.id=m.role_id
 JOIN app.role_permissions rp ON rp.role_id=r.id
 WHERE m.principal_id=app.current_principal_id() AND p.status='active' AND p.kind='user'
 AND m.status='active' AND (m.expires_at IS NULL OR m.expires_at>now())
 AND w.status IN ('active','paused')
 GROUP BY w.id ORDER BY w.name,w.id
$$;
CREATE FUNCTION app.open_session(subject text, session_id uuid, session_hash text, csrf text, aal text, mfa timestamptz)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE p uuid;
BEGIN
 SELECT pr.id INTO p FROM app.users u JOIN app.principals pr ON pr.id=u.principal_id
 WHERE u.auth_subject=subject AND pr.status='active' AND pr.kind='user';
 IF p IS NULL THEN RETURN NULL; END IF;
 INSERT INTO app.auth_sessions(id,principal_id,token_hash,csrf_hash,assurance,mfa_at,expires_at)
 VALUES(session_id,p,session_hash,csrf,aal,mfa,now()+interval '12 hours');
 RETURN p;
END $$;
CREATE FUNCTION app.resolve_session(session_hash text)
RETURNS TABLE(principal_id uuid,session_id uuid,assurance text,mfa_at timestamptz,csrf_hash text)
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
 UPDATE app.auth_sessions s SET last_seen_at=now() FROM app.principals p
 WHERE s.token_hash=session_hash AND p.id=s.principal_id AND p.status='active'
 AND p.kind='user' AND s.revoked_at IS NULL AND s.expires_at>now()
 AND s.last_seen_at>now()-interval '30 minutes'
 RETURNING s.principal_id,s.id,s.assurance,s.mfa_at,s.csrf_hash::text
$$;
CREATE FUNCTION app.close_session(session_hash text, csrf text, rid uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,app AS $$
DECLARE p uuid; sid uuid;
BEGIN
 UPDATE app.auth_sessions SET revoked_at=now()
 WHERE token_hash=session_hash AND csrf_hash=csrf AND revoked_at IS NULL
 RETURNING principal_id,id INTO p,sid;
 IF p IS NOT NULL THEN
  INSERT INTO app.audit_entries(id,workspace_id,created_by,actor_id,actor_type,action_type,target_type,target_id,
    request_id,correlation_id,command_id,decision,outcome,change_summary,payload_hash,policy_version)
  SELECT gen_random_uuid(),workspace_id,p,p,'user','auth.logout','auth_session',sid,
    rid,rid,rid,'allow','revoked','Session ended',repeat('0',64),'phase-2'
  FROM app.memberships WHERE principal_id=p AND status='active' GROUP BY workspace_id;
 END IF;
END $$;

ALTER FUNCTION app.profile() OWNER TO company_auth;
ALTER FUNCTION app.authorized_workspaces() OWNER TO company_auth;
ALTER FUNCTION app.open_session(text,uuid,text,text,text,timestamptz) OWNER TO company_auth;
ALTER FUNCTION app.resolve_session(text) OWNER TO company_auth;
ALTER FUNCTION app.close_session(text,text,uuid) OWNER TO company_auth;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.current_principal_id(),app.current_workspace_id(),app.has_active_membership(uuid,uuid) TO company_api,company_worker,company_auth;
GRANT EXECUTE ON FUNCTION app.profile(),app.authorized_workspaces(),app.open_session(text,uuid,text,text,text,timestamptz),app.resolve_session(text),app.close_session(text,text,uuid) TO company_api;

CREATE FUNCTION app.check_principal_subtype() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
DECLARE pid uuid; k text; u integer; s integer;
BEGIN
 IF TG_TABLE_NAME='principals' THEN pid=NEW.id; ELSE pid=COALESCE(NEW.principal_id,OLD.principal_id); END IF;
 SELECT kind INTO k FROM app.principals WHERE id=pid;
 SELECT count(*) INTO u FROM app.users WHERE principal_id=pid;
 SELECT count(*) INTO s FROM app.service_identities WHERE principal_id=pid;
 IF k IS NOT NULL AND NOT ((k='user' AND u=1 AND s=0) OR (k='service' AND s=1 AND u=0)) THEN
  RAISE EXCEPTION 'Principal subtype invariant' USING ERRCODE='23514';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER principal_subtype AFTER INSERT OR UPDATE ON app.principals DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION app.check_principal_subtype();
CREATE CONSTRAINT TRIGGER user_subtype AFTER INSERT OR UPDATE OR DELETE ON app.users DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION app.check_principal_subtype();
CREATE CONSTRAINT TRIGGER service_subtype AFTER INSERT OR UPDATE OR DELETE ON app.service_identities DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION app.check_principal_subtype();

CREATE FUNCTION app.version_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.id<>OLD.id OR NEW.created_by<>OLD.created_by OR NEW.created_at<>OLD.created_at THEN
  RAISE EXCEPTION 'Immutable identity' USING ERRCODE='23514';
 END IF;
 IF TG_TABLE_NAME='memberships' AND NEW.workspace_id<>OLD.workspace_id THEN
  RAISE EXCEPTION 'Immutable workspace' USING ERRCODE='23514';
 END IF;
 IF TG_TABLE_NAME IN ('users','service_identities') AND NEW.principal_id<>OLD.principal_id THEN
  RAISE EXCEPTION 'Immutable principal subtype' USING ERRCODE='23514';
 END IF;
 IF NEW.record_version<>OLD.record_version+1 THEN
  RAISE EXCEPTION 'Expected next record version' USING ERRCODE='40001';
 END IF;
 NEW.updated_at=clock_timestamp(); RETURN NEW;
END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['principals','users','service_identities','roles','role_permissions','workspaces','memberships'] LOOP
  EXECUTE format('CREATE TRIGGER version_update BEFORE UPDATE ON app.%I FOR EACH ROW EXECUTE FUNCTION app.version_update()',t);
 END LOOP;
END $$;
