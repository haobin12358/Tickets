# -*- coding: utf-8 -*-
from flask import Flask
from flask import Blueprint
from flask_cors import CORS

from .api import AHello, AFile, AUser, ACommission, AOrder
from .extensions.request_handler import error_handler, request_first_handler
from .config.secret import DefaltSettig
from .extensions.register_ext import register_ext
from .extensions.base_jsonencoder import JSONEncoder
from .extensions.base_request import Request


def register(app):
    bp = Blueprint(__name__, 'bp', url_prefix='/api')
    bp.add_url_rule('/user/<string:user>', view_func=AUser.as_view('user'))
    bp.add_url_rule('/file/<string:file>', view_func=AFile.as_view('file'))
    bp.add_url_rule('/hello/<string:hello>', view_func=AHello.as_view('hello'))
    bp.add_url_rule('/order/<string:order>', view_func=AOrder.as_view('order'))
    bp.add_url_rule('/commission/<string:commission>', view_func=ACommission.as_view('commission'))
    app.register_blueprint(bp)


def create_app():
    app = Flask(__name__)
    app.json_encoder = JSONEncoder
    app.request_class = Request
    app.config.from_object(DefaltSettig)
    register(app)
    CORS(app, supports_credentials=True)
    request_first_handler(app)
    register_ext(app)
    error_handler(app)
    return app
