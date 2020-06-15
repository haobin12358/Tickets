from ..control.COthers import COthers
from ..extensions.base_resource import Resource


class AOthers(Resource):
    def __init__(self):
        self.other = COthers()

    def get(self, string):
        apis = {
            'get_params': self.other.get_params,  # play/get_params
            'location': self.other.get_location,  # news/location 获取定位
            'list': self.other.brand_list,  # brand/list
            'list_role': self.other.list_role,  # play/list_role
            'get_dealing_approval': self.other.get_dealing_approval,  # approval/get_dealing_approval
        }
        return apis

    def post(self, string):
        apis = {
            'update_role': self.other.update_role,  # play/update_role
        }
        return apis
