"""Correct polymorphic actor-trigger field access without editing applied revisions."""

from alembic import op

revision = "0008_runtime_actor_guard"
down_revision = "0007_runtime_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE OR REPLACE FUNCTION app.runtime_actor_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    BEGIN
      IF current_user IN ('company_api','company_worker') THEN
        IF TG_OP='INSERT' THEN
          IF NEW.created_by IS DISTINCT FROM app.current_principal_id() THEN RAISE EXCEPTION 'Actor mismatch' USING ERRCODE='23514'; END IF;
        END IF;
        IF TG_ARGV[0]='mutable' THEN
          IF NEW.updated_by IS DISTINCT FROM app.current_principal_id() THEN RAISE EXCEPTION 'Actor mismatch' USING ERRCODE='23514'; END IF;
        END IF;
      END IF;
      RETURN NEW;
    END $$;
    """)


def downgrade() -> None:
    op.execute("""
    CREATE OR REPLACE FUNCTION app.runtime_actor_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,app AS $$
    BEGIN
      IF current_user IN ('company_api','company_worker') THEN
        IF TG_OP='INSERT' AND NEW.created_by IS DISTINCT FROM app.current_principal_id() THEN RAISE EXCEPTION 'Actor mismatch' USING ERRCODE='23514'; END IF;
        IF TG_ARGV[0]='mutable' AND NEW.updated_by IS DISTINCT FROM app.current_principal_id() THEN RAISE EXCEPTION 'Actor mismatch' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    """)
