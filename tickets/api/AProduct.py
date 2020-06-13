from ..control.CProduct import CProduct
from ..extensions.base_resource import Resource


class AProduct(Resource):
    def __init__(self):
        self.product = CProduct()

    def get(self, product):
        apis = {
            'list': self.product.list_product,
            'get': self.product.get_product,
            'get_promotion': self.product.get_promotion,
        }
        return apis

    def post(self, product):
        apis = {
            'verify': self.product.product_verified,
        }
        return apis
