from ..control.CCommision import CCommision
from ..extensions.base_resource import Resource


class ACommission(Resource):
    def __init__(self):
        self.ccom = CCommision()

    def get(self, commission):
        apis = {
            "get": self.ccom.get,
        }
        return apis

    def post(self, commission):
        apis = {
            'update': self.ccom.update,
        }
        return apis
