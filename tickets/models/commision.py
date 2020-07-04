import json

from sqlalchemy import String, DECIMAL, Integer

from tickets.extensions.base_model import Base, Column
from tickets.extensions.error_response import StatusError


class Commision(Base):
    __tablename__ = 'Commision'
    COid = Column(String(64), primary_key=True)
    Levelcommision = Column(String(32), default='["0", "0", "0", "0"]', comment='佣金比例: 1级, 2级, 3级, 平台')
    # 升级相关
    InviteNum = Column(Integer, default=0, comment='升级所需人数')
    GroupSale = Column(DECIMAL(precision=28, scale=2), comment='升级所需团队总额')
    PesonalSale = Column(DECIMAL(precision=28, scale=2), comment='升级所需个人总额')
    InviteNumScale = Column(DECIMAL(scale=2), default=1, comment='下次升级/上次升级 比例')
    GroupSaleScale = Column(DECIMAL(scale=2), default=1, comment='下次升级/上次升级 比例')
    PesonalSaleScale = Column(DECIMAL(scale=2), default=1, comment='下次升级/上次升级 比例')
    # 级差相关
    ReduceRatio = Column(String(32), default='["0", "0", "0", "0"]', comment='级差减额, 共四级')
    IncreaseRatio = Column(String(32), default='["0", "0", "0", "0"]', comment='级差增额')

    # 平台统一供应商让利比
    DevideRate = Column(DECIMAL(scale=2), comment='平台统一供应商佣金比')

    # 升级规则
    LevelUpTwo = Column(Integer, default=0, comment='一级升二级要求人数')
    LevelUpThree = Column(Integer, default=0, comment='二级升三级要求人数')

    # 降级规则
    LevelDownTwo = Column(Integer, default=0, comment='三级降二级考核人数')
    LevelDownOne = Column(Integer, default=0, comment='二级降一级考核人数')
    LevelDownZero = Column(Integer, default=0, comment='三级降二级考核人数')
    LevelDownTwoRep = Column(Integer, default=0, comment='三级降二级考核人数可替代')
    LevelDownOneRep = Column(Integer, default=0, comment='二级降一级考核人数可替代')
    LevelDownZeroRep = Column(Integer, default=0, comment='三级降二级考核人数可替代')

    # 奖励规则
    LevelUpTwoReward = Column(DECIMAL(scale=2), default=0, comment='升二级奖励')
    LevelUpThreeReward = Column(DECIMAL(scale=2), default=0, comment='升三级奖励')

    # 考核周期
    CheckTime = Column(Integer, default=7, comment='考核周期，单位：天')

    @classmethod
    def devide_rate_baseline(cls):
        commision = cls.query.filter(cls.isdelete == False).first()
        if commision:
            level_commision = json.loads(commision.Levelcommision)
            return level_commision[-1]
        raise StatusError('项目需要初始化')

    @classmethod
    def level_commisions(cls):
        commision = cls.query.filter(cls.isdelete == False).first()
        if commision:
            level_commision = json.loads(commision.Levelcommision)
            return level_commision
        raise StatusError('项目需要初始化')


