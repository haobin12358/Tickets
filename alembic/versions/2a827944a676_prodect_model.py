"""prodect_model

Revision ID: 2a827944a676
Revises: 11ef41aefdca
Create Date: 2020-06-11 01:51:08.765399

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2a827944a676'
down_revision = '11ef41aefdca'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('Product',
    sa.Column('isdelete', sa.Boolean(), nullable=True),
    sa.Column('createtime', sa.DateTime(), nullable=True),
    sa.Column('updatetime', sa.DateTime(), nullable=True),
    sa.Column('PRid', sa.String(length=64), nullable=False),
    sa.Column('CreatorId', sa.String(length=64), nullable=True),
    sa.Column('CreatorType', sa.String(length=20), nullable=True),
    sa.Column('PRname', sa.String(length=256), nullable=False),
    sa.Column('PRimg', sa.Text(), nullable=True),
    sa.Column('PRtimeLimeted', sa.Integer(), nullable=True),
    sa.Column('PRissueStartTime', sa.DateTime(), nullable=True),
    sa.Column('PRissueEndTime', sa.DateTime(), nullable=True),
    sa.Column('PRuseStartTime', sa.DateTime(), nullable=True),
    sa.Column('PRuseEndTime', sa.DateTime(), nullable=True),
    sa.Column('PRdetails', sa.Text(), nullable=True),
    sa.Column('PRlinePrice', sa.DECIMAL(precision=28, scale=2), nullable=True),
    sa.Column('PRtruePrice', sa.DECIMAL(precision=28, scale=2), nullable=True),
    sa.Column('PRstatus', sa.Integer(), nullable=True),
    sa.Column('PRnum', sa.Integer(), nullable=True),
    sa.Column('PRbanner', sa.Text(), nullable=True),
    sa.Column('SUid', sa.String(length=64), nullable=True),
    sa.Column('longitude', sa.String(length=255), nullable=True),
    sa.Column('latitude', sa.String(length=255), nullable=True),
    sa.Column('address', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('PRid')
    )
    op.create_table('Supplizer',
    sa.Column('isdelete', sa.Boolean(), nullable=True),
    sa.Column('createtime', sa.DateTime(), nullable=True),
    sa.Column('updatetime', sa.DateTime(), nullable=True),
    sa.Column('SUid', sa.String(length=64), nullable=False),
    sa.Column('SUloginPhone', sa.String(length=11), nullable=False),
    sa.Column('SUlinkPhone', sa.String(length=11), nullable=True),
    sa.Column('SUname', sa.String(length=32), nullable=True),
    sa.Column('SUlinkman', sa.String(length=16), nullable=False),
    sa.Column('SUaddress', sa.String(length=255), nullable=False),
    sa.Column('SUstatus', sa.Integer(), nullable=True),
    sa.Column('SUdeposit', sa.DECIMAL(precision=28, scale=2), nullable=True),
    sa.Column('SUbanksn', sa.String(length=32), nullable=True),
    sa.Column('SUbankname', sa.String(length=64), nullable=True),
    sa.Column('SUpassword', sa.String(length=255), nullable=True),
    sa.Column('SUheader', sa.String(length=255), nullable=True),
    sa.Column('SUcontract', sa.Text(), nullable=True),
    sa.Column('SUbusinessLicense', sa.Text(), nullable=True),
    sa.Column('SUregisteredFund', sa.String(length=255), nullable=True),
    sa.Column('SUmainCategory', sa.Text(), nullable=True),
    sa.Column('SUregisteredTime', sa.DateTime(), nullable=True),
    sa.Column('SUlegalPerson', sa.Text(), nullable=True),
    sa.Column('SUemail', sa.String(length=256), nullable=True),
    sa.Column('SUlegalPersonIDcardFront', sa.Text(), nullable=True),
    sa.Column('SUlegalPersonIDcardBack', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('SUid')
    )
    op.create_index(op.f('ix_Supplizer_SUloginPhone'), 'Supplizer', ['SUloginPhone'], unique=True)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_Supplizer_SUloginPhone'), table_name='Supplizer')
    op.drop_table('Supplizer')
    op.drop_table('Product')
    # ### end Alembic commands ###
