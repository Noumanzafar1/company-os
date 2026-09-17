"""Correct shared trigger field access discovered by the disabled-user test.

Revision ID: 0002_identity_guards
Revises: 0001_foundation
"""

from pathlib import Path

from alembic import op

revision = "0002_identity_guards"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE OR REPLACE FUNCTION app.version_update() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.id<>OLD.id OR NEW.created_by<>OLD.created_by OR NEW.created_at<>OLD.created_at THEN
        RAISE EXCEPTION 'Immutable identity' USING ERRCODE='23514';
      END IF;
      IF TG_TABLE_NAME='memberships' THEN
        IF NEW.workspace_id<>OLD.workspace_id THEN
          RAISE EXCEPTION 'Immutable workspace' USING ERRCODE='23514';
        END IF;
      END IF;
      IF TG_TABLE_NAME IN ('users','service_identities') THEN
        IF NEW.principal_id<>OLD.principal_id THEN
          RAISE EXCEPTION 'Immutable principal subtype' USING ERRCODE='23514';
        END IF;
      END IF;
      IF NEW.record_version<>OLD.record_version+1 THEN
        RAISE EXCEPTION 'Expected next record version' USING ERRCODE='40001';
      END IF;
      NEW.updated_at=clock_timestamp(); RETURN NEW;
    END $$;
    """)


def downgrade() -> None:
    original = Path(__file__).with_name("0001_foundation.sql").read_text(encoding="utf-8")
    function = original.split("CREATE FUNCTION app.version_update()", 1)[1].split("END $$;", 1)[0]
    op.execute("CREATE OR REPLACE FUNCTION app.version_update()" + function + "END $$;")
