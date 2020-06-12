from ..control.COrder import COrder
from ..extensions.base_resource import Resource


class AOrder(Resource):
    def __init__(self):
        self.corder = COrder()

    def get(self, order):
        apis = {
            "list": self.corder.list,
            "list_omstatus": self.corder.list_omstatus,
            "get": self.corder.get,
        }
        return apis

    def post(self, order):
        apis = {
            'pay': self.corder.pay,
            'wechat_notify': self.corder.wechat_notify,
            'cancle': self.corder.cancle,
        }
        return apis
