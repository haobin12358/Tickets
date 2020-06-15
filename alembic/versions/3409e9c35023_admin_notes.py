"""admin_notes

Revision ID: 3409e9c35023
Revises: 096230c10a9d
Create Date: 2020-06-14 02:22:17.096158

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3409e9c35023'
down_revision = '096230c10a9d'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('AdminNotes',
    sa.Column('isdelete', sa.Boolean(), nullable=True),
    sa.Column('createtime', sa.DateTime(), nullable=True),
    sa.Column('updatetime', sa.DateTime(), nullable=True),
    sa.Column('ANid', sa.String(length=64), nullable=False),
    sa.Column('ADid', sa.String(length=64), nullable=False),
    sa.Column('ANaction', sa.Text(), nullable=True),
    sa.Column('ANdoneid', sa.String(length=64), nullable=True),
    sa.PrimaryKeyConstraint('ANid')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('AdminNotes')
    # ### end Alembic commands ###