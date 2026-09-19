"""Correct reservation column binding without rewriting applied revisions."""

from alembic import op

revision = "0024_ai_guard_correction"
down_revision = "0023_ai_context_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    DO $$ DECLARE body text; BEGIN
      body=pg_get_functiondef('app.ai_call_binding()'::regprocedure);
      EXECUTE replace(body,'b.amount_usd','b.maximum_usd');
      body=pg_get_functiondef('app.ai_identity_guard()'::regprocedure);
      body=replace(body,'OLD.status','(to_jsonb(OLD)->>''status'')');
      body=replace(body,'NEW.status','(to_jsonb(NEW)->>''status'')');
      body=replace(body,'NEW.ended_at','(to_jsonb(NEW)->>''ended_at'')');
      body=replace(body,'NEW.permission_epoch','(to_jsonb(NEW)->>''permission_epoch'')::integer');
      body=replace(body,'OLD.permission_epoch','(to_jsonb(OLD)->>''permission_epoch'')::integer');
      body=replace(body,'NEW.rights_valid','(to_jsonb(NEW)->>''rights_valid'')::boolean');
      body=replace(body,'NEW.state','(to_jsonb(NEW)->>''state'')');
      EXECUTE body;
    END $$;
    """)


def downgrade() -> None:
    op.execute("""
    DO $$ DECLARE body text; BEGIN
      body=pg_get_functiondef('app.ai_call_binding()'::regprocedure);
      EXECUTE replace(body,'b.maximum_usd','b.amount_usd');
    END $$;
    """)
