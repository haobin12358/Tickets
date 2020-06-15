from ..control.COthers import COthers
from ..extensions.base_resource import Resource


class AOthers(Resource):
    def __init__(self):
        self.other = COthers()

    def get(self, string):
        apis = {
            'get_params': self.other.get_params,
            'location': self.other.get_location,  # 获取定位
        }
        return apis
