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
from tickets.extensions.error_response import ParamsError, StatusError, AuthorityError, LevelStatus
from tickets.extensions.interface.user_interface import is_user, is_admin, token_required, phone_required, is_supplizer
from tickets.extensions.make_qrcode import qrcodeWithtext
from tickets.extensions.params_validates import parameter_required
from tickets.extensions.register_ext import db, mini_wx_pay
from tickets.extensions.success_response import Success
from tickets.extensions.tasks import add_async_task, auto_cancle_order
from tickets.extensions.weixin.pay import WeixinPayError
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
            "USCsuperlevel": 0,
            "USCsupper1": None,
            "USCsupper2": None,
            "USCsupper3": None
        }
        user = User.query.filter(User.USid == usid).first_("未找到用户")
        # TODO 后期普通用户升级为一级规则调整后需要修改
        with db.auto_commit():
            supper = user.USsupper1
            if not supper:
                # 无分销者，野人模式
                db.session.add(user_sub_commision)
                db.session.flush()
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
                sub_commision = UserSubCommission.create(user_sub_commision)
                db.session.add(sub_commision)
                db.session.flush()
        if user_sub_commision["USCsupper1"]:
            self._level_zero_up_one(user_sub_commision["USCsupper1"])

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
                user.fill("team_number", len(super_team))
            elif super_level == 1:
                super_team = UserSubCommission.query.filter(UserSubCommission.isdelete == 0,
                                                            UserSubCommission.USCsuperlevel == 0,
                                                            UserSubCommission.USCsupper1 == user.USid) \
                    .all()
                user.fill("team_number", len(super_team))
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
            data = parameter_required()
            filter_args = [Approval.isdelete == 0, Approval.PTid == 'touplevel']
            avstatus = data.get('avstatus')
            if avstatus and avstatus != 'all':
                try:
                    filter_args.append(Approval.AVstatus == getattr(ApplyStatus, avstatus).value)
                except (AttributeError, ValueError):
                    pass
            approval_list = Approval.query.filter(*filter_args) \
                .all_with_page()
        else:
            raise StatusError("用户无权限")
        for approval in approval_list:
            approval.fill("createtime", approval.createtime)
            user = User.query.filter(User.USid == approval.AVstartid, User.isdelete == 0).first()
            approval.fill("usname", user.USname)
            approval.fill("usheader", user.USheader)
            usersubcommision = UserSubCommission.query.filter(UserSubCommission.USid == approval.AVstartid,
                                                              UserSubCommission.isdelete == 0)\
                .first()
            user_super_level = usersubcommision.USCsuperlevel
            approval.fill("uscsuperlevel", user_super_level)
            if user_super_level == 1:
                super_team = UserSubCommission.query.filter(UserSubCommission.isdelete == 0,
                                                            UserSubCommission.USCsupper1 == getattr(request, 'user').id,
                                                            UserSubCommission.USCsuperlevel == 1).all()
            else:
                super_team = UserSubCommission.query.filter(UserSubCommission.isdelete == 0,
                                                            UserSubCommission.USCsupper2 == getattr(request, 'user').id,
                                                            UserSubCommission.USCsuperlevel == 2).all()
            approval.fill("team_number", len(super_team))
            user_supper3_id = usersubcommision.USCsupper3
            user_supper3 = User.query.filter(User.USid == user_supper3_id, User.isdelete == 0).first()
            approval.fill("user_supper3_name", user_supper3.USname)
            approval.fill("user_supper3_telphone", user_supper3.UStelephone)

        return Success(message="获取审批流列表成功", data=approval_list)

    @token_required
    def mock_approval(self):
        """
        审批升级情况
        """
        # TODO 查看分配列表，有，清理该数据且update分佣表，无pass
        # TODO 查看分佣表，一级分佣位置为该用户的数据update
        # TODO 检测刚才待update数据，二级分佣位置为空pass，二级分佣位置存在数据且分配列表无数据pass，二级分佣位置存在数据且分配列表有数据delete
        # TODO 二级升三级同处理
        data = parameter_required(('avid', 'avstatus', ))
        if data.get('avstatus') == "access":
            with db.auto_commit():
                # 审批通过
                approval_dict = {
                    "AVstatus": 10
                }
                approval = Approval.query.filter(Approval.AVid == data.get('avid'),
                                                 Approval.isdelete == 0,
                                                 Approval.AVstatus == 0) \
                    .first_("该审批流已审批")
                approval_instance = approval.update(approval_dict)
                db.session.add(approval_instance)
                db.session.flush()
                # 处理升级后佣金表和分配表数据
                usid = approval.AVstartid
                user_distribute_list = UserDistribute.query.filter(UserDistribute.UDinperson == usid,
                                                                   UserDistribute.isdelete == 0)\
                    .all()
                for user_distribute in user_distribute_list:
                    user_distribute_dict = {
                        "isdelete": 1
                    }
                    user_distribute.update(user_distribute_dict)
                    db.session.add(user_distribute)
                    db.session.flush()
                # 查看分佣表
                user_sub_commision = UserSubCommission.query.filter(UserSubCommission.USid == usid,
                                                                    UserSubCommission.isdelete == 0)\
                    .first()
                user_super_level = user_sub_commision.USCsuperlevel
                if user_super_level == 1:
                    # TODO 一级位置为usid的用户置空，二级位置设置为usid
                    user_commision_dict = {
                        "USCsupper1": None,
                        "USCsupper2": usid
                    }
                    user_level_zero_list = UserSubCommission.query.filter(UserSubCommission.USCsupper1 == usid,
                                                                          UserSubCommission.isdelete == 0)\
                        .all()
                    for user_level_zero in user_level_zero_list:
                        user_level_zero.update(user_commision_dict)
                        db.session.add(user_level_zero)
                        db.session.flush()
                    # TODO 更新usid的用户level为2
                    user_level_dict = {
                        "USCsuperlevel": 2
                    }
                    user_sub_commision.update(user_level_dict)
                    db.session.add(user_sub_commision)
                    db.session.flush()
                    # TODO 该usid用户的二级用户获得设置的奖金
                    user_commision_config = Commision.query.filter(Commision.isdelete == 0).first()
                    leveluptworeward = user_commision_config.LevelUpTwoReward or 0
                    if leveluptworeward:
                        commision = UserCommission.create({
                            "UCid": str(uuid.uuid1()),
                            "UCcommission": leveluptworeward,
                            "USid": "0",
                            "CommisionFor": 20,
                            "FromUsid": None,
                            "UCstatus": 1,
                            "UCtype": 5,
                            "UCendTime": None,
                            "PRname": None,
                            "PRimg": None,
                            "OMid": None
                        })
                        db.session.add(commision)
                elif user_super_level == 2:
                    # TODO 二级位置为usid的用户置空，三级位置设置为usid
                    user_commision_dict = {
                        "USCsupper2": None,
                        "USCsupper3": usid
                    }
                    user_level_one_list = UserSubCommission.query.filter(UserSubCommission.USCsupper2 == usid,
                                                                          UserSubCommission.isdelete == 0) \
                        .all()
                    for user_level_one in user_level_one_list:
                        user_level_one.update(user_commision_dict)
                        db.session.add(user_level_one)
                        db.session.flush()
                    # TODO 更新usid的用户level为3
                    user_level_dict = {
                        "USCsuperlevel": 3
                    }
                    user_sub_commision.update(user_level_dict)
                    db.session.add(user_sub_commision)
                    db.session.flush()
                    # TODO 该usid用户的三级用户获得设置的奖金
                    user_commision_config = Commision.query.filter(Commision.isdelete == 0).first()
                    levelupthreereward = user_commision_config.LevelUpThreeReward or 0
                    if levelupthreereward:
                        commision = UserCommission.create({
                            "UCid": str(uuid.uuid1()),
                            "UCcommission": Decimal(levelupthreereward, 2),
                            "USid": "0",
                            "CommisionFor": 20,
                            "FromUsid": None,
                            "UCstatus": 1,
                            "UCtype": 5,
                            "UCendTime": None,
                            "PRname": None,
                            "PRimg": None,
                            "OMid": None
                        })
                        db.session.add(commision)
                else:
                    pass

        else:
            with db.auto_commit():
                approval_dict = {
                    "AVstatus": -10
                }
                approval = Approval.query.filter(Approval.AVid == data.get('avid'),
                                                 Approval.isdelete == 0,
                                                 Approval.AVstatus == 0)\
                    .first_("该审批流已审批")
                approval_instance = approval.update(approval_dict)
                db.session.add(approval_instance)
                db.session.flush()
        return Success(message="审批成功")

    @token_required
    def set_user_level(self):
        """
        设置用户等级
        0->3
        1->3
        2->3
        0->2
        0->1
        1->2
        1->0
        2->1
        2->0
        3->2
        3->1
        3->0
        """
        data = parameter_required(('set_level', 'usid', ))
        usid = data.get('usid')
        user_sub_commission = UserSubCommission.query.filter(UserSubCommission.USid == usid,
                                                             UserSubCommission.isdelete == 0)\
            .first()
        user_super_level = user_sub_commission.USCsuperlevel
        set_level = data.get('set_level') or 0
        if user_super_level == 0:
            if set_level == 0:
                return LevelStatus()
            elif set_level == 1:
                self._level_zero_up_one(usid)
            elif set_level == 2:
                self._level_zero_up_two(usid)
            elif set_level == 3:
                self._level_zero_up_three(usid)
            else:
                pass
        elif user_super_level == 1:
            if set_level == 0:
                self._level_one_down_zero(usid)
            elif set_level == 1:
                return LevelStatus()
            elif set_level == 2:
                self._level_one_up_two(usid)
            elif set_level == 3:
                self._level_one_up_three(usid)
            else:
                pass
        elif user_super_level == 2:
            if set_level == 0:
                self._level_two_down_zero(usid)
            elif set_level == 1:
                self._level_two_down_one(usid)
            elif set_level == 2:
                return LevelStatus()
            elif set_level == 3:
                self._level_two_up_three(usid)
            else:
                pass
        elif user_super_level == 3:
            if set_level == 0:
                self._level_three_down_zero(usid)
            elif set_level == 1:
                self._level_three_down_one(usid)
            elif set_level == 2:
                self._level_three_down_two(usid)
            elif set_level == 3:
                return LevelStatus()
            else:
                pass
        else:
            return LevelStatus()

        return Success(message="设置成功")


    def _level_one_up_two(self, usid):
        """
        用户等级从1升为2
        触发升级审批流，交由三级用户审批
        """
        self._mock_approval(usid, 1)

    def _level_zero_up_one(self, usid):
        """
        用户等级从0升为1
        1.update分佣表uscsuperlevel
        2.查看分享者是否为1级
        3.是，查看分享者是否凑够规定人数，如果凑够，触发定时任务，如果未凑够，pass
        4.否，pass
        """
        with db.auto_commit():
            user = UserSubCommission.query.filter(UserSubCommission.USid == usid,
                                                  UserSubCommission.isdelete == 0).first()
            user_subcommission_dict = {
                "USCsuperlevel": 1
            }
            user_subcommission_instance = user.update(user_subcommission_dict)
            db.session.add(user_subcommission_instance)
            db.session.flush()
            ussuper1 = user.USCsupper1
            if ussuper1:
                user_super = UserSubCommission.query.filter(UserSubCommission.USid == ussuper1,
                                                            UserSubCommission.isdelete == 0)\
                    .first()
                user_super_level = user_super.USCsuperlevel
                if user_super_level == 1:
                    super_one_list = UserSubCommission.query.filter(UserSubCommission.USCsupper1 == ussuper1,
                                                                    UserSubCommission.isdelete == 0,
                                                                    UserSubCommission.USCsuperlevel > 0)\
                        .all()
                    commision_configs = Commision.query.filter(Commision.isdelete == 0).first()
                    leveluptwo = commision_configs.LevelUpTwo
                    if len(super_one_list) >= leveluptwo:
                        self._mock_approval(ussuper1, 1)
                else:
                    pass
            else:
                pass

    def _level_zero_up_two(self, usid):
        """
        用户等级从0升为2
        1.update分佣表uscsuperlevel
        2.查看二级分佣人员是否为2级
        3.是，查看分享者是否凑够规定人数，如果凑够，触发定时任务，如果未凑够，pass
        4.否，pass
        """
        with db.auto_commit():
            user = UserSubCommission.query.filter(UserSubCommission.USid == usid,
                                                  UserSubCommission.isdelete == 0)\
                .first()
            user_subcommission_dict = {
                "USCsuperlevel": 2
            }
            user_subcommission_instance = user.update(user_subcommission_dict)
            db.session.add(user_subcommission_instance)
            db.session.flush()
            uscsupper2 = user.USCsupper2
            if uscsupper2:
                user_super = UserSubCommission.query.filter(UserSubCommission.USid == uscsupper2,
                                                            UserSubCommission.isdelete == 0)\
                    .first()
                user_super_level = user_super.USCsuperlevel
                if user_super_level == 2:
                    super_one_list = UserSubCommission.query.filter(UserSubCommission.USCsupper1 == uscsupper2,
                                                                    UserSubCommission.isdelete == 0,
                                                                    UserSubCommission.USCsuperlevel > 0)\
                        .all()
                    commision_configs = Commision.query.filter(Commision.isdelete == 0).first()
                    leveluptwo = commision_configs.LevelUpThree
                    if len(super_one_list) >= leveluptwo:
                        self._mock_approval(uscsupper2, 2)
                else:
                    pass
            else:
                pass

    def _level_zero_up_three(self, usid):
        """
        用户等级从0升为3
        update分佣表uscsuperlevel
        """
        with db.auto_commit():
            user = UserSubCommission.query.filter(UserSubCommission.USid == usid,
                                                  UserSubCommission.isdelete == 0)\
                .first()
            user_subcommission_dict = {
                "USCsuperlevel": 3
            }
            user_subcommission_instance = user.update(user_subcommission_dict)
            db.session.add(user_subcommission_instance)
            db.session.flush()

    def _level_one_up_three(self, usid):
        """
        用户等级从1升为3
        1.update分佣表uscsuperlevel
        2.查看分佣表中所有uscsupper1为usid的数据，更新uscsupper1为空，更新uscsupper2为空，更新uscsupper3为usid
        """
        with db.auto_commit():
            user = UserSubCommission.query.filter(UserSubCommission.USid == usid,
                                                  UserSubCommission.isdelete == 0)\
                .first()
            user_subcommission_dict = {
                "USCsuperlevel": 3

            }
            user_subcommission_instance = user.update(user_subcommission_dict)
            db.session.add(user_subcommission_instance)
            user_subcommission_list_dict = {
                "USCsupper1": None,
                "USCsupper2": None,
                "USCsupper3": usid
            }
            user_subcommission_list = UserSubCommission.query.filter(UserSubCommission.USCsupper1 == usid,
                                                  UserSubCommission.isdelete == 0)\
                .all()
            for user_subcommission in user_subcommission_list:
                user_subcommission.update(user_subcommission_list_dict)
                db.session.add(user_subcommission)
            db.session.flush()

    # 定时任务涉及
    def _level_one_down_zero(self, usid):
        """
        用户等级从1降为0
        1.update分佣表uscsuperlevel
        2.查看分佣表中所有uscsupper1为usid的数据，更新uscsupper1为空
        """
        with db.auto_commit():
            user = UserSubCommission.query.filter(UserSubCommission.USid == usid,
                                                  UserSubCommission.isdelete == 0) \
                .first()
            user_subcommission_dict = {
                "USCsuperlevel": 0

            }
            user_subcommission_instance = user.update(user_subcommission_dict)
            db.session.add(user_subcommission_instance)
            user_subcommission_list_dict = {
                "USCsupper1": None
            }
            user_subcommission_list = UserSubCommission.query.filter(UserSubCommission.USCsupper1 == usid,
                                                                     UserSubCommission.isdelete == 0) \
                .all()
            for user_subcommission in user_subcommission_list:
                user_subcommission.update(user_subcommission_list_dict)
                db.session.add(user_subcommission)
            db.session.flush()

    def _level_two_up_three(self, usid):
        """
        用户等级从2升为3
        """
        self._mock_approval(usid, 2)

    def _level_two_down_zero(self, usid):
        """
        用户等级从2降为0
        1.update分佣表uscsuperlevel
        2.查看分佣表中所有uscsupper2为usid的数据，更新uscsupper2为空
        """
        with db.auto_commit():
            user = UserSubCommission.query.filter(UserSubCommission.USid == usid,
                                                  UserSubCommission.isdelete == 0) \
                .first()
            user_subcommission_dict = {
                "USCsuperlevel": 0

            }
            user_subcommission_instance = user.update(user_subcommission_dict)
            db.session.add(user_subcommission_instance)
            user_subcommission_list_dict = {
                "USCsupper2": None
            }
            user_subcommission_list = UserSubCommission.query.filter(UserSubCommission.USCsupper2 == usid,
                                                                     UserSubCommission.isdelete == 0) \
                .all()
            for user_subcommission in user_subcommission_list:
                user_subcommission.update(user_subcommission_list_dict)
                db.session.add(user_subcommission)
            db.session.flush()

    # 定时任务涉及
    def _level_two_down_one(self, usid):
        """
        用户等级从2降为1
        """
        pass

    # 定时任务涉及
    def _level_three_down_two(self, usid):
        """
        用户等级从3降为2
        """
        pass

    def _level_three_down_one(self, usid):
        """
        用户等级从3降为1
        """
        return LevelStatus()

    def _level_three_down_zero(self, usid):
        """
        用户等级从3降为0
        1.update分佣表uscsuperlevel
        2.查看分佣表中所有uscsupper3为usid的数据，更新uscsupper3为空
        """
        with db.auto_commit():
            user = UserSubCommission.query.filter(UserSubCommission.USid == usid,
                                                  UserSubCommission.isdelete == 0) \
                .first()
            user_subcommission_dict = {
                "USCsuperlevel": 0

            }
            user_subcommission_instance = user.update(user_subcommission_dict)
            db.session.add(user_subcommission_instance)
            user_subcommission_list_dict = {
                "USCsupper3": None
            }
            user_subcommission_list = UserSubCommission.query.filter(UserSubCommission.USCsupper3 == usid,
                                                                     UserSubCommission.isdelete == 0) \
                .all()
            for user_subcommission in user_subcommission_list:
                user_subcommission.update(user_subcommission_list_dict)
                db.session.add(user_subcommission)
            db.session.flush()

    def _mock_approval(self, usid, level):
        """
        触发正常升级审批流
        usid: 发起人id
        level: 发起人等级
        """
        with db.auto_commit():
            approval_dict = {}
            approval_dict["AVid"] = str(uuid.uuid1())
            approval_dict["AVname"] = "touplevel" + datetime.now().strftime('%Y%m%d%H%M%S')
            approval_dict["AVstartid"] = usid
            approval_dict["AVlevel"] = level
            approval_dict["AVstatus"] = 0
            user_sub_commission = UserSubCommission.query.filter(UserSubCommission.USid == usid,
                                                                 UserSubCommission.isdelete == 0)\
                .first()
            if user_sub_commission.USCsuperlevel == 1:
                approval_dict["AVcontent"] = user_sub_commission.USCsupper3 or None
            else:
                approval_dict["AVcontent"] = None
            approval_dict["PTid"] = "touplevel"
            user_sub_commission_instance = Approval.create(approval_dict)
            db.session.add(user_sub_commission_instance)
            db.session.flush()


    # TODO 降级-定时任务