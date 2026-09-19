"""Lock mutable jobs when admitting specs; preserve immutable input privileges."""

from alembic import op

revision = "0020_long_spec_lock"
down_revision = "0019_long_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE OR REPLACE FUNCTION app.long_spec_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE input app.runtime_inputs;
    BEGIN
      SELECT * INTO input FROM app.runtime_inputs WHERE workspace_id=NEW.workspace_id AND id=NEW.input_id;
      PERFORM id FROM app.jobs WHERE workspace_id=NEW.workspace_id AND input_ref=NEW.input_id ORDER BY id FOR UPDATE;
      IF input.id IS NULL OR EXISTS(SELECT 1 FROM app.jobs WHERE workspace_id=NEW.workspace_id AND input_ref=input.id AND attempt_count>0) THEN RAISE EXCEPTION 'Execution already admitted' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    ALTER TABLE app.runtime_heartbeats DROP CONSTRAINT runtime_heartbeats_component_check;
    ALTER TABLE app.runtime_heartbeats ADD CONSTRAINT runtime_heartbeats_component_check CHECK(component IN ('worker','scheduler','fake_adapter','long_pool'));
    """)


def downgrade() -> None:
    op.execute("""
    DELETE FROM app.runtime_heartbeats WHERE component='long_pool';
    ALTER TABLE app.runtime_heartbeats DROP CONSTRAINT runtime_heartbeats_component_check;
    ALTER TABLE app.runtime_heartbeats ADD CONSTRAINT runtime_heartbeats_component_check CHECK(component IN ('worker','scheduler','fake_adapter'));
    CREATE OR REPLACE FUNCTION app.long_spec_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    DECLARE input app.runtime_inputs;
    BEGIN
      SELECT * INTO input FROM app.runtime_inputs WHERE workspace_id=NEW.workspace_id AND id=NEW.input_id FOR UPDATE;
      IF input.id IS NULL OR EXISTS(SELECT 1 FROM app.jobs WHERE workspace_id=NEW.workspace_id AND input_ref=input.id AND attempt_count>0) THEN RAISE EXCEPTION 'Execution already admitted' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    """)
