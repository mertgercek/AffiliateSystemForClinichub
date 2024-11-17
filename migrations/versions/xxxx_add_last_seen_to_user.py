"""add last_seen to user

Revision ID: xxxx
Revises: previous_revision_id
Create Date: 2024-03-17 21:10:21.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = 'xxxx'
down_revision = 'previous_revision_id'  # replace with your last migration id
branch_labels = None
depends_on = None

def upgrade():
    # Add last_seen column with current timestamp as default
    op.add_column('user', sa.Column('last_seen', sa.DateTime(), nullable=True, server_default=sa.text('NOW()')))

def downgrade():
    # Remove last_seen column
    op.drop_column('user', 'last_seen') 