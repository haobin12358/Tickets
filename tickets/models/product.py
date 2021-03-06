from sqlalchemy import String, Text, DateTime, DECIMAL, Integer, orm, BIGINT

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
    PRlinePrice = Column(DECIMAL(precision=28, scale=2), default=0, comment='划线价格')
    PRtruePrice = Column(DECIMAL(precision=28, scale=2), default=0, comment='实际价格')
    PurchasePrice = Column(DECIMAL(precision=28, scale=2), default=0, comment='采购价')  # 0702增加
    PRstatus = Column(Integer, default=0, comment='抢票状态 0: 未开始, 1: 发放中, 2: 中止 , 3: 已结束')
    PRnum = Column(Integer, default=1, comment='数量')
    PRbanner = Column(Text, url_list=True, comment='轮播图片')
    SUid = Column(String(64), comment='所属供应商')
    longitude = Column(String(255), comment='经度')
    latitude = Column(String(255), comment='纬度')
    address = Column(Text, comment='游玩场所位置')


class ProductMonthSaleValue(Base):
    """商品月销量"""
    __tablename__ = 'ProductMonthSaleValue'
    PMSVid = Column(String(64), primary_key=True)
    PRid = Column(String(64), nullable=False, comment='商品id')
    PMSVnum = Column(BIGINT, default=0)
    PMSVfakenum = Column(BIGINT, default=0)

    @orm.reconstructor
    def __init__(self):
        super(ProductMonthSaleValue, self).__init__()
        self.hide('PMSVfakenum')
        if isinstance(self.PMSVnum, int) and isinstance(self.PMSVfakenum, int):
            self.PMSVnum = max(self.PMSVnum, self.PMSVfakenum)


class Activation(Base):
    """
    活跃度
    """
    __tablename__ = 'Activation'
    ATid = Column(String(64), primary_key=True)
    USid = Column(String(64))
    ATTid = Column(String(64), comment='活跃度类型：分享新用户,分享老用户,发布内容,加精,打赏,提交联动平台账号')
    ATnum = Column(Integer, default=0, comment='活跃度')


class ActivationType(Base):
    """
    活跃度类型
    """
    __tablename__ = 'ActivationType'
    ATTid = Column(String(64), primary_key=True, comment='该id需要脚本生成固定id')
    ATTname = Column(String(256), comment='获取积分方式简述')
    ATTnum = Column(Integer, default=0, comment='该获取方式获取的活跃度')
    ATTupperLimit = Column(Integer, default=0, comment='该获取方式获取的活跃度上限')
    ATTdayUpperLimit = Column(Integer, default=0, comment='该获取方式每日获取的活跃度上限')
    # ATTtype = Column(Integer, default=0, comment='是否信息绑定')
    # ATTicon = Column(Text, comment='信息绑定的icon')
    ADid = Column(String(64), comment='创建管理员id')

    @orm.reconstructor
    def __init__(self):
        super(ActivationType, self).__init__()
        self.hide('ADid')


class ProductOrderActivation(Base):
    """
    门票订单活跃度关联表
    """
    __tablename__ = 'ProductOrderActivation'
    POAid = Column(String(64), primary_key=True)
    OMid = Column(String(64), comment='订单')
    ATid = Column(String(64), comment='活跃度')
    POAcontent = Column(String(64), comment='如果是随笔，随笔实体id 分享： 分享人id 加精/打赏： 管理员id')


class ProductVerifier(Base):
    """
    核销员
    """
    __tablename__ = 'ProductVerifier'
    PVid = Column(String(64), primary_key=True)
    SUid = Column(String(64), comment='供应商')
    PVphone = Column(String(13), nullable=False)


class ProductVerifiedRecord(Base):
    """核销记录"""
    __tablename__ = 'ProductVerifiedRecord'
    PVRid = Column(String(64), primary_key=True)
    ownerId = Column(String(64), comment='门票持有者id')
    VerifierId = Column(String(64), comment='验证人员id')
    OMid = Column(String(64), comment='订单id')
    param = Column(Text, comment='扫描到的原参数')


class Agreement(Base):
    """规则/协议"""
    __tablename__ = 'Agreement'
    AMid = Column(String(64), primary_key=True)
    AMcontent = Column(Text, comment='协议内容')
    AMtype = Column(Integer, default=0, comment='协议类型 0:转让协议 1: 退款规则 2：门票规则 3：活跃分规则')
    AMname = Column(String(256), comment='规则名')
