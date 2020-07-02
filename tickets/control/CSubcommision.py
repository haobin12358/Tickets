"""
本文件用于设计分销逻辑
createtime: 2020/6/26
by:haobin12358
"""
import json
import os
import random
import re
import time
import uuid
from datetime import datetime, date, timedelta
from decimal import Decimal

from flask import request, current_app
from sqlalchemy import false, cast, Date, func, extract

from tickets.config.enums import PayType, ProductStatus, UserCommissionStatus, ApplyFrom, OrderStatus, WexinBankCode
from tickets.config.http_config import API_HOST
from tickets.config.timeformat import format_for_web_second, format_forweb_no_HMS
from tickets.extensions.error_response import ParamsError, StatusError, AuthorityError
from tickets.extensions.interface.user_interface import is_user, is_admin, token_required, phone_required, is_supplizer
from tickets.extensions.make_qrcode import qrcodeWithtext
from tickets.extensions.params_validates import parameter_required
from tickets.extensions.register_ext import db, mini_wx_pay
from tickets.extensions.success_response import Success
from tickets.extensions.tasks import add_async_task, auto_cancle_order
from tickets.extensions.weixin.pay import WeixinPayError
from tickets.extensions.register_ext import qiniu_oss
from tickets.models import User, Product, UserWallet, Commision, OrderPay, OrderMain, UserCommission, Supplizer, \
    ProductMonthSaleValue, UserDistribute, UserSubCommission

class CSubcommision():

    def _mock_first_login(self, usid):
        """
        只有新用户登录时操作
        1.models.User insert数据（含分销人员）
        2.models.User update上级分销人员models.User.USsuperlevel值为1
        3.调用本方法获得分佣各级对应人员
        """
        user_sub_commision = {
            "USCsupper1": None,
            "USCsupper2": None,
            "USCsupper3": None
        }
        user = User.query.filter(User.USid == usid).first_("未找到用户")
        # TODO 后期普通用户升级为一级规则调整后需要修改
        supper = user.USsupper1
        if not supper:
            # 无分销者，野人模式
            return user_sub_commision
        else:
            # 上级分销人员
            supper_user = User.query.filter(User.USid == supper).first_("未找到用户")
            level = supper_user.USsuperlevel
            if level == 1:
                user_sub_commision["USCsupper1"] = supper
                # 一级分佣人员的上级分销者id
                supper2 = supper_user.USsupper1
                if not supper2:
                    # 无上级分销者
                    return user_sub_commision
                else:
                    # 循环寻找二级分佣人员
                    while supper_user.USsuperlevel == 2 or not supper2:
                        supper_user = User.query.filter(User.USid == supper2).first()
                        if supper_user.USsuperlevel == 2:
                            user_sub_commision["USCsupper2"] = supper2
                        supper2 = supper_user.USsupper1

                    # 判断二级分佣人员是否存在
                    if not user_sub_commision["USCsupper2"]:
                        return user_sub_commision
                    else:
                        supper3 = supper_user.USsupper1
                        # 循环寻找三级分佣人员
                        while supper_user.USsuperlevel == 3 or not supper3:
                            supper_user = User.query.filter(User.USid == supper3).first()
                            if supper_user.USsuperlevel == 3:
                                user_sub_commision["USCsupper3"] = supper3
                            supper3 = supper_user.USsupper1
            elif level == 2:
                user_sub_commision["USCsupper2"] = supper
                supper3 = supper_user.USsupper1
                if not supper3:
                    # 无上级分销者
                    return user_sub_commision
                else:
                    # 循环寻找三级分佣人员
                    while supper_user.USsuperlevel == 3 or not supper3:
                        supper_user = User.query.filter(User.USid == supper3).first()
                        if supper_user.USsuperlevel == 3:
                            user_sub_commision["USCsupper3"] = supper3
                        supper3 = supper_user.USsupper1
            elif level == 3:
                user_sub_commision["USCsupper3"] = supper
            else:
                pass
            return user_sub_commision

    def _mock_distribute_user(self, udinputer, udinperson, udexecutor):
        """
        udinputer: 操作人id
        udinperson: 被执行人id
        udexecutor: 管理者id
        """
        