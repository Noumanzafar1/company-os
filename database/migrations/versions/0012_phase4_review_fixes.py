"""Bound effect ownership, current recovery health, event versions and schedules."""

from alembic import op

revision = "0012_phase4_review_fixes"
down_revision = "0011_runtime_event_payloads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE app.jobs ADD COLUMN coalesced_effect_id uuid;
    ALTER TABLE app.jobs ADD FOREIGN KEY(workspace_id,coalesced_effect_id) REFERENCES app.external_effects(workspace_id,id);
    ALTER TABLE app.jobs ADD CHECK(coalesced_effect_id IS NULL OR (effect_id IS NULL AND budget_reservation_id IS NULL));
    CREATE INDEX jobs_coalesced_effect ON app.jobs(workspace_id,coalesced_effect_id) WHERE coalesced_effect_id IS NOT NULL;
    -- Preserve historical outcomes while removing legacy duplicate execution authority.
    UPDATE app.jobs j SET coalesced_effect_id=e.id,effect_id=NULL,budget_reservation_id=NULL,record_version=j.record_version+1
      FROM app.external_effects e WHERE j.workspace_id=e.workspace_id AND j.effect_id=e.id AND j.job_type='synthetic' AND j.id<>e.job_id;
    CREATE FUNCTION app.runtime_effect_ownership_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    BEGIN
      IF (NEW.job_id,NEW.reservation_id,NEW.quota_bucket_id,NEW.connection_id,NEW.effect_key,NEW.request_hash,NEW.request_ref)
        IS DISTINCT FROM (OLD.job_id,OLD.reservation_id,OLD.quota_bucket_id,OLD.connection_id,OLD.effect_key,OLD.request_hash,OLD.request_ref)
      THEN RAISE EXCEPTION 'Immutable effect authority' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER runtime_effect_ownership BEFORE UPDATE ON app.external_effects FOR EACH ROW EXECUTE FUNCTION app.runtime_effect_ownership_guard();
    CREATE FUNCTION app.runtime_job_effect_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    BEGIN
      IF NEW.job_type='synthetic' AND NEW.effect_id IS NOT NULL AND NOT EXISTS
        (SELECT 1 FROM app.external_effects e WHERE e.workspace_id=NEW.workspace_id AND e.id=NEW.effect_id AND e.job_id=NEW.id)
      THEN RAISE EXCEPTION 'Effect belongs to another job' USING ERRCODE='23514'; END IF;
      IF NEW.coalesced_effect_id IS NOT NULL AND NOT EXISTS
        (SELECT 1 FROM app.external_effects e WHERE e.workspace_id=NEW.workspace_id AND e.id=NEW.coalesced_effect_id AND e.job_id<>NEW.id AND e.request_hash=NEW.input_hash)
      THEN RAISE EXCEPTION 'Invalid coalesced effect reference' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER runtime_job_effect BEFORE INSERT OR UPDATE ON app.jobs FOR EACH ROW EXECUTE FUNCTION app.runtime_job_effect_guard();
    CREATE FUNCTION app.runtime_event_version_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE actual_version bigint;
    BEGIN
      CASE NEW.aggregate_type
      WHEN 'runtime_input' THEN SELECT 1 INTO actual_version FROM app.runtime_inputs WHERE workspace_id=NEW.workspace_id AND id=NEW.aggregate_id;
      WHEN 'job' THEN SELECT record_version INTO actual_version FROM app.jobs WHERE workspace_id=NEW.workspace_id AND id=NEW.aggregate_id FOR SHARE;
      WHEN 'effect' THEN SELECT record_version INTO actual_version FROM app.external_effects WHERE workspace_id=NEW.workspace_id AND id=NEW.aggregate_id FOR SHARE;
      WHEN 'budget' THEN SELECT record_version INTO actual_version FROM app.budgets WHERE workspace_id=NEW.workspace_id AND id=NEW.aggregate_id FOR SHARE;
      WHEN 'incident' THEN SELECT record_version INTO actual_version FROM app.incidents WHERE workspace_id=NEW.workspace_id AND id=NEW.aggregate_id FOR SHARE;
      ELSE actual_version=NULL;
      END CASE;
      IF actual_version IS NULL OR NEW.aggregate_version IS DISTINCT FROM actual_version
      THEN RAISE EXCEPTION 'Event aggregate version mismatch' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    -- PostgreSQL orders same-kind triggers by name: lock/version before payload validation.
    CREATE TRIGGER runtime_event_aggregate_version BEFORE INSERT ON app.events FOR EACH ROW EXECUTE FUNCTION app.runtime_event_version_guard();
    ALTER TABLE app.schedules DROP CONSTRAINT schedules_rule_check;
    ALTER TABLE app.schedules ADD COLUMN last_error_code text CHECK(last_error_code IS NULL OR last_error_code='INVALID_SCHEDULE');
    CREATE FUNCTION app.runtime_schedule_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    BEGIN
      IF TG_OP='UPDATE' THEN
        IF NOT NEW.enabled AND NEW.last_error_code='INVALID_SCHEDULE'
          AND (to_jsonb(NEW)-ARRAY['enabled','last_error_code','record_version','updated_at','updated_by'])
            =(to_jsonb(OLD)-ARRAY['enabled','last_error_code','record_version','updated_at','updated_by'])
        THEN RETURN NEW; END IF;
      END IF;
      IF NEW.rule !~ '^daily:([01][0-9]|2[0-3]):[0-5][0-9]$'
        OR NOT EXISTS(SELECT 1 FROM pg_timezone_names WHERE name=NEW.timezone)
      THEN RAISE EXCEPTION 'Invalid schedule rule or IANA timezone' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER runtime_schedule_validate BEFORE INSERT OR UPDATE ON app.schedules FOR EACH ROW EXECUTE FUNCTION app.runtime_schedule_guard();
    REVOKE ALL ON FUNCTION app.runtime_effect_ownership_guard(),app.runtime_job_effect_guard(),app.runtime_event_version_guard(),app.runtime_schedule_guard() FROM PUBLIC;
    """)


def downgrade() -> None:
    op.execute("""
    DROP TRIGGER runtime_schedule_validate ON app.schedules;
    DROP FUNCTION app.runtime_schedule_guard();
    ALTER TABLE app.schedules DROP COLUMN last_error_code;
    ALTER TABLE app.schedules ADD CONSTRAINT schedules_rule_check CHECK(rule ~ '^daily:[0-2][0-9]:[0-5][0-9]$') NOT VALID;
    DROP TRIGGER runtime_event_aggregate_version ON app.events;
    DROP FUNCTION app.runtime_event_version_guard();
    DROP TRIGGER runtime_job_effect ON app.jobs;
    DROP FUNCTION app.runtime_job_effect_guard();
    DROP TRIGGER runtime_effect_ownership ON app.external_effects;
    DROP FUNCTION app.runtime_effect_ownership_guard();
    ALTER TABLE app.jobs DROP COLUMN coalesced_effect_id;
    """)
