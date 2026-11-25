"""run web access and retry link

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("web_access", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("retry_of_run_id", sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f("ix_runs_retry_of_run_id"), ["retry_of_run_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_runs_retry_of_run_id_runs"), "runs", ["retry_of_run_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_runs_retry_of_run_id_runs"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_runs_retry_of_run_id"))
        batch_op.drop_column("retry_of_run_id")
        batch_op.drop_column("web_access")
