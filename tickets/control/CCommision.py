import json


from tickets.extensions.error_response import ParamsError
from tickets.extensions.params_validates import parameter_required
from tickets.extensions.success_response import Success
from tickets.extensions.interface.user_interface import admin_required
from tickets.extensions.register_ext import db
from tickets.models import Commision


class CCommision:

    @admin_required
    def update(self):
        """平台分销佣金设置"""
        # form = CommsionUpdateForm().valid_data()
        data = parameter_required()
        levelcommision = data.get('levelcommision')
        invitenum = data.get('invitenum', 0)
        groupsale = data.get('groupsale', 0)
        pesonalsale = data.get('pesonalsale', 0)
        invitenumscale = data.get('invitenumscale', 0)
        groupsalescale = data.get('groupsalescale', 0)
        pesonalsalescale = data.get('pesonalsalescale', 0)
        reduceratio = data.get('reduceratio')
        increaseratio = data.get('increaseratio')
        deviderate = data.get('deviderate')
        if not levelcommision or len(levelcommision) != 4:
            raise ParamsError('请设置四级佣金比')
        for comm in levelcommision:
            if comm <= 0 or comm > 100:
                raise ParamsError('佣金比不合适 需小于100, 大于0')
        # todo 其他参数校验，目前用不到，忽略校验

        with db.auto_commit():
            commision = Commision.query.filter(
                Commision.isdelete == False
            ).first()
            if not commision:
                commision = Commision()
            from tickets import JSONEncoder
            commission_dict = {
                'Levelcommision': json.dumps(levelcommision, cls=JSONEncoder),
                'InviteNum': invitenum,
                'GroupSale': groupsale,
                'PesonalSale': pesonalsale,
                'InviteNumScale': invitenumscale,
                'GroupSaleScale': groupsalescale,
                'PesonalSaleScale': pesonalsalescale,
                'ReduceRatio': json.dumps(reduceratio, cls=JSONEncoder),
                'IncreaseRatio': json.dumps(increaseratio, cls=JSONEncoder),
                'DevideRate': deviderate,
            }
            [setattr(commision, k, v) for k, v in commission_dict.items() if v is not None and v != '[]']
            # if not commision.InviteNum and not commision.PesonalSale and not commision.GroupSale:
            #     raise ParamsError('升级条件不可全为0')
            usercommision = levelcommision[:-1]
            if sum(usercommision) > 100:
                raise ParamsError('总佣金比大于100')
            db.session.add(commision)
            # BASEADMIN().create_action(AdminActionS.update.value, 'Commision', commision.COid)
        return Success('修改成功')

    def get(self):
        commision = Commision.query.filter(
            Commision.isdelete == False,
        ).first()
        commision.Levelcommision = json.loads(commision.Levelcommision)
        commision.ReduceRatio = json.loads(commision.ReduceRatio)
        commision.IncreaseRatio = json.loads(commision.IncreaseRatio)
        return Success(data=commision)
