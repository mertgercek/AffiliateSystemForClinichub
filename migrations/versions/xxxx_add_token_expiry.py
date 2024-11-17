"""add token expiry to user

Revision ID: xxxx
Revises: previous_revision_id
Create Date: 2024-03-17 21:15:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'xxxx'
down_revision = 'previous_revision_id'  # replace with your last migration id
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('user', sa.Column('token_expiry', sa.DateTime(), nullable=True))

def downgrade():
    op.drop_column('user', 'token_expiry') 