"""add_purchase_price

Revision ID: b4522f916919
Revises: 67186446f8d3
Create Date: 2020-07-02 16:14:14.116004

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'b4522f916919'
down_revision = '67186446f8d3'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('UserDistribute')
    op.drop_table('UserSubCommission')
    op.add_column('Product', sa.Column('PurchasePrice', sa.DECIMAL(precision=28, scale=2), nullable=True))
    op.drop_column('User', 'USsuperlevel')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('User', sa.Column('USsuperlevel', mysql.INTEGER(display_width=11), autoincrement=False, nullable=True))
    op.drop_column('Product', 'PurchasePrice')
    op.create_table('UserSubCommission',
    sa.Column('isdelete', mysql.TINYINT(display_width=1), autoincrement=False, nullable=True),
    sa.Column('createtime', mysql.DATETIME(), nullable=True),
    sa.Column('updatetime', mysql.DATETIME(), nullable=True),
    sa.Column('USCid', mysql.VARCHAR(length=64), nullable=False),
    sa.Column('USCsupper1', mysql.VARCHAR(length=64), nullable=True),
    sa.Column('USCsupper2', mysql.VARCHAR(length=64), nullable=True),
    sa.Column('USCsupper3', mysql.VARCHAR(length=64), nullable=True),
    sa.PrimaryKeyConstraint('USCid'),
    mysql_default_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_table('UserDistribute',
    sa.Column('isdelete', mysql.TINYINT(display_width=1), autoincrement=False, nullable=True),
    sa.Column('createtime', mysql.DATETIME(), nullable=True),
    sa.Column('updatetime', mysql.DATETIME(), nullable=True),
    sa.Column('UDid', mysql.VARCHAR(length=64), nullable=False),
    sa.Column('UDinputer', mysql.VARCHAR(length=64), nullable=True),
    sa.Column('UDinperson', mysql.VARCHAR(length=64), nullable=True),
    sa.Column('UDexecutor', mysql.VARCHAR(length=64), nullable=True),
    sa.PrimaryKeyConstraint('UDid'),
    mysql_default_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    # ### end Alembic commands ###
