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

from tickets.config.enums import PayType, ProductStatus, UserCommissionStatus, ApplyFrom, OrderStatus, ApplyStatus
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
    ProductMonthSaleValue, UserDistribute, UserSubCommission, Approval

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

    @token_required
    def mock_distribute_user(self):
        """
        分配
        udinputer: 操作人id
        udinperson: 被执行人id----list
        udexecutor: 管理者id
        """
        data = parameter_required(("inperson_list", "udexecutor"))
        user = UserSubCommission.query.filter(UserSubCommission.isdelete == 0,
                                              UserSubCommission.USid == getattr(request, 'user').id) \
            .first()
        user_super_level = user.USCsuperlevel
        with db.auto_commit():
            for inperson in data.get("inperson_list"):
                if user_super_level == 3:
                    distribute = UserDistribute.create({
                        "UDid": str(uuid.uuid1()),
                        "UDinputer": getattr(request, "user").id,
                        "UDinperson": inperson["usid"],
                        "UDexecutor": data.get("udexecutor")
                    })
                    db.session.add(distribute)
                    user_subcommission_dict = {
                        "USCsupper2": data.get("udexecutor")
                    }
                    user_subcommission = UserSubCommission.query.filter(UserSubCommission.isdelete == 0,
                                                                        UserSubCommission.USid == inperson["usid"])\
                        .first()
                    user_subcommission_entity = UserSubCommission.query.filter(UserSubCommission.isdelete == 0,
                                                                        UserSubCommission.USCid == user_subcommission.USCid)\
                        .first()
                    user_subcommission_entity.update(user_subcommission_dict)
                    db.session.add(user_subcommission_entity)
                elif user_super_level == 2:
                    distribute = UserDistribute.create({
                        "UDid": str(uuid.uuid1()),
                        "UDinputer": getattr(request, "user").id,
                        "UDinperson": inperson["usid"],
                        "UDexecutor": data.get("udexecutor")
                    })
                    db.session.add(distribute)
                    user_subcommission_dict = {
                        "USCsupper1": data.get("udexecutor")
                    }
                    user_subcommission = UserSubCommission.query.filter(UserSubCommission.isdelete == 0,
                                                                        UserSubCommission.USid == inperson["usid"]) \
                        .first()
                    user_subcommission_entity = UserSubCommission.query.filter(UserSubCommission.isdelete == 0,
                                                                               UserSubCommission.USCid == user_subcommission.USCid) \
                        .first()
                    user_subcommission_entity.update(user_subcommission_dict)
                    db.session.add(user_subcommission_entity)
                else:
                    raise StatusError('用户无权限')


        return Success(message="分配成功")

    @token_required
    def get_user_team(self):
        """
        团队管理
        三级用户：从属二级用户头像/昵称/对应从属一级人数
        二级用户：从属一级用户头像/昵称/对应从属普通用户人数
        一级用户：从属普通用户头像/昵称/总订单数
        """
        # data = parameter_required()
        user = UserSubCommission.query.filter(UserSubCommission.isdelete == 0,
                                              UserSubCommission.USid == getattr(request, 'user').id)\
            .first()
        user_super_level = user.USCsuperlevel
        if user_super_level == 3:
            filter_args = [UserSubCommission.isdelete == 0,
                           UserSubCommission.USCsuperlevel == 2,
                           UserSubCommission.USCsupper3 == getattr(request, 'user').id]
        elif user_super_level == 2:
            filter_args = [UserSubCommission.isdelete == 0,
                           UserSubCommission.USCsuperlevel == 1,
                           UserSubCommission.USCsupper2 == getattr(request, 'user').id]
        elif user_super_level == 1:
            filter_args = [UserSubCommission.isdelete == 0,
                           UserSubCommission.USCsuperlevel == 0,
                           UserSubCommission.USCsupper1 == getattr(request, 'user').id]
        else:
            raise StatusError('用户无权限')

        user_team = UserSubCommission.query.filter(*filter_args)\
            .order_by(UserSubCommission.createtime.desc()).all_with_page()
        for user in user_team:
            user_info = User.query.filter(User.isdelete == 0, User.USid == user.USid).first()
            user.fill("usname", user_info.USname)
            user.fill("usheader", user_info.USheader)
            super_level = user.USCsuperlevel
            if super_level == 2:
                super_team = UserSubCommission.query.filter(UserSubCommission.isdelete == 0,
                                                            UserSubCommission.USCsuperlevel == 1,
                                                            UserSubCommission.USCsupper2 == user.USid)\
                    .all()
                user.fill("team_num", len(super_team))
            elif super_level == 1:
                super_team = UserSubCommission.query.filter(UserSubCommission.isdelete == 0,
                                                            UserSubCommission.USCsuperlevel == 0,
                                                            UserSubCommission.USCsupper1 == user.USid) \
                    .all()
                user.fill("team_num", len(super_team))
            elif super_level == 0:
                # TODO 总订单数
                order_list = OrderMain.query.filter(OrderMain.USid == user.USid,
                                                    OrderMain.isdelete == 0,
                                                    OrderStatus in [10, 20])\
                    .all()
                user.fill("order_list", len(order_list))
            else:
                pass

        return Success(message="获取团队信息成功", data=user_team)

    @token_required
    def get_subcommision_index(self):
        """
        团队数据
        总订单数
        总收益
        今日订单数
        今日收益
        今日邀请人数
        """
        subcommision_index = {}
        # 总收益
        user_total_commision = 0
        user_commision_list = UserCommission.query.filter(UserCommission.isdelete == 0,
                                                           UserCommission.USid == getattr(request, 'user').id,
                                                           UserCommission.CommisionFor == 20,
                                                           UserCommission.UCstatus == 1,
                                                           UserCommission.UCtype == 0)\
            .all()
        for user_commision in user_commision_list:
            user_total_commision = user_total_commision + user_commision.UCcommission
        subcommision_index["user_total_commision"] = user_total_commision
        # 今日收益
        user_today_commision = 0
        user_commision_todsy_list = UserCommission.query.filter(UserCommission.isdelete == 0,
                                                          UserCommission.USid == getattr(request, 'user').id,
                                                          UserCommission.CommisionFor == 20,
                                                          UserCommission.UCstatus == 1,
                                                          UserCommission.UCtype == 0,
                                                          cast(UserCommission.createtime, Date) == datetime.now().date())\
            .all()
        for user_commision in user_commision_todsy_list:
            user_today_commision = user_today_commision + user_commision.UCcommission
        subcommision_index["user_today_commision"] = user_today_commision

        # trans: 目前分佣逻辑下，订单会创造收益，实时到账，所以直接按照收益条数计算
        # 总订单数
        subcommision_index["user_total_order"] = len(user_commision_list)
        # 今日订单数
        subcommision_index["user_today_order"] = len(user_commision_todsy_list)

        # 今日邀请人数
        user_today = User.query.filter(User.isdelete == 0,
                                       User.USsupper1 == getattr(request, 'user').id,
                                       cast(User.createtime, Date) == datetime.now().date()).all()
        subcommision_index["user_today"] = len(user_today)

        return Success(message="获取营销数据成功", data=subcommision_index)

    @token_required
    def get_share_list(self):
        """
        人员分配列表
        三级用户：从属一级用户头像/昵称
        二级用户：从属普通用户头像/昵称
        """
        user = UserSubCommission.query.filter(UserSubCommission.isdelete == 0,
                                              UserSubCommission.USid == getattr(request, 'user').id) \
            .first()
        user_super_level = user.USCsuperlevel
        if user_super_level == 3:
            filter_args = [UserSubCommission.isdelete == 0,
                           UserSubCommission.USCsuperlevel == 1,
                           UserSubCommission.USCsupper3 == getattr(request, 'user').id,
                           UserSubCommission.USCsupper2.is_(None)]
        elif user_super_level == 2:
            filter_args = [UserSubCommission.isdelete == 0,
                           UserSubCommission.USCsuperlevel == 0,
                           UserSubCommission.USCsupper2 == getattr(request, 'user').id,
                           UserSubCommission.USCsupper1.is_(None)]
        else:
            raise StatusError('用户无权限')

        user_team = UserSubCommission.query.filter(*filter_args) \
            .order_by(UserSubCommission.createtime.desc()).all_with_page()
        for user in user_team:
            user_info = User.query.filter(User.isdelete == 0, User.USid == user.USid).first()
            user.fill("usname", user_info.USname)
            user.fill("usheader", user_info.USheader)

        return Success(message="获取待分配信息成功", data=user_team)

    def get_distribute_list(self):
        """
        待分配列表
        三级用户：从属二级用户头像/昵称/对应从属一级用户数
        二级用户：从属一级用户头像/昵称/对应从属普通用户数
        """
        user = UserSubCommission.query.filter(UserSubCommission.isdelete == 0,
                                              UserSubCommission.USid == getattr(request, 'user').id) \
            .first()
        user_super_level = user.USCsuperlevel
        if user_super_level == 3:
            filter_args = [UserSubCommission.isdelete == 0,
                           UserSubCommission.USCsuperlevel == 2,
                           UserSubCommission.USCsupper3 == getattr(request, 'user').id]
        elif user_super_level == 2:
            filter_args = [UserSubCommission.isdelete == 0,
                           UserSubCommission.USCsuperlevel == 1,
                           UserSubCommission.USCsupper2 == getattr(request, 'user').id]
        else:
            raise StatusError('用户无权限')

        user_team = UserSubCommission.query.filter(*filter_args) \
            .order_by(UserSubCommission.createtime.desc()).all_with_page()

        for user in user_team:
            user_info = User.query.filter(User.isdelete == 0, User.USid == user.USid).first()
            user.fill("usname", user_info.USname)
            user.fill("usheader", user_info.USheader)
            if user_super_level == 3:
                super_team = UserSubCommission.query.filter(UserSubCommission.isdelete == 0,
                                                            UserSubCommission.USCsupper3 == getattr(request, 'user').id,
                                                            UserSubCommission.USCsupper2 == user.USid,
                                                            UserSubCommission.USCsuperlevel == 1).all()
            elif user_super_level == 2:
                super_team = UserSubCommission.query.filter(UserSubCommission.isdelete == 0,
                                                            UserSubCommission.USCsupper2 == getattr(request, 'user').id,
                                                            UserSubCommission.USCsupper1 == user.USid,
                                                            UserSubCommission.USCsuperlevel == 0).all()
            else:
                super_team = []

            user.fill("team_number", len(super_team))

        return Success(message="获取待分配列表成功", data=user_team)

    @token_required
    def get_approval_list(self):
        """
        升级审核列表
        仅三级用户
        头像/昵称/一级人员数目/审核结果
        """
        if is_user():
            approval_list = Approval.query.filter(Approval.isdelete == 0,
                                             Approval.AVcontent == getattr(request, 'user').id,
                                             Approval.AVstatus == 0,
                                             Approval.PTid == 'touplevel')\
                .all_with_page()
        elif is_admin():
            data = parameter_required(('avstatus'))
            filter_args = [Approval.isdelete == 0, Approval.PTid == 'touplevel']
            if data.get("avstatus") == 'all':
                pass
            else:
                avstatus = ApplyStatus(data.get('avstatus')).value
                filter_args.append(Approval.AVstatus == avstatus)
            approval_list = Approval.query.filter(*filter_args) \
                .all_with_page()
        else:
            raise StatusError("用户无权限")
        for approval in approval_list:
            user = User.query.filter(User.USid == approval.AVstartid, User.isdelete == 0).first()
            approval.fill("usname", user.USname)
            approval.fill("usheader", user.USheader)
            super_team = UserSubCommission.query.filter(UserSubCommission.isdelete == 0,
                                                        UserSubCommission.USCsupper1 == getattr(request, 'user').id,
                                                        UserSubCommission.USCsuperlevel == 1).all()
            approval.fill("team_number", len(super_team))

        return Success(message="获取审批流列表成功", data=approval_list)

    def mock_approval(self):
        """
        审批升级情况
        """
        # TODO 天亮以后再继续
        return Success(message="审批成功")


    # TODO 升级-定时任务
    # TODO 降级-定时任务
    # TODO 奖励-定时任务