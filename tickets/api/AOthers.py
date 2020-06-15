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
        }
        return apis
