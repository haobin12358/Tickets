from tickets.extensions.base_resource import Resource
from tickets.control.CActivation import CActivation


class AActivation(Resource):
    def __init__(self):
        self.cat = CActivation()

    def post(self, activation):
        apis = {
            'update_activationtype': self.cat.update_activationtype,
        }
        return apis

    def get(self, activation):
        apis = {
            'get_activationtype': self.cat.get_activationtype,
            'list_activationtype': self.cat.list_activationtype,
            # 'get_userlinkage': self.cat.get_userlinkage,
            'get_duration_activation': self.cat.get_duration_activation,
        }
        return apis
