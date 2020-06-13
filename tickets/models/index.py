from sqlalchemy import Boolean, String, Integer, Text
from sqlalchemy.dialects.mysql import LONGTEXT

from tickets.extensions.base_model import Base, Column


class MiniProgramBanner(Base):
    """小程序轮播图"""
    __tablename__ = 'MiniProgramBanner'
    MPBid = Column(String(64), primary_key=True)
    ADid = Column(String(64), comment='创建者id')
    MPBpicture = Column(Text, nullable=False, comment='图片', url=True)
    MPBsort = Column(Integer, comment='顺序')
    MPBshow = Column(Boolean, default=True, comment='是否展示')
    MPBposition = Column(Integer, default=0, comment='轮播图位置 0: 首页, 1: 出游')
    contentlink = Column(LONGTEXT, comment='跳转链接')


class LinkContent(Base):
    """轮播图链接富文本"""
    __tablename__ = 'LinkContent'
    LCid = Column(String(64), primary_key=True)
    LCcontent = Column(LONGTEXT, comment='富文本详情')
