"""Phase 6B immutable configuration, context and proposal accounting."""

from alembic import op

revision = "0021_ai_gateway"
down_revision = "0020_long_spec_lock"
branch_labels = None
depends_on = None

TABLES = {
    "ai_evaluation_batches": (False, "body jsonb NOT NULL CHECK(octet_length(body::text)<=16384)"),
    "ai_registry": (
        False,
        "kind text NOT NULL CHECK(kind IN ('prompt','schema','price','dataset')), name text NOT NULL, version integer NOT NULL CHECK(version>0), body jsonb NOT NULL CHECK(octet_length(body::text)<=65536), content_hash char(64) NOT NULL, UNIQUE(workspace_id,kind,name,version)",
    ),
    "ai_provider_connections": (
        False,
        "provider text NOT NULL CHECK(provider IN ('fake_openai','fake_anthropic','openai','anthropic')), status text NOT NULL CHECK(status IN ('enabled','unconfigured','disabled','testing','degraded')), environment text NOT NULL CHECK(environment='technical'), credential_ref text, report jsonb NOT NULL, CHECK(provider LIKE 'fake_%' OR status IN ('unconfigured','disabled')), CHECK(credential_ref IS NULL), UNIQUE(workspace_id,provider)",
    ),
    "ai_fixture_sources": (
        True,
        "document_id uuid NOT NULL, evidence_id uuid NOT NULL, state text NOT NULL DEFAULT 'approved' CHECK(state IN ('approved','revoked','retracted','expired')), permission_epoch integer NOT NULL DEFAULT 1 CHECK(permission_epoch>0), rights_valid boolean NOT NULL DEFAULT true, expires_at timestamptz NOT NULL, observed_at timestamptz NOT NULL, excerpt text NOT NULL CHECK(octet_length(excerpt)<=2048), UNIQUE(workspace_id,evidence_id), UNIQUE(workspace_id,document_id)",
    ),
    "ai_routes": (
        False,
        "version integer NOT NULL CHECK(version>0), body jsonb NOT NULL CHECK(octet_length(body::text)<=8192), content_hash char(64) NOT NULL, prompt_id uuid NOT NULL, schema_id uuid NOT NULL, price_id uuid NOT NULL, target_id uuid NOT NULL",
    ),
    "ai_route_states": (
        True,
        "route_id uuid NOT NULL, state text NOT NULL CHECK(state IN ('draft','evaluated','active','superseded','disabled')), evaluation_id uuid, manifest_id uuid, rollback_route_id uuid, activated_at timestamptz, approved_by uuid REFERENCES app.principals(id), UNIQUE(workspace_id,route_id)",
    ),
    "context_packs": (
        False,
        "source_id uuid NOT NULL, body jsonb NOT NULL CHECK(octet_length(body::text)<=32768), content_hash char(64) NOT NULL, requester_id uuid NOT NULL REFERENCES app.principals(id)",
    ),
    "agent_runs": (
        True,
        "evaluation boolean NOT NULL DEFAULT false, job_id uuid NOT NULL, input_id uuid NOT NULL, route_id uuid NOT NULL, context_id uuid NOT NULL, task jsonb NOT NULL CHECK(octet_length(task::text)<=8192), scenario text NOT NULL, state text NOT NULL CHECK(state IN ('queued','running','retry_wait','accepted','refused','incomplete','quarantined','failed','uncertain','cancelled')), result_id uuid, correlation_id uuid NOT NULL, error_code varchar(100), UNIQUE(workspace_id,input_id), UNIQUE(workspace_id,job_id)",
    ),
    "model_runs": (
        True,
        "agent_run_id uuid NOT NULL, reservation_id uuid NOT NULL, ordinal integer NOT NULL CHECK(ordinal BETWEEN 1 AND 2), request_key char(64) NOT NULL, provider text NOT NULL CHECK(provider IN ('fake_openai','fake_anthropic','openai','anthropic')), model_id varchar(100) NOT NULL, prompt_id uuid NOT NULL, price_id uuid NOT NULL, status text NOT NULL CHECK(status IN ('started','completed','failed','refused','incomplete','uncertain')), response_meta jsonb NOT NULL DEFAULT '{}', estimated_usd numeric(20,8) NOT NULL CHECK(estimated_usd>=0), confirmed_usd numeric(20,8), latency_ms numeric, ended_at timestamptz, error_code varchar(100), UNIQUE(workspace_id,agent_run_id,ordinal), UNIQUE(workspace_id,request_key)",
    ),
    "ai_results": (
        False,
        "agent_run_id uuid NOT NULL, body jsonb NOT NULL CHECK(octet_length(body::text)<=16384), UNIQUE(workspace_id,agent_run_id)",
    ),
    "ai_evaluations": (
        False,
        "batch_id uuid NOT NULL, UNIQUE(workspace_id,batch_id), route_id uuid NOT NULL, dataset_id uuid NOT NULL, binding_hash char(64) NOT NULL, body jsonb NOT NULL CHECK(octet_length(body::text)<=65536), current_route_id uuid NOT NULL, current_result jsonb NOT NULL",
    ),
}
REFS = {
    "ai_routes": {
        "prompt_id": "ai_registry",
        "schema_id": "ai_registry",
        "price_id": "ai_registry",
        "target_id": "authority_test_targets",
    },
    "ai_route_states": {
        "route_id": "ai_routes",
        "evaluation_id": "ai_evaluations",
        "manifest_id": "approval_manifests",
        "rollback_route_id": "ai_routes",
    },
    "context_packs": {"source_id": "ai_fixture_sources"},
    "agent_runs": {
        "job_id": "jobs",
        "input_id": "runtime_inputs",
        "route_id": "ai_routes",
        "context_id": "context_packs",
        "result_id": "ai_results",
    },
    "model_runs": {
        "agent_run_id": "agent_runs",
        "reservation_id": "budget_reservations",
        "prompt_id": "ai_registry",
        "price_id": "ai_registry",
    },
    "ai_results": {"agent_run_id": "agent_runs"},
    "ai_evaluations": {
        "batch_id": "ai_evaluation_batches",
        "route_id": "ai_routes",
        "dataset_id": "ai_registry",
        "current_route_id": "ai_routes",
    },
}


def upgrade() -> None:
    for table, (mutable, fields) in TABLES.items():
        extra = (
            ",updated_at timestamptz NOT NULL DEFAULT now(),updated_by uuid NOT NULL REFERENCES app.principals(id),record_version bigint NOT NULL DEFAULT 1"
            if mutable
            else ""
        )
        op.execute(f"""CREATE TABLE app.{table}(id uuid PRIMARY KEY,workspace_id uuid NOT NULL REFERENCES app.workspaces(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),created_by uuid NOT NULL REFERENCES app.principals(id),schema_version smallint NOT NULL DEFAULT 1{extra},{fields},UNIQUE(workspace_id,id));
        ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE app.{table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY ai_scope ON app.{table} TO company_api,company_worker USING(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id)) WITH CHECK(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id));
        CREATE TRIGGER ai_history BEFORE UPDATE OR DELETE ON app.{table} FOR EACH ROW EXECUTE FUNCTION app.core_row_guard('{"mutable" if mutable else "append"}');
        CREATE TRIGGER ai_actor BEFORE INSERT OR UPDATE ON app.{table} FOR EACH ROW EXECUTE FUNCTION app.runtime_actor_guard('{"mutable" if mutable else "append"}');
        GRANT SELECT ON app.{table} TO company_api,company_worker;
        CREATE INDEX {table}_chronology ON app.{table}(workspace_id,created_at,id);
        """)
    for table, refs in REFS.items():
        for column, parent in refs.items():
            op.execute(
                f"ALTER TABLE app.{table} ADD CONSTRAINT {table}_{column}_fk FOREIGN KEY(workspace_id,{column}) REFERENCES app.{parent}(workspace_id,id)"
            )
    op.execute("""
    GRANT INSERT ON app.context_packs,app.agent_runs,app.ai_evaluation_batches,app.ai_fixture_sources TO company_api;
    GRANT INSERT ON app.ai_evaluations TO company_worker;
    GRANT UPDATE ON app.ai_fixture_sources,app.ai_route_states TO company_api;
    GRANT UPDATE ON app.agent_runs TO company_worker;
    GRANT INSERT,UPDATE ON app.model_runs TO company_worker;
    GRANT INSERT ON app.ai_results TO company_worker;
    CREATE UNIQUE INDEX ai_one_active_route ON app.ai_route_states(workspace_id) WHERE state='active';
    CREATE FUNCTION app.ai_identity_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    BEGIN
      IF TG_TABLE_NAME='agent_runs' AND
       (to_jsonb(NEW)-ARRAY['state','result_id','error_code','record_version','updated_at','updated_by']) IS DISTINCT FROM
       (to_jsonb(OLD)-ARRAY['state','result_id','error_code','record_version','updated_at','updated_by']) THEN
       RAISE EXCEPTION 'Immutable AI task' USING ERRCODE='23514'; END IF;
      IF TG_TABLE_NAME='model_runs' AND (OLD.status<>'started' OR NEW.status='started' OR NEW.ended_at IS NULL OR
       (to_jsonb(NEW)-ARRAY['status','response_meta','confirmed_usd','latency_ms','ended_at','error_code','record_version','updated_at','updated_by']) IS DISTINCT FROM
       (to_jsonb(OLD)-ARRAY['status','response_meta','confirmed_usd','latency_ms','ended_at','error_code','record_version','updated_at','updated_by'])) THEN
       RAISE EXCEPTION 'Immutable model call/history' USING ERRCODE='23514'; END IF;
      IF TG_TABLE_NAME='ai_fixture_sources' AND current_user='company_api' AND
       (NEW.state<>'revoked' OR NEW.permission_epoch<>OLD.permission_epoch+1 OR NEW.rights_valid OR
       (to_jsonb(NEW)-ARRAY['state','permission_epoch','rights_valid','record_version','updated_at','updated_by']) IS DISTINCT FROM
       (to_jsonb(OLD)-ARRAY['state','permission_epoch','rights_valid','record_version','updated_at','updated_by'])) THEN
       RAISE EXCEPTION 'Protective revocation only' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER task_identity BEFORE UPDATE ON app.agent_runs FOR EACH ROW EXECUTE FUNCTION app.ai_identity_guard();
    CREATE TRIGGER call_identity BEFORE UPDATE ON app.model_runs FOR EACH ROW EXECUTE FUNCTION app.ai_identity_guard();
    CREATE TRIGGER source_identity BEFORE UPDATE ON app.ai_fixture_sources FOR EACH ROW EXECUTE FUNCTION app.ai_identity_guard();
    REVOKE ALL ON FUNCTION app.ai_identity_guard() FROM PUBLIC;
    ALTER TABLE app.usage_entries DROP CONSTRAINT usage_entries_provider_check,
      DROP CONSTRAINT usage_entries_task_type_check,DROP CONSTRAINT usage_entries_rate_version_check;
    ALTER TABLE app.usage_entries ADD CONSTRAINT usage_entries_provider_check CHECK(provider IN ('fake_local','fake_openai','fake_anthropic','openai','anthropic')),
      ADD CONSTRAINT usage_entries_task_type_check CHECK(task_type IN ('synthetic','gateway_contract')),
      ADD CONSTRAINT usage_entries_rate_version_check CHECK(rate_version='phase-4-fake-v1' OR rate_version LIKE 'ai:%');
    """)


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN IF EXISTS(SELECT 1 FROM app.agent_runs) OR EXISTS(SELECT 1 FROM app.ai_evaluations) THEN RAISE EXCEPTION 'Preserve AI history: restore matched baseline backup'; END IF; END $$;"""
    )
    for table, refs in REFS.items():
        for column in refs:
            op.execute(f"ALTER TABLE app.{table} DROP CONSTRAINT {table}_{column}_fk")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE app.{table}")
    op.execute("""DROP FUNCTION app.ai_identity_guard();
    ALTER TABLE app.usage_entries DROP CONSTRAINT usage_entries_provider_check,DROP CONSTRAINT usage_entries_task_type_check,DROP CONSTRAINT usage_entries_rate_version_check;
    ALTER TABLE app.usage_entries ADD CONSTRAINT usage_entries_provider_check CHECK(provider='fake_local'),ADD CONSTRAINT usage_entries_task_type_check CHECK(task_type='synthetic'),ADD CONSTRAINT usage_entries_rate_version_check CHECK(rate_version='phase-4-fake-v1');""")
