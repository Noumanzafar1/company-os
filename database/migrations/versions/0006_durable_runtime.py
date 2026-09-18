"""Phase 4 durable synthetic runtime. Frozen migration-local schema."""

from alembic import op

revision = "0006_durable_runtime"
down_revision = "0005_phase3_review_fixes"
branch_labels = None
depends_on = None

TABLES = {
    "fake_endpoints": (
        False,
        "adapter text NOT NULL CHECK(adapter='fake_local_v1'), name varchar(100) NOT NULL, enabled boolean NOT NULL, UNIQUE(workspace_id,name)",
    ),
    "runtime_inputs": (
        True,
        "scenario text NOT NULL CHECK(scenario IN ('success','transient','invalid','exhausted','wait','effect_success','effect_rejected','effect_lost','effect_unknown','safety','reconcile')), logical_key varchar(200) NOT NULL, content_hash char(64) NOT NULL, UNIQUE(workspace_id,logical_key)",
    ),
    "workflow_runs": (
        False,
        "type text NOT NULL CHECK(type='synthetic'), version integer NOT NULL CHECK(version=1), subject_id uuid NOT NULL, state text NOT NULL CHECK(state IN ('running','waiting','succeeded','failed','cancelled')), deadline_at timestamptz, correlation_id uuid NOT NULL",
    ),
    "events": (
        True,
        "event_type varchar(100) NOT NULL, aggregate_type varchar(100) NOT NULL, aggregate_id uuid NOT NULL, aggregate_version bigint NOT NULL CHECK(aggregate_version>0), occurred_at timestamptz NOT NULL DEFAULT now(), received_at timestamptz NOT NULL DEFAULT now(), actor_type text NOT NULL CHECK(actor_type IN ('user','service')), actor_id uuid NOT NULL REFERENCES app.principals(id), causation_id uuid, correlation_id uuid NOT NULL, origin text NOT NULL CHECK(origin IN ('company_os','fake_local')), classification text NOT NULL CHECK(classification='internal'), payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='object' AND octet_length(payload::text)<=16384), payload_ref uuid, trace_id varchar(100) NOT NULL, UNIQUE(workspace_id,aggregate_type,aggregate_id,aggregate_version,event_type)",
    ),
    "outbox": (
        False,
        "event_id uuid NOT NULL, available_at timestamptz NOT NULL DEFAULT now(), attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0), dispatched_at timestamptz, UNIQUE(workspace_id,event_id)",
    ),
    "consumer_receipts": (
        True,
        "event_id uuid NOT NULL, consumer_name varchar(100) NOT NULL, consumer_version integer NOT NULL CHECK(consumer_version>0), replay_namespace varchar(100) NOT NULL, UNIQUE(workspace_id,event_id,consumer_name)",
    ),
    "jobs": (
        False,
        "job_type text NOT NULL CHECK(job_type IN ('synthetic','reconcile_effect')), job_version integer NOT NULL CHECK(job_version=1), workflow_run_id uuid, subject_id uuid NOT NULL, input_ref uuid NOT NULL, input_hash char(64) NOT NULL, state text NOT NULL CHECK(state IN ('queued','leased','running','retry_wait','waiting_approval','waiting_external','cancel_requested','succeeded','dead_letter','cancelled')), priority text NOT NULL CHECK(priority IN ('safety','interactive','normal','bulk')), available_at timestamptz NOT NULL DEFAULT now(), deadline_at timestamptz NOT NULL, idempotency_key varchar(300) NOT NULL, attempt_count integer NOT NULL DEFAULT 0 CHECK(attempt_count>=0), max_attempts integer NOT NULL DEFAULT 3 CHECK(max_attempts BETWEEN 1 AND 10), timeout_seconds integer NOT NULL DEFAULT 30 CHECK(timeout_seconds BETWEEN 1 AND 300), lease_owner varchar(100), lease_expires_at timestamptz, heartbeat_at timestamptz, fence bigint NOT NULL DEFAULT 0 CHECK(fence>=0), cancel_requested_at timestamptz, last_error_code varchar(100), budget_reservation_id uuid, origin_event_id uuid, correlation_id uuid NOT NULL, waiting_on_resource_id uuid, effect_id uuid, replay_namespace varchar(100) NOT NULL DEFAULT '', recovery_of_id uuid, CHECK((state IN ('leased','running','cancel_requested'))=(lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)), UNIQUE(workspace_id,job_type,idempotency_key)",
    ),
    "job_attempts": (
        True,
        "job_id uuid NOT NULL, attempt_no integer NOT NULL CHECK(attempt_no>0), worker_id varchar(100) NOT NULL, fence bigint NOT NULL, phase text NOT NULL CHECK(phase IN ('start','finish')), started_at timestamptz NOT NULL, ended_at timestamptz, outcome varchar(100) NOT NULL, error_code varchar(100), effect_id uuid, reservation_id uuid, UNIQUE(workspace_id,job_id,attempt_no,phase), CHECK((phase='finish')=(ended_at IS NOT NULL))",
    ),
    "job_dependencies": (
        True,
        "job_id uuid NOT NULL, depends_on_job_id uuid NOT NULL, condition text NOT NULL CHECK(condition IN ('succeeded','terminal')), CHECK(job_id<>depends_on_job_id), UNIQUE(workspace_id,job_id,depends_on_job_id)",
    ),
    "schedules": (
        False,
        "name varchar(100) NOT NULL, timezone varchar(100) NOT NULL, rule varchar(100) NOT NULL CHECK(rule ~ '^daily:[0-2][0-9]:[0-5][0-9]$'), next_due_at timestamptz NOT NULL, last_emitted_slot varchar(200), enabled boolean NOT NULL, missed_policy text NOT NULL CHECK(missed_policy IN ('skip','one_catchup')), input_ref uuid NOT NULL, UNIQUE(workspace_id,name)",
    ),
    "schedule_slots": (
        True,
        "schedule_id uuid NOT NULL, slot varchar(200) NOT NULL, job_id uuid NOT NULL, late boolean NOT NULL, UNIQUE(workspace_id,schedule_id,slot)",
    ),
    "external_effects": (
        False,
        "connection_id uuid NOT NULL, action_type text NOT NULL CHECK(action_type='fake.execute'), target_id uuid NOT NULL, effect_key varchar(300) NOT NULL, request_hash char(64) NOT NULL, request_ref uuid NOT NULL, approval_id uuid CHECK(approval_id IS NULL), policy_version_id uuid CHECK(policy_version_id IS NULL), authority_version text NOT NULL CHECK(authority_version='phase-4-fake-v1'), expected_version bigint NOT NULL CHECK(expected_version=1), state text NOT NULL CHECK(state IN ('prepared','dispatching','confirmed','rejected','uncertain','cancelled')), dispatch_started_at timestamptz, provider_request_id varchar(100), provider_object_id varchar(100), receipt_hash char(64), reconcile_after timestamptz, lease_fence bigint NOT NULL DEFAULT 0, job_id uuid NOT NULL, reservation_id uuid, UNIQUE(workspace_id,connection_id,effect_key)",
    ),
    "budgets": (
        False,
        "period_start timestamptz NOT NULL, period_end timestamptz NOT NULL, category varchar(100) NOT NULL, limit_usd numeric(20,8) NOT NULL CHECK(limit_usd>=0), reserved_usd numeric(20,8) NOT NULL DEFAULT 0 CHECK(reserved_usd>=0), spent_usd numeric(20,8) NOT NULL DEFAULT 0 CHECK(spent_usd>=0), status text NOT NULL CHECK(status IN ('active','frozen')), CHECK(period_end>period_start), CHECK(reserved_usd+spent_usd<=limit_usd), UNIQUE(workspace_id,category,period_start,period_end)",
    ),
    "budget_reservations": (
        False,
        "budget_id uuid NOT NULL, job_id uuid NOT NULL, call_key varchar(300) NOT NULL, maximum_usd numeric(20,8) NOT NULL CHECK(maximum_usd>0), actual_usd numeric(20,8), state text NOT NULL CHECK(state IN ('reserved','settled','uncertain','released')), CHECK(actual_usd IS NULL OR actual_usd BETWEEN 0 AND maximum_usd), UNIQUE(workspace_id,call_key)",
    ),
    "usage_entries": (
        True,
        "reservation_id uuid NOT NULL, provider text NOT NULL CHECK(provider='fake_local'), task_type text NOT NULL CHECK(task_type='synthetic'), requests integer NOT NULL CHECK(requests>=0), units numeric(20,8) NOT NULL CHECK(units>=0), workflow_executions integer NOT NULL CHECK(workflow_executions>=0), cost_usd numeric(20,8) NOT NULL CHECK(cost_usd>=0), cost_status text NOT NULL CHECK(cost_status IN ('estimated','confirmed')), rate_version text NOT NULL CHECK(rate_version='phase-4-fake-v1'), UNIQUE(workspace_id,reservation_id,cost_status)",
    ),
    "quota_buckets": (
        False,
        "connection_id uuid NOT NULL, dimension text NOT NULL CHECK(dimension='requests'), window_start timestamptz NOT NULL, window_end timestamptz NOT NULL, limit_units bigint NOT NULL CHECK(limit_units>=0), reserved_units bigint NOT NULL DEFAULT 0 CHECK(reserved_units>=0), consumed_units bigint NOT NULL DEFAULT 0 CHECK(consumed_units>=0), safety_reserve bigint NOT NULL CHECK(safety_reserve>=0), CHECK(reserved_units+consumed_units<=limit_units), CHECK(window_end>window_start), UNIQUE(workspace_id,connection_id,dimension,window_start)",
    ),
    "fake_receipts": (
        True,
        "effect_id uuid NOT NULL, outcome text NOT NULL CHECK(outcome IN ('confirmed','rejected')), visible_after timestamptz NOT NULL, provider_request_id varchar(100) NOT NULL, receipt_hash char(64) NOT NULL, UNIQUE(workspace_id,effect_id)",
    ),
    "webhook_inbox": (
        False,
        "connection_id uuid NOT NULL, provider_event_key varchar(200) NOT NULL, payload_encrypted text NOT NULL CHECK(octet_length(payload_encrypted)<32768), payload_sha256 char(64) NOT NULL, authenticated boolean NOT NULL CHECK(authenticated), received_at timestamptz NOT NULL DEFAULT now(), provider_occurred_at timestamptz, expires_at timestamptz NOT NULL DEFAULT now()+interval '30 days', state text NOT NULL CHECK(state IN ('received','processing','applied','quarantined','ignored')), error_code varchar(100), external_id uuid NOT NULL, observation_version bigint NOT NULL CHECK(observation_version>0), observation text NOT NULL CHECK(observation IN ('active','stopped')), UNIQUE(workspace_id,connection_id,provider_event_key)",
    ),
    "fake_observations": (
        False,
        "connection_id uuid NOT NULL, input_ref uuid NOT NULL, observation_version bigint NOT NULL CHECK(observation_version>0), state text NOT NULL CHECK(state IN ('active','stopped')), UNIQUE(workspace_id,connection_id,input_ref)",
    ),
    "runtime_heartbeats": (
        False,
        "component text NOT NULL CHECK(component IN ('worker','scheduler','fake_adapter')), instance varchar(100) NOT NULL, measured_at timestamptz NOT NULL, UNIQUE(workspace_id,component,instance)",
    ),
    "incidents": (
        False,
        "severity text NOT NULL CHECK(severity IN ('P0','P1','P2')), kind varchar(100) NOT NULL, state text NOT NULL CHECK(state IN ('open','contained','recovering','resolved')), owner_id uuid NOT NULL REFERENCES app.principals(id), opened_at timestamptz NOT NULL DEFAULT now(), resolved_at timestamptz, fingerprint varchar(300) NOT NULL, UNIQUE(workspace_id,fingerprint)",
    ),
    "incident_evidence": (
        True,
        "incident_id uuid NOT NULL, job_id uuid, effect_id uuid, CHECK(num_nonnulls(job_id,effect_id)=1)",
    ),
    "runtime_attention": (
        False,
        "incident_id uuid NOT NULL, state text NOT NULL CHECK(state IN ('open','snoozed','resolved')), snooze_until timestamptz, reason varchar(500), UNIQUE(workspace_id,incident_id)",
    ),
}
REFS = {
    "workflow_runs": {"subject_id": "runtime_inputs"},
    "events": {"payload_ref": "runtime_inputs"},
    "outbox": {"event_id": "events"},
    "consumer_receipts": {"event_id": "events"},
    "jobs": {
        "workflow_run_id": "workflow_runs",
        "subject_id": "runtime_inputs",
        "input_ref": "runtime_inputs",
        "origin_event_id": "events",
        "budget_reservation_id": "budget_reservations",
        "effect_id": "external_effects",
        "waiting_on_resource_id": "runtime_inputs",
        "recovery_of_id": "jobs",
    },
    "job_attempts": {
        "job_id": "jobs",
        "effect_id": "external_effects",
        "reservation_id": "budget_reservations",
    },
    "job_dependencies": {"job_id": "jobs", "depends_on_job_id": "jobs"},
    "schedules": {"input_ref": "runtime_inputs"},
    "schedule_slots": {"schedule_id": "schedules", "job_id": "jobs"},
    "external_effects": {
        "connection_id": "fake_endpoints",
        "target_id": "runtime_inputs",
        "request_ref": "runtime_inputs",
        "job_id": "jobs",
        "reservation_id": "budget_reservations",
    },
    "budget_reservations": {"budget_id": "budgets", "job_id": "jobs"},
    "usage_entries": {"reservation_id": "budget_reservations"},
    "quota_buckets": {"connection_id": "fake_endpoints"},
    "fake_receipts": {"effect_id": "external_effects"},
    "webhook_inbox": {"connection_id": "fake_endpoints"},
    "fake_observations": {"connection_id": "fake_endpoints", "input_ref": "runtime_inputs"},
    "incident_evidence": {
        "incident_id": "incidents",
        "job_id": "jobs",
        "effect_id": "external_effects",
    },
    "runtime_attention": {"incident_id": "incidents"},
}


def upgrade() -> None:
    for table, (immutable, fields) in TABLES.items():
        mutable = (
            ""
            if immutable
            else ", updated_at timestamptz NOT NULL DEFAULT now(), record_version bigint NOT NULL DEFAULT 1 CHECK(record_version>0), updated_by uuid NOT NULL REFERENCES app.principals(id)"
        )
        op.execute(
            f"CREATE TABLE app.{table}(id uuid PRIMARY KEY,workspace_id uuid NOT NULL REFERENCES app.workspaces(id),created_at timestamptz NOT NULL DEFAULT now(),schema_version smallint NOT NULL DEFAULT 1 CHECK(schema_version>0),created_by uuid NOT NULL REFERENCES app.principals(id){mutable},{fields},UNIQUE(workspace_id,id))"
        )
        op.execute(
            f"ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY; ALTER TABLE app.{table} FORCE ROW LEVEL SECURITY"
        )
        op.execute(
            f"CREATE POLICY runtime_scope ON app.{table} TO company_api,company_worker USING(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id)) WITH CHECK(workspace_id=app.current_workspace_id() AND app.has_active_membership(app.current_principal_id(),workspace_id))"
        )
        op.execute(
            f"GRANT SELECT,INSERT{'' if immutable else ',UPDATE'} ON app.{table} TO company_api,company_worker"
        )
        op.execute(f"CREATE INDEX {table}_chronology ON app.{table}(workspace_id,created_at,id)")
        op.execute(
            f"CREATE TRIGGER runtime_guard BEFORE UPDATE OR DELETE ON app.{table} FOR EACH ROW EXECUTE FUNCTION app.core_row_guard('{'append' if immutable else 'mutable'}')"
        )
    for table, refs in REFS.items():
        for field, target in refs.items():
            op.execute(
                f"ALTER TABLE app.{table} ADD FOREIGN KEY(workspace_id,{field}) REFERENCES app.{target}(workspace_id,id) DEFERRABLE INITIALLY IMMEDIATE"
            )
            op.execute(f"CREATE INDEX {table}_{field}_fk ON app.{table}(workspace_id,{field})")
    op.execute("""
    CREATE INDEX jobs_ready ON app.jobs(workspace_id,priority,available_at,created_at) WHERE state IN ('queued','retry_wait');
    CREATE INDEX effects_reconcile ON app.external_effects(workspace_id,reconcile_after) WHERE state IN ('dispatching','uncertain');
    CREATE INDEX outbox_pending ON app.outbox(workspace_id,available_at) WHERE dispatched_at IS NULL;
    CREATE FUNCTION app.runtime_actor_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    BEGIN
      IF current_user IN ('company_api','company_worker') THEN
        IF TG_OP='INSERT' AND NEW.created_by IS DISTINCT FROM app.current_principal_id() THEN RAISE EXCEPTION 'Actor mismatch' USING ERRCODE='23514'; END IF;
        IF TG_ARGV[0]='mutable' AND NEW.updated_by IS DISTINCT FROM app.current_principal_id() THEN RAISE EXCEPTION 'Actor mismatch' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE FUNCTION app.runtime_dependencies_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    BEGIN
      PERFORM pg_advisory_xact_lock(hashtextextended(NEW.workspace_id::text,41));
      IF EXISTS(WITH RECURSIVE chain(id) AS (
        SELECT NEW.depends_on_job_id UNION SELECT d.depends_on_job_id FROM app.job_dependencies d JOIN chain c ON d.job_id=c.id WHERE d.workspace_id=NEW.workspace_id
      ) SELECT 1 FROM chain WHERE id=NEW.job_id) THEN RAISE EXCEPTION 'Dependency cycle' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER dependency_cycle BEFORE INSERT ON app.job_dependencies FOR EACH ROW EXECUTE FUNCTION app.runtime_dependencies_guard();
    CREATE FUNCTION app.runtime_workspaces() RETURNS TABLE(principal_id uuid,workspace_id uuid,authz_epoch bigint)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
      SELECT p.id,w.id,w.authz_epoch FROM app.service_identities s JOIN app.principals p ON p.id=s.principal_id
      JOIN app.memberships m ON m.principal_id=p.id JOIN app.workspaces w ON w.id=m.workspace_id
      WHERE session_user='company_worker' AND s.name='foundation-worker' AND s.capability_profile='phase-4-fake-runtime'
      AND p.status='active' AND s.expires_at>now() AND m.status='active' AND (m.expires_at IS NULL OR m.expires_at>now()) AND w.status IN ('active','paused')
    $$;
    ALTER FUNCTION app.runtime_workspaces() OWNER TO company_auth;
    REVOKE ALL ON FUNCTION app.runtime_workspaces(),app.runtime_actor_guard(),app.runtime_dependencies_guard() FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION app.runtime_workspaces() TO company_worker;
    GRANT SELECT,INSERT ON app.audit_entries TO company_worker;
    """)
    for table, (immutable, _) in TABLES.items():
        op.execute(
            f"CREATE TRIGGER runtime_actor BEFORE INSERT OR UPDATE ON app.{table} FOR EACH ROW EXECUTE FUNCTION app.runtime_actor_guard('{'append' if immutable else 'mutable'}')"
        )

    op.execute("""
    GRANT SELECT ON app.fake_endpoints TO company_auth;
    CREATE POLICY callback_directory ON app.fake_endpoints TO company_auth USING(true);
    CREATE FUNCTION app.fake_callback_context(endpoint uuid) RETURNS TABLE(principal_id uuid,workspace_id uuid,authz_epoch bigint)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,app AS $$
      SELECT p.id,w.id,w.authz_epoch FROM app.fake_endpoints e JOIN app.workspaces w ON w.id=e.workspace_id
      JOIN app.memberships m ON m.workspace_id=w.id JOIN app.principals p ON p.id=m.principal_id
      JOIN app.service_identities s ON s.principal_id=p.id
      WHERE e.id=endpoint AND e.enabled AND s.name='foundation-worker' AND s.capability_profile='phase-4-fake-runtime'
      AND p.status='active' AND s.expires_at>now() AND m.status='active' AND (m.expires_at IS NULL OR m.expires_at>now()) AND w.status IN ('active','paused')
    $$;
    ALTER FUNCTION app.fake_callback_context(uuid) OWNER TO company_auth;
    REVOKE ALL ON FUNCTION app.fake_callback_context(uuid) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION app.fake_callback_context(uuid) TO company_api;
    """)


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION app.runtime_workspaces(); DROP FUNCTION app.fake_callback_context(uuid)"
    )
    op.execute("REVOKE SELECT,INSERT ON app.audit_entries FROM company_worker")
    # Drop only the explicitly enumerated Phase 4 constraints before cyclic table references.
    for table in TABLES:
        op.execute(f"DROP TABLE app.{table} CASCADE")
    op.execute(
        "DROP FUNCTION app.runtime_actor_guard(); DROP FUNCTION app.runtime_dependencies_guard()"
    )
