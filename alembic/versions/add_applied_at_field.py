"""add applied_at field to job_results

Revision ID: add_applied_at
Revises: 
Create Date: 2025-08-15

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_applied_at'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add applied_at column to job_results table
    op.add_column('job_results', sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True))
    
    # Add index for applied_at field for faster queries
    op.create_index('ix_job_results_applied_at', 'job_results', ['applied_at'])


def downgrade() -> None:
    # Remove index and column
    op.drop_index('ix_job_results_applied_at', table_name='job_results')
    op.drop_column('job_results', 'applied_at')