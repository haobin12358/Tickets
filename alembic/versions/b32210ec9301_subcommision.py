"""'subcommision'

Revision ID: b32210ec9301
Revises: b4522f916919
Create Date: 2020-07-02 21:11:46.191292

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'b32210ec9301'
down_revision = 'b4522f916919'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('UserDistribute',
    sa.Column('isdelete', sa.Boolean(), nullable=True, comment='是否删除'),
    sa.Column('createtime', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updatetime', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.Column('UDid', sa.String(length=64), nullable=False),
    sa.Column('UDinputer', sa.String(length=64), nullable=True, comment='操作人'),
    sa.Column('UDinperson', sa.String(length=64), nullable=True, comment='被执行人'),
    sa.Column('UDexecutor', sa.String(length=64), nullable=True, comment='管理者'),
    sa.PrimaryKeyConstraint('UDid')
    )
    op.create_table('UserSubCommission',
    sa.Column('isdelete', sa.Boolean(), nullable=True, comment='是否删除'),
    sa.Column('createtime', sa.DateTime(), nullable=True, comment='创建时间'),
    sa.Column('updatetime', sa.DateTime(), nullable=True, comment='更新时间'),
    sa.Column('USCid', sa.String(length=64), nullable=False),
    sa.Column('USCsupper1', sa.String(length=64), nullable=True, comment='一级分佣人员'),
    sa.Column('USCsupper2', sa.String(length=64), nullable=True, comment='二级分佣人员'),
    sa.Column('USCsupper3', sa.String(length=64), nullable=True, comment='三级分佣人员'),
    sa.PrimaryKeyConstraint('USCid')
    )

    op.add_column('User', sa.Column('USsuperlevel', sa.Integer(), nullable=True, comment='分佣等级'))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('User', 'USsuperlevel')
    op.drop_table('UserSubCommission')
    op.drop_table('UserDistribute')
    # ### end Alembic commands ###
