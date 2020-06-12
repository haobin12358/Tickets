from sqlalchemy import String, Text, DateTime, DECIMAL, Integer

from tickets.extensions.base_model import Base, Column


class Product(Base):
    """商品实体"""
    __tablename__ = 'Product'
    PRid = Column(String(64), primary_key=True)
    CreatorId = Column(String(64), comment='创建者id')
    CreatorType = Column(String(20), comment='创建者类型')
    PRname = Column(String(256), nullable=False, comment='商品名')
    PRimg = Column(Text, url=True, comment='封面图')
    PRtimeLimeted = Column(Integer, default=0, comment='是否为限时商品  0:非限时 1:限时')
    PRissueStartTime = Column(DateTime, comment='开始发放时间')
    PRissueEndTime = Column(DateTime, comment='发放结束时间')
    PRuseStartTime = Column(DateTime, comment='有效使用期开始时间')
    PRuseEndTime = Column(DateTime, comment='有效使用期结束时间')
    PRdetails = Column(Text, comment='商品详情')
    PRlinePrice = Column(DECIMAL(precision=28, scale=2), comment='划线价格')
    PRtruePrice = Column(DECIMAL(precision=28, scale=2), comment='实际价格')
    PRstatus = Column(Integer, default=0, comment='抢票状态 0: 未开始, 1: 发放中, 2: 中止 , 3: 已结束')
    PRnum = Column(Integer, default=1, comment='数量')
    PRbanner = Column(Text, url_list=True, comment='轮播图片')
    SUid = Column(String(64), comment='所属供应商')
    longitude = Column(String(255), comment='经度')
    latitude = Column(String(255), comment='纬度')
    address = Column(Text, comment='游玩场所位置')


class ProductVerifier(Base):
    """
    核销员
    """
    __tablename__ = 'ProductVerifier'
    PVid = Column(String(64), primary_key=True)
    SUid = Column(String(64), comment='供应商')
    PVphone = Column(String(13), nullable=False)
