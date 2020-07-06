from sqlalchemy import String, Boolean, Integer, DECIMAL, DateTime, Text

from tickets.extensions.base_model import Base, Column


class OrderMain(Base):
    """
    订单主单, 下单时每种品牌单独一个订单, 但是一并付费
    """
    __tablename__ = 'OrderMain'
    OMid = Column(String(64), primary_key=True)
    OMno = Column(String(64), nullable=False, comment='订单编号')
    OPayno = Column(String(64), comment='付款流水号,与orderpay对应')  # 之前适配一次支付多订单参数。目前沿用以便后续更迭
    USid = Column(String(64), nullable=False, comment='用户id')
    # UseCoupon = Column(Boolean, default=False, comment='是否优惠券')
    # OMfrom = Column(Integer, default=0, comment='')
    # PBname = Column(String(32), nullable=False, comment='品牌名')
    # PBid = Column(String(64), nullable=False, comment='品牌id')
    # OMclient = Column(Integer, default=0, comment='下单设备: 0: 微信, 10: app')
    # OMfreight = Column(Float, default=0, comment='运费')
    OMmount = Column(DECIMAL(precision=28, scale=2), nullable=False, comment='总价')
    OMtrueMount = Column(DECIMAL(precision=28, scale=2), nullable=False, comment='实际总价')
    OMstatus = Column(Integer, default=1, comment='订单状态')
    OMinRefund = Column(Boolean, default=False, comment='主单是否在售后状态')
    OMmessage = Column(String(255), comment='留言')
    # 收货信息
    OMrecvPhone = Column(String(11), comment='收货电话')  # 前期无收货地址默认都是空
    OMrecvName = Column(String(11), comment='收货人姓名')  # 前期无收货地址默认都是空
    OMrecvAddress = Column(String(255), comment='地址')  # 前期无收货地址默认都是空
    PRcreateId = Column(String(64), comment='发布者id')  # 为商品所属供应商id, 无表示平台
    OMlogisticType = Column(Integer, default=0, comment='发货类型 0 正常发货, 10线上发货(无物流)')  # 前期只有线上发货 默认都是10
    OMintegralpayed = Column(Integer, default=0, comment='获得的活跃分')
    OMpayType = Column(Integer, default=2, comment='支付方式 2 直购 3 活跃分')
    # 上级
    UPperid = Column(String(64), comment='一级分佣者')  # 方便查询下级
    UPperid2 = Column(String(64), comment='二级分佣者')
    UPperid3 = Column(String(64), comment='三级分佣者')
    UPshareid = Column(String(64), comment='分享者id')

    # 商品信息
    # PRattribute = Column(Text, comment='商品属性 ["网络","颜色","存储"]')
    PRid = Column(String(64), nullable=False, comment='商品ID')
    PRname = Column(String(255), nullable=False, comment='商品标题')
    PRimg = Column(String(255), comment='主图', url=True)
    OPnum = Column(Integer, default=1, comment='数量')
    OMqrcode = Column(Text, url=True, comment='二维码')
    # 指定佣金比, 用于活动的自定义设置
    # USCommission1 = Column(DECIMAL(scale=2), comment='一级佣金比')
    # USCommission2 = Column(DECIMAL(scale=2), comment='二级佣金比')
    # USCommission3 = Column(DECIMAL(scale=2), comment='三级佣金比')


class OrderPay(Base):
    """
    付款流水
    """
    __tablename__ = 'OrderPay'
    OPayid = Column(String(64), primary_key=True)
    OPayno = Column(String(64), index=True, comment='交易号, 自己生成')  # 即out_trade_no
    OPayType = Column(Integer, default=0, comment='支付方式 0 微信 10 支付宝 20 活跃分')
    OPaytime = Column(DateTime, comment='付款时间')
    OPayMount = Column(DECIMAL(precision=28, scale=2), comment='付款金额')
    OPaysn = Column(String(64), comment='第三方支付流水')
    OPayJson = Column(Text, comment='回调原文')
    OPaymarks = Column(String(255), comment='备注')


class UserCommission(Base):
    """用户佣金"""
    __tablename__ = 'UserCommission'
    UCid = Column(String(64), primary_key=True)
    UCcommission = Column(DECIMAL(precision=28, scale=2), comment='获取佣金')
    USid = Column(String(64), comment='用户或供应商id 0表示平台')
    CommisionFor = Column(Integer, default=20, comment='0 平台, 10 供应商, 20 普通用户')
    FromUsid = Column(String(64), comment='订单来源用户')
    UCstatus = Column(Integer, default=0, comment='佣金状态{-1: 异常, 0：预期到账, 1: 已到账, 2: 已提现}')
    UCtype = Column(Integer, default=0, comment='收益类型 0：佣金 1：新人商品 2：押金 3:圈子打赏 4: 拼团退款 5:奖励金')
    UCendTime = Column(DateTime, comment='预期到账时间')
    PRname = Column(String(255), comment='商品标题')
    PRimg = Column(Text, url=True, comment='商品封面图')
    OMid = Column(String(64), comment='佣金来源订单')
