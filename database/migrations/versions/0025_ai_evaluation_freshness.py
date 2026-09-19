"""Promotion must compare the still-current route with recent immutable evidence."""

from alembic import op

revision = "0025_ai_evaluation_freshness"
down_revision = "0024_ai_guard_correction"
branch_labels = None
depends_on = None

OLD = "OR e.body->>'decision' IS DISTINCT FROM 'technical_pass'"
NEW = (
    OLD
    + """
        OR e.created_at<clock_timestamp()-interval '30 days'
        OR e.current_route_id IS DISTINCT FROM (r.payload->>'current_route_id')::uuid
        OR (r.payload->>'rollback_route_id') IS DISTINCT FROM (r.payload->>'current_route_id')"""
)


def replace_guard(before: str, after: str) -> None:
    from sqlalchemy import text

    conn = op.get_bind()
    body = conn.execute(
        text("SELECT pg_get_functiondef('app.ai_route_use_guard()'::regprocedure)")
    ).scalar_one()
    if before not in body:
        raise RuntimeError("Unexpected route guard definition")
    op.execute(body.replace(before, after))


def upgrade() -> None:
    replace_guard(OLD, NEW)


def downgrade() -> None:
    replace_guard(NEW, OLD)
