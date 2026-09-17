"""Phase 2 identity, sessions, audit and forced RLS.

Revision ID: 0001_foundation
Revises: none
"""

from pathlib import Path

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(Path(__file__).with_suffix(".sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    # Explicit operator-only rollback; all synthetic Phase 2 data is lost.
    op.execute("DROP SCHEMA app CASCADE")
