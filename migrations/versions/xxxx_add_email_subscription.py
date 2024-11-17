"""add email subscription to user

Revision ID: xxxx
Revises: previous_revision_id
Create Date: 2024-03-17 21:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'xxxx'
down_revision = 'previous_revision_id'  # replace with your last migration id
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('user', sa.Column('email_subscribed', sa.Boolean(), nullable=False, server_default='true'))

def downgrade():
    op.drop_column('user', 'email_subscribed') 