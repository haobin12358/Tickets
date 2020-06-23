# -*- coding: utf-8 -*-
from sqlalchemy import Integer, String, Text, Boolean, DateTime, DECIMAL, orm
from sqlalchemy.dialects.mysql import LONGTEXT
from tickets.extensions.base_model import Base, Column


class User(Base):
    """
    用户表
    """
    __tablename__ = "User"
    USid = Column(String(64), primary_key=True)
    USname = Column(String(255), nullable=False, comment='用户名')
    UScustomizeName = Column(String(255), comment='自定义昵称')
    USrealname = Column(String(255), comment='用户真实姓名')
    UStelephone = Column(String(13), comment='手机号')
    USgender = Column(Integer, default=2, comment='性别 {0:unknown, 1: male, 2: famale')
    USbirthday = Column(DateTime, comment='出生日期')
    UScustomizeBirthday = Column(DateTime, comment='自定义生日')
    USareaId = Column(String(64), comment='用户自定义地区')
    UScustomizeHeader = Column(Text, url=True, comment='用户自定义头像')
    USidentification = Column(String(24), comment='身份证号')
    USheader = Column(Text, default='用户头像', url=True)
    USopenid1 = Column(Text, comment='小程序 openid')
    USopenid2 = Column(Text, comment='服务号 openid')
    USopenid3 = Column(Text, comment='blog网页 openid')
    USunionid = Column(Text, comment='统一unionID')
    USsupper1 = Column(String(64), comment='一级代理商id')
    USsupper2 = Column(String(64), comment='二级代理商id')
    USsupper3 = Column(String(64), comment='三级代理商id')
    USCommission1 = Column(DECIMAL(scale=2), comment='当用户作为一级时, 佣金分成')  # 一级佣金分成比例
    USCommission2 = Column(DECIMAL(scale=2), comment='佣金分成')  # 二级佣金分成比例
    USCommission3 = Column(DECIMAL(scale=2), comment='佣金分成')  # 三级佣金分成比例
    USintegral = Column(Integer, default=0, comment='积分')
    USlevel = Column(Integer, default=1, comment='等级 {1：普通用户}')
    USwxacode = Column(Text, url=True, comment='用户小程序码')
    USplayName = Column(String(255), comment='小程序伪真实姓名')
    USminiLevel = Column(Integer, default=0, comment='小程序等级')

    @orm.reconstructor
    def __init__(self):
        super(User, self).__init__()
        self.hide('UScustomizeName', 'UScustomizeBirthday', 'UScustomizeHeader')
        self.USname = self.UScustomizeName or self.USname
        self.USbirthday = self.UScustomizeBirthday or self.USbirthday
        self.USheader = self.UScustomizeHeader or self.USheader


class UserLoginTime(Base):
    __tablename__ = 'UserLoginTime'
    ULTid = Column(String(64), primary_key=True)
    USid = Column(String(64), nullable=False, comment='用户id')
    USTip = Column(String(64), comment='登录ip地址')
    ULtype = Column(Integer, default=1, comment='登录用户类型 1: 用户，2 管理员')
    OSVersion = Column(String(25), comment='手机系统版本')
    PhoneModel = Column(String(16), comment='手机型号')
    WechatVersion = Column(String(16), comment='微信版本')
    NetType = Column(String(10), comment='用户网络')
    UserAgent = Column(Text, comment='浏览器User-Agent')


class UserAccessApi(Base):
    """记录访问api的信息"""
    __tablename__ = 'UserAccessApi'
    UAAid = Column(String(64), primary_key=True)
    USid = Column(String(64), nullable=False, comment='用户id')
    ULA = Column(String(64), comment='请求api地址')
    USTip = Column(String(64), comment='登录ip地址')
    OSVersion = Column(String(25), comment='手机系统版本')
    PhoneModel = Column(String(16), comment='手机型号')
    WechatVersion = Column(String(16), comment='微信版本')
    NetType = Column(String(10), comment='用户网络')


class UserLocation(Base):
    __tablename__ = 'UserLocation'
    ULid = Column(String(64), primary_key=True)
    ULformattedAddress = Column(Text, comment='预测地址')
    ULcountry = Column(Text, comment='国家')
    ULprovince = Column(Text, comment='身份')
    ULcity = Column(Text, comment='城市')
    ULdistrict = Column(Text, comment='区县')
    ULresult = Column(Text, comment='查询结果')
    ULlng = Column(Text, comment='维度')
    ULlat = Column(Text, comment='经度')
    USid = Column(String(64), comment='用户id')


class UserMedia(Base):
    """
    用户身份证图片表
    """
    __tablename__ = 'UserMedia'
    UMid = Column(String(64), primary_key=True)
    USid = Column(String(64), comment='用户id')
    UMurl = Column(Text, url=True, comment='图片路径')
    UMtype = Column(Integer, default=1, comment='图片类型 1: 身份证正面, 2: 身份证反面')


class IDCheck(Base):
    """实名认证查询"""
    __tablename__ = 'IDcheck'
    IDCid = Column(String(64), primary_key=True)
    IDCcode = Column(String(24), nullable=False, comment='查询所用的身份证')
    IDCname = Column(Text, comment='查询所用的姓名')
    IDCresult = Column(Boolean, default=False, comment='查询结果')
    IDCrealName = Column(Text, comment='查询结果里的真实姓名')
    IDCcardNo = Column(Text, comment='查询结果的真实身份证')
    IDCaddrCode = Column(Text, comment='查询结果的地区编码')
    IDCbirth = Column(Text, comment='生日')
    IDCsex = Column(Integer, comment='性别')
    IDCcheckBit = Column(String(2), comment='身份证最后一位')
    IDCaddr = Column(Text, comment='查询结果的地址信息，精确到县')
    IDCerrorCode = Column(String(8), comment='查询结果code')
    IDCreason = Column(Text, comment='查询结果')


class UserIntegral(Base):
    """用户积分表 """
    __tablename__ = 'UserIntegral'
    UIid = Column(String(64), primary_key=True)
    USid = Column(String(64), comment='用户id')
    UIintegral = Column(Integer, comment='该动作产生的积分变化数')
    UIaction = Column(Integer, default=1, comment='积分变动原因 1 转发')
    UItype = Column(Integer, default=1, comment='积分变动类型 1 收入 2 支出')


class AddressProvince(Base):
    """省"""
    __tablename__ = 'AddressProvince'
    APid = Column(String(8), primary_key=True, comment='省id')
    APname = Column(String(20), nullable=False, comment='省名')


class AddressCity(Base):
    """市"""
    __tablename__ = 'AddressCity'
    ACid = Column(String(8), primary_key=True, comment='市id')
    ACname = Column(String(20), nullable=False, comment='市名')
    APid = Column(String(8), nullable=False, comment='省id')


class AddressArea(Base):
    """区县"""
    __tablename__ = 'AddressArea'
    AAid = Column(String(8), primary_key=True, comment='区县id')
    AAname = Column(String(32), nullable=False, comment='区县名')
    ACid = Column(String(8), nullable=False, comment='市名')


class UserInvitation(Base):
    """用户邀请记录表"""
    __tablename__ = 'UserInvitation'
    UINid = Column(String(64), primary_key=True)
    USInviter = Column(String(64), comment='邀请人')
    USInvited = Column(String(64), comment='被邀请人')
    UINapi = Column(String(100), comment='触发此次记录的api')


class UserWallet(Base):
    """用户钱包"""
    __tablename__ = 'UserWallet'
    UWid = Column(String(64), primary_key=True)
    USid = Column(String(64), comment='用户id')
    CommisionFor = Column(Integer, default=20, comment='0 平台, 10 供应商, 20 普通用户')
    UWbalance = Column(DECIMAL(precision=28, scale=2), comment='用户账户余额')
    UWtotal = Column(DECIMAL(precision=28, scale=2), comment='用户账户总额')
    UWcash = Column(DECIMAL(precision=28, scale=2), comment='用户账号可提现余额')
    UWexpect = Column(DECIMAL(precision=28, scale=2), comment='用户账号预期到账金额')


class CashNotes(Base):
    """用户提现记录"""
    __tablename__ = 'CashNotes'
    CNid = Column(String(64), primary_key=True)
    USid = Column(String(64), comment='用户id')
    CommisionFor = Column(Integer, default=20, comment='0 平台, 10 供应商, 20 普通用户')
    CNbankName = Column(Text, comment='开户行')
    CNbankDetail = Column(Text, comment='开户网点详情')
    CNcardNo = Column(String(32), comment='卡号')
    CNcashNum = Column(DECIMAL(precision=28, scale=2), comment='提现金额')
    CNcardName = Column(String(32), comment='开户人')
    CNstatus = Column(Integer, default=0, comment='提现状态 0: 审核中, 1: 审核通过, -1:拒绝')
    CNrejectReason = Column(Text, comment='拒绝理由')
    ApplyPlatform = Column(Integer, comment='申请来源平台 {1：服务号 2：小程序 3：移动端}')


class CashFlow(Base):
    """提现流水"""
    __tablename__ = 'CashFlow'
    CFWid = Column(String(64), primary_key=True)
    CNid = Column(String(64), nullable=False, comment='提现申请id')
    partner_trade_no = Column(String(64), comment='微信商户订单号')
    response = Column(Text, comment='微信返回的原数据')
    status = Column(String(64), comment="代付订单状态：PROCESSING, SUCCESS, FAILED, BANK_FAIL")
    reason = Column(Text, comment='失败原因')
    amout = Column(Integer, comment='提现金额(单位：分)')
    cmms_amt = Column(Integer, default=0, comment='手续费, 提现到银行卡产生(单位：分)')
    CFWfrom = Column(Integer, default=0, comment='提现渠道 0, 微信零钱 1, 银行卡')


class CoveredCertifiedNameLog(Base):
    """覆盖已认证姓名记录表"""
    __tablename__ = 'CoveredCertifiedNameLog'
    CNLid = Column(String(64), primary_key=True)
    OldName = Column(String(255), comment='原真实姓名')
    NewName = Column(String(255), comment='替换后真实姓名')
    OldIdentityNumber = Column(String(64), comment='原身份证号')
    NewIdentityNumber = Column(String(64), comment='替换后身份证号')


class SharingParameters(Base):
    """短分享参数"""
    __tablename__ = 'SharingParameters'
    SPSid = Column(Integer, autoincrement=True, primary_key=True, comment='主键，同时作为缩短的参数')
    USid = Column(String(64), comment='用户id')
    SPScontent = Column(Text, comment='分享的原参数')
    SPSname = Column(String(30), comment='分享的参数名 如: secret_usid, plid')


class SharingType(Base):
    """分享类型"""
    __tablename__ = 'SharingType'
    STid = Column(String(64), primary_key=True)
    USid = Column(String(64), comment='')
    STtype = Column(Integer, default=0, comment='分享类型')


class Admin(Base):
    """
    管理员
    """
    __tablename__ = 'Admin'
    ADid = Column(String(64), primary_key=True)
    ADnum = Column(Integer, autoincrement=True)
    ADname = Column(String(255), comment='管理员名')
    ADtelephone = Column(String(13), comment='管理员联系电话')
    ADpassword = Column(Text, nullable=False, comment='密码')
    ADfirstpwd = Column(Text, comment=' 初始密码 明文保存')
    ADfirstname = Column(Text, comment=' 初始用户名')
    ADheader = Column(Text, comment='头像', url=True)
    ADlevel = Column(Integer, default=2, comment='管理员等级，{1: 超级管理员, 2: 普通管理员}')
    ADstatus = Column(Integer, default=0, comment='账号状态，{0:正常, 1: 被冻结, 2: 已删除}')


class AdminActions(Base):
    """
    记录管理员行为
    """
    __tablename__ = 'AdminAction'
    AAid = Column(String(64), primary_key=True)
    ADid = Column(String(64), comment='管理员id')
    AAaction = Column(Integer, default=1, comment='管理员行为, {1: 添加, 2: 删除 3: 修改}')
    AAmodel = Column(String(255), comment='操作的数据表')
    AAdetail = Column(LONGTEXT, comment='请求的data')
    AAkey = Column(String(255), comment='操作数据表的主键的值')


class AdminNotes(Base):
    """
    管理员变更记录
    """
    __tablename__ = 'AdminNotes'
    ANid = Column(String(64), primary_key=True)
    ADid = Column(String(64), nullable=False, comment='管理员id')
    ANaction = Column(Text, comment='变更动作')
    ANdoneid = Column(String(64), comment='修改人id')


class Supplizer(Base):
    """供应商"""
    __tablename__ = 'Supplizer'
    SUid = Column(String(64), primary_key=True)
    SUloginPhone = Column(String(11), nullable=False, index=True, unique=True, comment='登录手机号')
    SUlinkPhone = Column(String(11), default=SUloginPhone, comment='供应商联系电话')
    SUname = Column(String(32), default=SUlinkPhone, comment='供应商名字')
    SUlinkman = Column(String(16), nullable=False, comment='供应商联系人')
    SUaddress = Column(String(255), nullable=False, comment='供应商地址')
    SUstatus = Column(Integer, default=0, comment='状态: 10 待审核 0 正常 -10 禁用')
    SUdeposit = Column(DECIMAL(precision=28, scale=2), comment='供应商押金')
    SUbanksn = Column(String(32), comment='卡号')
    SUbankname = Column(String(64), comment='银行')
    SUpassword = Column(String(255), comment='供应商密码密文')
    SUheader = Column(String(255), comment='头像', url=True)
    SUcontract = Column(Text, url_list=True, comment='合同列表')
    SUbusinessLicense = Column(Text, url=True, comment='营业执照')
    SUregisteredFund = Column(String(255), comment='注册资金')
    SUmainCategory = Column(Text, comment='主营类目')
    SUregisteredTime = Column(DateTime, comment='注册时间')
    SUlegalPerson = Column(Text, comment='法人姓名')
    SUemail = Column(String(256), comment='供应商邮箱')
    SUlegalPersonIDcardFront = Column(Text, url=True, comment='法人身份证正面')
    SUlegalPersonIDcardBack = Column(Text, url=True, comment='法人身份证正面')
    SUgrade = Column(Integer, default=1, comment='供应商类型 0：普通货物， 1：虚拟商品供应商')


class SupplizerAccount(Base):
    """供应商账户信息表"""
    __tablename__ = 'SupplizerAccount'
    SAid = Column(String(64), primary_key=True)
    SUid = Column(String(64), comment='供应商id')
    SAbankName = Column(Text, comment='开户行')
    SAbankDetail = Column(Text, comment='开户网点详情')
    SAcardNo = Column(String(32), comment='卡号')
    SAcardName = Column(Text, comment='开户人')
    SACompanyName = Column(Text, comment='公司名')
    SAICIDcode = Column(Text, comment='纳税识别码')
    SAaddress = Column(Text, comment='地址电话')
    SAbankAccount = Column(Text, comment='开票信息的银行账户')
